"""Asterisk ARI transport (E13-03, ADR-0023/0033) — REST + WS behaviour with a
mocked gateway, plus the adapter's health wiring. Real-Asterisk coverage is the
`sip` compose profile integration test (E13-08)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from integrations.telephony_sip.adapter import build
from integrations.telephony_sip.ari import AriClient, AriConfig, AriError

_INFO = {"system": {"version": "20.9.0"}, "config": {"name": "asterisk"}}


def _client(handler: Any, **cfg: Any) -> AriClient:
    return AriClient(
        AriConfig(host="pbx.test", username="bbz", password="s3cret", **cfg),
        transport=httpx.MockTransport(handler),
    )


async def test_info_probe_hits_the_right_url_with_basic_auth() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_INFO)

    ari = _client(handler)
    assert (await ari.info())["system"]["version"] == "20.9.0"
    assert seen["url"] == "http://pbx.test:8088/ari/asterisk/info"
    assert seen["auth"] and seen["auth"].startswith("Basic ")
    await ari.aclose()


async def test_rest_errors_become_arierror_without_leaking_the_response() -> None:
    ari = _client(lambda r: httpx.Response(503, text="gateway down, secret=s3cret"))
    with pytest.raises(AriError) as exc:
        await ari.info()
    assert "s3cret" not in str(exc.value)
    assert "/asterisk/info" in str(exc.value)
    await ari.aclose()


async def test_control_verbs_map_to_channel_endpoints() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        return httpx.Response(204)

    ari = _client(handler)
    await ari.answer("ch1")
    await ari.hangup("ch1")
    await ari.hold("ch1")
    await ari.unhold("ch1")
    await ari.send_dtmf("ch1", "12#")
    await ari.redirect("ch1", "PJSIP/line2")
    await ari.aclose()

    assert "POST /ari/channels/ch1/answer?" in calls
    # hang up is DELETE /channels/{id}; remove-hold is DELETE /channels/{id}/hold
    assert "DELETE /ari/channels/ch1?" in calls
    assert "POST /ari/channels/ch1/hold?" in calls
    assert "DELETE /ari/channels/ch1/hold?" in calls
    assert any("dtmf?dtmf=12" in c and "%23" in c for c in calls)
    assert any("redirect?endpoint=PJSIP" in c for c in calls)


async def test_ws_uri_and_auth_header_carry_no_credentials_in_the_url() -> None:
    ari = _client(lambda r: httpx.Response(200, json=_INFO), app_name="bbz-sip")
    uri = ari._ws_uri()
    assert uri == "ws://pbx.test:8088/ari/events?app=bbz-sip"
    # the password / an api_key never go in the URL — only the Basic auth header
    assert "s3cret" not in uri
    assert "api_key" not in uri
    assert ari._auth_header()["Authorization"].startswith("Basic ")
    await ari.aclose()


# --- adapter health wiring ------------------------------------------------


def _cfg(**gw: Any) -> dict[str, Any]:
    return {
        "gateway": {"kind": "asterisk_ari", "host": "pbx.test", **gw},
        "credentials": {"username": "bbz", "password": "s3cret"},
        "lines": ["2001"],
    }


async def test_build_without_a_gateway_stays_a_scaffold() -> None:
    p = build({"lines": ["2001"]})
    h = await p.health()
    assert h.state.value == "unknown"
    assert "scaffold" in h.summary


async def test_health_reports_unavailable_when_ari_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = build(_cfg())

    async def _boom(_self: Any) -> Any:
        raise AriError("ARI GET /asterisk/info: ConnectError")

    monkeypatch.setattr(AriClient, "info", _boom)
    h = await p.health()
    assert h.state.value == "unavailable"
    assert "unreachable" in h.summary
    await p.shutdown()


async def test_health_is_degraded_when_rest_is_up_but_the_event_stream_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = build(_cfg())

    async def _info(_self: Any) -> dict[str, Any]:
        return _INFO

    monkeypatch.setattr(AriClient, "info", _info)
    h = await p.health()
    assert h.state.value == "degraded"  # ws.connected is False until events() runs
    assert h.details["asterisk_version"] == "20.9.0"
    await p.shutdown()


async def test_events_yields_parsed_frames_and_skips_garbage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [json.dumps({"type": "StasisStart", "channel": {"id": "c1"}}), "not json", b"\x00"]

    class _FakeWs:
        async def __aenter__(self) -> _FakeWs:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        def __aiter__(self) -> _FakeWs:
            self._it = iter(frames)
            return self

        async def __anext__(self) -> Any:
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration from None

    def _connect(*_: Any, **__: Any) -> _FakeWs:
        return _FakeWs()

    monkeypatch.setattr("integrations.telephony_sip.ari.websockets.connect", _connect)
    ari = _client(lambda r: httpx.Response(200, json=_INFO))
    got = []
    async for ev in ari.events(reconnect=False):
        got.append(ev)
    assert got == [{"type": "StasisStart", "channel": {"id": "c1"}}]
    assert ari.ws.connected is False  # clean end
    await ari.aclose()
