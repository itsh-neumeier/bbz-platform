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
