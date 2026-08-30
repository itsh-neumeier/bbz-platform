"""Application leader election (ADR-0018).

Cluster-wide singletons (the outbox dispatcher, later the CUCM control leader)
run on exactly one app node, chosen by a short-lived etcd lease with keepalive.
On any doubt — lease lost, connection to etcd gone — the holder *steps down
immediately*; another node takes over within ``2 * ttl``.

Two backends:

* :class:`LocalLeaderElection` — always the leader. Single-node dev / tests
  with no etcd (``BBZ_WORKER_LEADER_BACKEND=""``).
* :class:`EtcdLeaderElection` — the real thing, over etcd's v3 HTTP/JSON gateway
  (so no gRPC client dependency); ``BBZ_WORKER_LEADER_BACKEND="etcd"``.

Even during a hand-off the outbox ``dedupe_key`` / ``SKIP LOCKED`` prevent a
double side effect — this is defence in depth.
"""

from __future__ import annotations

import base64
import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)


@dataclass(frozen=True)
class EtcdTls:
    """mTLS material for the etcd client (ADR-0018). Empty strings -> plain HTTP."""

    ca_file: str = ""
    cert_file: str = ""
    key_file: str = ""


class LeaderElection(ABC):
    name: str

    @abstractmethod
    async def acquire(self) -> bool:
        """Try to become leader. True if we hold leadership now."""

    @abstractmethod
    async def renew(self) -> bool:
        """Renew leadership. False means we lost it and must stop."""

    @abstractmethod
    async def resign(self) -> None:
        """Give up leadership promptly (best effort)."""


class LocalLeaderElection(LeaderElection):
    def __init__(self, name: str) -> None:
        self.name = name

    async def acquire(self) -> bool:
        return True

    async def renew(self) -> bool:
        return True

    async def resign(self) -> None:
        return None


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class EtcdLeaderElection(LeaderElection):
    def __init__(
        self,
        name: str,
        *,
        node_id: str,
        endpoints: list[str],
        ttl_seconds: int,
        prefix: str = "/bbz/leader",
        tls: EtcdTls | None = None,
    ) -> None:
        self.name = name
        self._node_id = node_id
        self._base = endpoints[0].rstrip("/")
        self._ttl = ttl_seconds
        self._key = f"{prefix.rstrip('/')}/{name}"
        self._lease_id: int | None = None
        verify: bool | str = tls.ca_file if tls and tls.ca_file else True
        cert = (tls.cert_file, tls.key_file) if tls and tls.cert_file and tls.key_file else None
        self._client = httpx.AsyncClient(
            timeout=max(2.0, ttl_seconds / 2), verify=verify, cert=cert
        )

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(f"{self._base}{path}", json=body)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def acquire(self) -> bool:
        try:
            grant = await self._post("/v3/lease/grant", {"TTL": str(self._ttl)})
            lease_id = int(grant["ID"])
            # atomic: put the lock key only if nobody created it yet
            txn = await self._post(
                "/v3/kv/txn",
                {
                    "compare": [
                        {
                            "key": _b64(self._key),
                            "target": "CREATE",
                            "result": "EQUAL",
                            "create_revision": "0",
                        }
                    ],
                    "success": [
                        {
                            "request_put": {
                                "key": _b64(self._key),
                                "value": _b64(self._node_id),
                                "lease": str(lease_id),
                            }
                        }
                    ],
                    "failure": [{"request_range": {"key": _b64(self._key)}}],
                },
            )
            if txn.get("succeeded"):
                self._lease_id = lease_id
                _log.info("leader_acquired", election=self.name, node_id=self._node_id)
                return True
            # someone else holds it — release the lease we just grabbed
            await self._post("/v3/lease/revoke", {"ID": str(lease_id)})
            return False
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            _log.warning("leader_acquire_failed", election=self.name, error=str(exc))
            return False

    async def renew(self) -> bool:
        if self._lease_id is None:
            return False
        try:
            resp = await self._post("/v3/lease/keepalive", {"ID": str(self._lease_id)})
            ttl = int(resp.get("result", {}).get("TTL", "0"))
            if ttl <= 0:
                await self.resign()
                return False
            return True
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            _log.warning("leader_renew_failed", election=self.name, error=str(exc))
            await self.resign()
            return False

    async def resign(self) -> None:
        lease_id, self._lease_id = self._lease_id, None
        if lease_id is not None:
            with contextlib.suppress(httpx.HTTPError):
                await self._post("/v3/lease/revoke", {"ID": str(lease_id)})
        _log.info("leader_resigned", election=self.name, node_id=self._node_id)

    async def aclose(self) -> None:
        await self.resign()
        await self._client.aclose()


def leader_election_for(name: str) -> LeaderElection:
    s = get_settings()
    if s.worker_leader_backend == "etcd":
        return EtcdLeaderElection(
            name,
            node_id=s.node_id,
            endpoints=s.cluster_dcs_endpoints,
            ttl_seconds=s.worker_leader_ttl_seconds,
            prefix=s.worker_leader_prefix,
            tls=EtcdTls(
                ca_file=s.cluster_dcs_tls_ca_file,
                cert_file=s.cluster_dcs_tls_cert_file,
                key_file=s.cluster_dcs_tls_key_file,
            ),
        )
    return LocalLeaderElection(name)
