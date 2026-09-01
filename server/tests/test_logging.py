"""Structured-log pipeline (E22-03): field consistency, key + transient
redaction, per-module levels, noisy-event sampling, the file sink."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from bbz_core.logging import configure_logging, correlation_id, get_logger, user_id
from bbz_core.redaction import MASK, redacting

Configure = Callable[..., io.StringIO]


@pytest.fixture
def cfg() -> Iterator[Configure]:
    """Return a helper that (re)configures logging to a fresh buffer."""
    bufs: list[io.StringIO] = []

    def _configure(**kwargs: object) -> io.StringIO:
        buf = io.StringIO()
        bufs.append(buf)
        configure_logging(json=True, node_id="BBZ-TEST", stream=buf, **kwargs)  # type: ignore[arg-type]
        return buf

    yield _configure
    configure_logging(level="INFO", json=False, node_id="unknown")


def _lines(buf: io.StringIO) -> list[dict]:
    return [json.loads(x) for x in buf.getvalue().splitlines() if x.strip()]


def test_every_line_carries_the_baseline_fields(cfg: Configure) -> None:
    buf = cfg(level="INFO")
    get_logger("bbz_core.demo").info("started")
    (line,) = _lines(buf)
    assert line["event"] == "started"
    assert line["level"] == "info"
    assert line["node_id"] == "BBZ-TEST"
    assert line["logger"] == "bbz_core.demo"
    assert "timestamp" in line


def test_request_context_fields_are_added_only_when_present(cfg: Configure) -> None:
    buf = cfg(level="INFO")
    log = get_logger("bbz_core.demo")
    log.info("anon")
    ct = correlation_id.set("corr-1")
    ut = user_id.set("user-42")
    log.info("in_request")
    correlation_id.reset(ct)
    user_id.reset(ut)

    anon, scoped = _lines(buf)
    assert "correlation_id" not in anon and "user_id" not in anon
    assert scoped["correlation_id"] == "corr-1"
    assert scoped["user_id"] == "user-42"


def test_sensitive_keys_are_redacted(cfg: Configure) -> None:
    buf = cfg(level="INFO")
    get_logger("bbz_core.demo").info(
        "auth_attempt",
        username="alice",
        password="hunter2",
        headers={"Authorization": "Bearer abc", "X-Trace": "ok"},
        dtmf_sequence="9A9A#9A",
        refresh_token="r-123",
    )
    (line,) = _lines(buf)
    assert line["username"] == "alice"
    assert line["password"] == MASK
    assert line["refresh_token"] == MASK
    assert line["dtmf_sequence"] == MASK
    assert line["headers"]["Authorization"] == MASK
    assert line["headers"]["X-Trace"] == "ok"


def test_a_registered_transient_secret_is_still_scrubbed(cfg: Configure) -> None:
    buf = cfg(level="INFO")
    with redacting("SUPER-SECRET-DTMF"):
        get_logger("bbz_core.demo").warning(
            "provider_error", detail="gateway rejected SUPER-SECRET-DTMF"
        )
    (line,) = _lines(buf)
    assert "SUPER-SECRET-DTMF" not in json.dumps(line)
    assert MASK in line["detail"]


def test_per_module_level_override(cfg: Configure) -> None:
    buf = cfg(level="INFO", module_levels="bbz_core.chatty=WARNING")
    get_logger("bbz_core.chatty").info("noise")  # dropped
    get_logger("bbz_core.chatty").warning("real")  # kept
    get_logger("bbz_core.other").info("kept")  # a different module, kept
    assert {line["event"] for line in _lines(buf)} == {"real", "kept"}


def test_a_more_specific_module_prefix_wins(cfg: Configure) -> None:
    buf = cfg(level="DEBUG", module_levels="bbz_core=WARNING,bbz_core.infra.leader=DEBUG")
    get_logger("bbz_core.infra.leader").debug("election")  # specific -> DEBUG -> kept
    get_logger("bbz_core.infra.other").info("muted")  # broad -> WARNING -> dropped
    assert {line["event"] for line in _lines(buf)} == {"election"}


def test_noisy_event_sampling(cfg: Configure) -> None:
    buf = cfg(level="INFO", sample="heartbeat=0")
    log = get_logger("bbz_core.demo")
    for _ in range(20):
        log.info("heartbeat")  # rate 0 -> all dropped
    log.info("real_event")  # not sampled -> kept
    assert [line["event"] for line in _lines(buf)] == ["real_event"]


def test_log_file_sink_tees_the_lines(tmp_path: Path) -> None:
    target = tmp_path / "bbz.log"
    configure_logging(json=True, node_id="BBZ-TEST", log_file=str(target))
    try:
        get_logger("bbz_core.demo").info("to_file")
        import logging as _l

        for h in _l.getLogger().handlers:
            h.flush()
        import sys

        sys.stdout.flush()
        assert '"event": "to_file"' in target.read_text(encoding="utf-8")
    finally:
        configure_logging(level="INFO", json=False, node_id="unknown")
