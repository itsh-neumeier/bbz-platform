"""E22-07: the optional observability stack — collector / Prometheus / Grafana
config validity and the dashboard JSON (every panel queries a metric we export)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_MON = _REPO / "deploy" / "monitoring"
_DASHBOARDS = sorted((_MON / "dashboards").glob("*.json"))

_METRIC_RE = re.compile(r"\bbbz_[a-z0-9_]+\b")
_HIST_SUFFIXES = ("_bucket", "_count", "_sum", "_created", "_total")


def _exported_metric_names() -> set[str]:
    from bbz_core.infra.metrics import REGISTRY

    return {c.name for c in REGISTRY.collect()}


def _base(name: str) -> str:
    for suffix in _HIST_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def test_the_monitoring_stack_files_exist() -> None:
    assert (_MON / "collector" / "otel-collector-config.yaml").is_file()
    assert (_MON / "prometheus" / "prometheus.yml").is_file()
    assert (_MON / "grafana" / "provisioning" / "datasources" / "prometheus.yml").is_file()
    assert (_MON / "grafana" / "provisioning" / "dashboards" / "bbz.yml").is_file()
    assert len(_DASHBOARDS) >= 3


def test_collector_config_is_a_valid_traces_pipeline() -> None:
    cfg = yaml.safe_load((_MON / "collector" / "otel-collector-config.yaml").read_text("utf-8"))
    assert "otlp" in cfg["receivers"]
    traces = cfg["service"]["pipelines"]["traces"]
    assert traces["receivers"] == ["otlp"]
    assert traces["exporters"]  # at least one
    # every referenced component is defined
    for stage in ("receivers", "processors", "exporters"):
        for comp in traces.get(stage, []):
            assert comp in cfg.get(stage, {}), f"{comp} used in traces but not defined"


def test_prometheus_config_loads_the_alert_rules() -> None:
    cfg = yaml.safe_load((_MON / "prometheus" / "prometheus.yml").read_text("utf-8"))
    assert any("bbz.rules.yml" in rf for rf in cfg["rule_files"])
    jobs = {j["job_name"] for j in cfg["scrape_configs"]}
    assert "bbz-api" in jobs
    api = next(j for j in cfg["scrape_configs"] if j["job_name"] == "bbz-api")
    assert api["metrics_path"] == "/api/v1/system/metrics"  # the gated endpoint


def test_grafana_provisioning_is_valid() -> None:
    ds = yaml.safe_load(
        (_MON / "grafana" / "provisioning" / "datasources" / "prometheus.yml").read_text("utf-8")
    )
    assert ds["datasources"][0]["type"] == "prometheus"
    assert ds["datasources"][0]["uid"] == "bbz-prometheus"
    prov = yaml.safe_load(
        (_MON / "grafana" / "provisioning" / "dashboards" / "bbz.yml").read_text("utf-8")
    )
    assert prov["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards"


@pytest.mark.parametrize("path", _DASHBOARDS, ids=lambda p: p.name)
def test_dashboard_json_is_well_formed_and_queries_real_metrics(path: Path) -> None:
    dash = json.loads(path.read_text("utf-8"))
    assert dash["uid"] and dash["title"] and dash["schemaVersion"] >= 39
    assert dash["panels"], "no panels"

    exported = _exported_metric_names()
    for panel in dash["panels"]:
        assert panel["title"]
        assert panel["gridPos"]
        targets = panel.get("targets", [])
        assert targets, f"panel {panel['title']!r} has no targets"
        for target in targets:
            expr = target["expr"]
            metrics = {_base(m) for m in _METRIC_RE.findall(expr)}
            assert metrics, f"panel {panel['title']!r}: no bbz_ metric in {expr!r}"
            unknown = metrics - exported
            assert not unknown, f"panel {panel['title']!r} queries unexported metric(s): {unknown}"


def test_every_dashboard_uses_the_provisioned_datasource() -> None:
    for path in _DASHBOARDS:
        dash = json.loads(path.read_text("utf-8"))
        for panel in dash["panels"]:
            assert panel["datasource"]["uid"] == "bbz-prometheus"
