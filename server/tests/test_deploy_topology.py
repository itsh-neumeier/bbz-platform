"""deploy/ per-node + quorum compose topology invariants (roadmap E06-01).

The real HA behaviour (Patroni failover, etcd quorum) is not testable here;
what CI *can* guard cheaply is the shape of the deployment: the quorum host
runs etcd only, a node runs the full stack, images are pinned, and no
plaintext credential sits in a committed file.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_NODE = _ROOT / "deploy" / "node"
_QUORUM = _ROOT / "deploy" / "quorum"
_ETCD = _ROOT / "deploy" / "etcd"


def _etcd_command(compose_path: Path) -> list[str]:
    return _compose(compose_path)["services"]["etcd"]["command"]


def _env_example(base: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (base / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip("'\"")
    return out


def _compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_quorum_runs_only_etcd() -> None:
    c = _compose(_QUORUM / "docker-compose.yml")
    assert set(c["services"]) == {"etcd"}
    assert c["name"] == "bbz-quorum"
    # no BBZ domain service image may ever leak onto the witness host
    images = {svc.get("image", "") for svc in c["services"].values()}
    for img in images:
        assert not any(x in img for x in ("bbz-api", "bbz-web", "spilo", "patroni")), img


def test_quorum_container_is_hardened() -> None:
    etcd = _compose(_QUORUM / "docker-compose.yml")["services"]["etcd"]
    assert etcd["read_only"] is True
    assert etcd["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in etcd["security_opt"]
    assert "mem_limit" in etcd and "pids_limit" in etcd
    # published ports bound via a configurable interface, not hard 0.0.0.0
    assert all("${QUORUM_BIND" in p for p in etcd["ports"])


def test_quorum_hardening_and_runbook_exist() -> None:
    assert (_QUORUM / "HARDENING.md").read_text(encoding="utf-8").strip()
    rb = (_ROOT / "docs" / "runbooks" / "quorum-node.md").read_text(encoding="utf-8")
    assert "BBZ-QUORUM01" in rb and "member add" in rb


def test_node_stack_has_every_service() -> None:
    c = _compose(_NODE / "docker-compose.yml")
    assert c["name"] == "bbz-node"
    assert {"etcd", "postgres", "api", "web", "reverse-proxy"} <= set(c["services"])


def test_node_and_quorum_are_separate_from_the_dev_stack() -> None:
    dev = _compose(_ROOT / "docker-compose.yml")
    assert dev["name"] == "bbz-platform"
    assert dev["name"] not in {"bbz-node", "bbz-quorum"}


@pytest.mark.parametrize("path", [_NODE / "docker-compose.yml", _QUORUM / "docker-compose.yml"])
def test_literal_images_are_pinned(path: Path) -> None:
    c = _compose(path)
    for name, svc in c["services"].items():
        image = svc.get("image", "")
        if image.startswith("${"):  # supplied per-deployment via .env
            continue
        assert ":" in image and not image.endswith(":latest"), f"{name}: {image!r}"


@pytest.mark.parametrize("path", [_NODE / "docker-compose.yml", _QUORUM / "docker-compose.yml"])
def test_no_plaintext_credentials_in_compose(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", "-")) or "PASSWORD" not in stripped.upper():
            continue
        key, _, value = stripped.partition(":")
        value = value.strip()
        if not value:  # a bare `name:` key (e.g. a secrets: definition)
            continue
        # a password *value* must resolve from an env var or a secret file
        # (either the compose `secrets:` file source or a /run/secrets mount)
        assert "${" in value or "secrets/" in value or key.upper().endswith("_FILE"), stripped


def test_secret_templates_exist_but_no_real_secret_is_committed() -> None:
    examples = sorted(p.name for p in (_NODE / "secrets").glob("*.example"))
    assert examples == [
        "bbz_jwt_secret.example",
        "bbz_totp_encryption_key.example",
        "postgres_replication_password.example",
        "postgres_superuser_password.example",
    ]
    real = [p for p in (_NODE / "secrets").iterdir() if not p.name.endswith(".example")]
    assert real == [], f"committed secret files: {real}"


def test_env_examples_exist_and_no_real_env_is_committed() -> None:
    for base in (_NODE, _QUORUM):
        assert (base / ".env.example").read_text(encoding="utf-8").strip()
        assert not (base / ".env").exists()


# --- E06-02: Patroni replication + failover config (ADR-0021) ---------------

_PATRONI = _NODE / "patroni" / "patroni.node.yml"
_ADR_0021 = _ROOT / ".ai" / "DECISIONS" / "ADR-0021-POSTGRESQL-REPLICATION-MODE.md"


def _patroni_raw() -> str:
    # the file carries ${ENV} placeholders, so read it as text
    return _PATRONI.read_text(encoding="utf-8")


def test_patroni_uses_synchronous_replication_with_fallback() -> None:
    text = _patroni_raw()
    assert "synchronous_mode: true" in text
    assert "synchronous_mode_strict: false" in text  # a lone primary stays writable
    assert "maximum_lag_on_failover:" in text  # a laggy standby is never promoted
    assert "namespace: /patroni/" in text  # ADR-0018 key-prefix split
    assert "use_pg_rewind: true" in text  # demoted primary rejoins without a base backup


def test_patroni_defines_a_failover_timing_budget() -> None:
    text = _patroni_raw()
    for key in ("ttl:", "loop_wait:", "retry_timeout:", "master_start_timeout:"):
        assert key in text, key


def test_replication_and_superuser_credentials_are_separate_secrets() -> None:
    c = _compose(_NODE / "docker-compose.yml")
    pg_secrets = set(c["services"]["postgres"]["secrets"])
    assert {"postgres_superuser_password", "postgres_replication_password"} <= pg_secrets
    text = _patroni_raw()
    assert "username: postgres" in text and "username: standby" in text


def test_adr_0021_is_accepted_and_indexed() -> None:
    adr = _ADR_0021.read_text(encoding="utf-8")
    assert "# ADR-0021:" in adr
    status = adr.split("## Status", 1)[1].split("##", 1)[0]
    assert status.strip().splitlines()[0].strip() == "Accepted"
    index = (_ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    assert "| 0021 |" in index and "Accepted |" in index.split("| 0021 |", 1)[1].splitlines()[0]


def test_db_failover_runbook_points_at_adr_0021() -> None:
    rb = (_ROOT / "docs" / "runbooks" / "db-failover.md").read_text(encoding="utf-8")
    assert "ADR-0021" in rb
    assert "RTO" in rb and "RPO" in rb


# --- E06-03: etcd 3-member cluster with mutual TLS (ADR-0018) ---------------


@pytest.mark.parametrize("path", [_NODE / "docker-compose.yml", _QUORUM / "docker-compose.yml"])
def test_etcd_enforces_mutual_tls_on_both_planes(path: Path) -> None:
    cmd = " ".join(_etcd_command(path))
    # client plane
    assert "--client-cert-auth" in cmd
    assert "--trusted-ca-file=" in cmd and "--cert-file=" in cmd
    assert "--listen-client-urls=https://" in cmd
    # peer plane
    assert "--peer-client-cert-auth" in cmd
    assert "--peer-trusted-ca-file=" in cmd and "--peer-cert-file=" in cmd
    assert "--listen-peer-urls=https://" in cmd
    # no plaintext endpoint except the local-only Prometheus /metrics listener
    non_metrics = [a for a in _etcd_command(path) if not a.startswith("--listen-metrics-urls=")]
    assert "http://" not in " ".join(non_metrics)


@pytest.mark.parametrize("path", [_NODE / "docker-compose.yml", _QUORUM / "docker-compose.yml"])
def test_every_member_lists_all_three_peers(path: Path) -> None:
    cmd = " ".join(_etcd_command(path))
    assert "${ETCD_INITIAL_CLUSTER" in cmd
    cluster = _env_example(path.parent)["ETCD_INITIAL_CLUSTER"]
    assert cluster.count("https://") == 3
    assert {"BBZ-SRV01", "BBZ-SRV02", "BBZ-QUORUM01"} <= set(cluster.replace("=", ",").split(","))


def test_bootstrap_auth_scopes_patroni_and_app_to_separate_prefixes() -> None:
    sh = (_ETCD / "bootstrap-auth.sh").read_text(encoding="utf-8")
    assert "role grant-permission patroni readwrite --prefix=true /patroni/" in sh
    assert "role grant-permission bbz readwrite --prefix=true /bbz/" in sh
    assert "auth enable" in sh


def test_etcd_helper_scripts_are_present_and_posix() -> None:
    for name in ("gen-certs.sh", "bootstrap-auth.sh", "snapshot.sh"):
        head = (_ETCD / name).read_text(encoding="utf-8").splitlines()[0]
        assert head.startswith("#!") and "sh" in head


def test_patroni_talks_to_etcd_over_tls_as_the_patroni_user() -> None:
    text = _patroni_raw()
    assert "protocol: https" in text
    assert "cert: /etc/etcd/certs/client-patroni.crt" in text


def test_generated_etcd_certs_are_gitignored() -> None:
    probe = _NODE / "etcd" / "certs" / "BBZ-SRV01-peer.key"
    r = subprocess.run(
        ["git", "check-ignore", str(probe)], cwd=_ROOT, capture_output=True, text=True
    )
    assert r.returncode == 0, "deploy/**/etcd/certs/ must be gitignored"


@pytest.mark.skipif(
    not (shutil.which("sh") and shutil.which("openssl")),
    reason="needs sh + openssl",
)
def test_gen_certs_produces_a_ca_signed_member_and_client_cert(tmp_path: Path) -> None:
    out = tmp_path / "certs"
    env = {
        "PATH": __import__("os").environ["PATH"],
        "OUT": str(out),
        "MEMBERS": "BBZ-SRV01=bbz-srv01,10.0.0.11 BBZ-QUORUM01=bbz-quorum01,10.0.0.13",
        "CLIENTS": "client-patroni client-bbz-app",
        "DAYS": "30",
    }
    subprocess.run(["sh", str(_ETCD / "gen-certs.sh")], env=env, check=True, capture_output=True)
    assert (out / "ca.crt").exists()
    verify = subprocess.run(
        [
            "openssl",
            "verify",
            "-CAfile",
            "ca.crt",
            "BBZ-SRV01-peer.crt",
            "client-patroni.crt",
        ],
        cwd=out,
        capture_output=True,
        text=True,
    )
    assert verify.returncode == 0, verify.stderr
    san = subprocess.run(
        ["openssl", "x509", "-in", "BBZ-SRV01-peer.crt", "-noout", "-text"],
        cwd=out,
        capture_output=True,
        text=True,
    ).stdout
    assert "bbz-srv01" in san and "10.0.0.11" in san
