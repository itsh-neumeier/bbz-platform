"""deploy/ per-node + quorum compose topology invariants (roadmap E06-01).

The real HA behaviour (Patroni failover, etcd quorum) is not testable here;
what CI *can* guard cheaply is the shape of the deployment: the quorum host
runs etcd only, a node runs the full stack, images are pinned, and no
plaintext credential sits in a committed file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_NODE = _ROOT / "deploy" / "node"
_QUORUM = _ROOT / "deploy" / "quorum"


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
