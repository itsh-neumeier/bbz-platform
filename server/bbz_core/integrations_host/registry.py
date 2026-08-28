from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bbz_integration_sdk.manifest import IntegrationManifest, validate_manifest


def _repo_root() -> Path:
    # server/bbz_core/integrations_host/registry.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def integrations_dir() -> Path:
    return _repo_root() / "integrations"


@dataclass(frozen=True)
class LoadedManifest:
    path: Path
    manifest: IntegrationManifest


class IntegrationRegistry:
    """Discovers and validates integration manifests.

    Phase 0: discovery + schema validation only. Adapter loading and lifecycle
    (enable/disable, health, mock-mode) arrive with Phase 1.
    """

    @staticmethod
    def discover() -> list[LoadedManifest]:
        base = integrations_dir()
        if not base.is_dir():
            return []
        out: list[LoadedManifest] = []
        for manifest_path in sorted(base.glob("*/manifest.json")):
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            out.append(LoadedManifest(path=manifest_path, manifest=validate_manifest(raw)))
        return out

    @staticmethod
    def discover_manifest_ids() -> list[str]:
        return [lm.manifest.id for lm in IntegrationRegistry.discover()]
