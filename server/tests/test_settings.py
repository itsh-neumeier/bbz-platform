from __future__ import annotations

from bbz_core.settings import Settings


def test_database_url_sync_uses_sync_driver() -> None:
    s = Settings(database_url="postgresql+asyncpg://u:p@h:5432/db")
    assert s.database_url_sync == "postgresql+psycopg://u:p@h:5432/db"
    plain = Settings(database_url="postgresql://u:p@h:5432/db")
    assert plain.database_url_sync == "postgresql+psycopg://u:p@h:5432/db"


def test_env_prefix(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BBZ_NODE_ID", "BBZ-SRV02")
    monkeypatch.setenv("BBZ_CLUSTER_DCS", "consul")
    s = Settings()
    assert s.node_id == "BBZ-SRV02"
    assert s.cluster_dcs == "consul"


def test_integration_host_discovers_repo_manifests() -> None:
    from bbz_core.integrations_host.registry import IntegrationRegistry

    ids = IntegrationRegistry.discover_manifest_ids()
    assert "telephony_mock" in ids
    # every discovered manifest validated against the SDK schema without raising
    assert len(ids) == len(set(ids))
