"""DWD weather-warnings client + CAP 1.2 parser (roadmap E18-02, ADR-0026).

Source: the DWD Open Data CAP feed
``opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/`` — Landkreis /
kreisfreie-Stadt granularity (WARNCELLID prefix ``1``), the operationally right
level for a Leitstelle. The directory holds
``Z_CAP_C_EDZW_<UTCts>_PVW_STATUS_PREMIUMDWD_DISTRICT_DE.zip`` files updated every
~10 min; the lexically-last is current. Each zip is a handful of CAP 1.2 XML
alerts.

:func:`parse_cap_alerts` is a pure function over the XML. :class:`DwdWarningsClient`
does the (blocking) HTTP + unzip — the adapter runs it in a thread. Every fetch
or parse failure is a raise; keeping the last-good snapshot is E18-06's job.

XML: parsed with stdlib ``ElementTree`` (expat resolves no external entities).
Input is size-capped and the source is DWD HTTPS; swap in ``defusedxml`` if the
threat model tightens.
"""

from __future__ import annotations

import datetime as _dt
import io
import re
import urllib.request
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

_CAP_NS = "{urn:oasis:names:tc:emergency:cap:1.2}"
_DIST_RE = re.compile(r"Z_CAP_C_EDZW_\d+_PVW_STATUS_PREMIUMDWD_DISTRICT_DE\.zip")

#: CAP severity → DWD warn level (1 yellow … 4 violet)
_LEVEL_BY_SEVERITY = {"Minor": "1", "Moderate": "2", "Severe": "3", "Extreme": "4"}

_MAX_ZIP_BYTES = 25 * 1024 * 1024
_MAX_XML_BYTES = 2 * 1024 * 1024
_TIMEOUT = 30

DEFAULT_BASE_URL = "https://opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/"


class DwdWarningsError(RuntimeError):
    """A fetch or parse of the DWD warnings feed failed."""


@dataclass(frozen=True)
class NormalizedAlert:
    region: str
    type: str
    level: str
    valid_from: _dt.datetime | None
    valid_to: _dt.datetime | None
    headline: str | None
    description: str | None
    source_ref: str
    warncell_id: str

    def as_item(self) -> dict[str, object]:
        """The dict shape the E18-06 refresh expects (``_ALERT_FIELDS``)."""
        return {
            "region": self.region,
            "type": self.type,
            "level": self.level,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "headline": self.headline,
            "description": self.description,
            "source_ref": self.source_ref,
        }


def _text(node: ET.Element | None) -> str | None:
    return node.text.strip() if node is not None and node.text and node.text.strip() else None


def _parse_dt(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.astimezone(_dt.UTC) if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)


def parse_cap_alerts(xml: bytes | str) -> list[NormalizedAlert]:
    """Every ``(alert, de-DE info, area)`` → one :class:`NormalizedAlert`.

    Skips ``msgType == "Cancel"`` (an entwarnung — the alert simply stops being
    in the feed) and areas without a WARNCELLID.
    """
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    if len(xml) > _MAX_XML_BYTES:
        raise DwdWarningsError(f"CAP document too large ({len(xml)} bytes)")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise DwdWarningsError(f"malformed CAP XML: {exc}") from exc

    if _text(root.find(f"{_CAP_NS}msgType")) == "Cancel":
        return []
    identifier = _text(root.find(f"{_CAP_NS}identifier"))
    if not identifier:
        return []

    out: list[NormalizedAlert] = []
    for info in root.findall(f"{_CAP_NS}info"):
        if (_text(info.find(f"{_CAP_NS}language")) or "de-DE").lower() not in {"de-de", "de"}:
            continue
        event = _text(info.find(f"{_CAP_NS}event")) or "Wetterwarnung"
        severity = _text(info.find(f"{_CAP_NS}severity")) or ""
        level = _LEVEL_BY_SEVERITY.get(severity, severity or "1")
        valid_from = _parse_dt(_text(info.find(f"{_CAP_NS}onset"))) or _parse_dt(
            _text(info.find(f"{_CAP_NS}effective"))
        )
        valid_to = _parse_dt(_text(info.find(f"{_CAP_NS}expires")))
        headline = _text(info.find(f"{_CAP_NS}headline"))
        description = _text(info.find(f"{_CAP_NS}description"))
        instruction = _text(info.find(f"{_CAP_NS}instruction"))
        if instruction:
            description = f"{description}\n\n{instruction}" if description else instruction

        for area in info.findall(f"{_CAP_NS}area"):
            area_desc = _text(area.find(f"{_CAP_NS}areaDesc"))
            warncell = None
            for gc in area.findall(f"{_CAP_NS}geocode"):
                if _text(gc.find(f"{_CAP_NS}valueName")) == "WARNCELLID":
                    warncell = _text(gc.find(f"{_CAP_NS}value"))
            if not area_desc or not warncell:
                continue
            out.append(
                NormalizedAlert(
                    region=area_desc,
                    type=event,
                    level=level,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    headline=headline,
                    description=description,
                    source_ref=identifier,
                    warncell_id=warncell,
                )
            )
    return out


class DwdWarningsClient:
    """Blocking HTTP + unzip against the DWD CAP DISTRICT feed."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: int = _TIMEOUT) -> None:
        self._base = base_url if base_url.endswith("/") else base_url + "/"
        self._timeout = timeout

    def _get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "bbz-platform/dwd"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data: bytes = resp.read(_MAX_ZIP_BYTES + 1)
        except (OSError, ValueError) as exc:
            raise DwdWarningsError(f"GET {url} failed: {exc}") from exc
        if len(data) > _MAX_ZIP_BYTES:
            raise DwdWarningsError(f"response from {url} exceeds {_MAX_ZIP_BYTES} bytes")
        return data

    def latest_zip_name(self) -> str:
        listing = self._get(self._base).decode("utf-8", "replace")
        names = sorted(set(_DIST_RE.findall(listing)))
        if not names:
            raise DwdWarningsError(f"no DISTRICT alert zip found at {self._base}")
        return names[-1]

    def fetch_alerts(self, *, warncell_ids: set[str] | None = None) -> list[NormalizedAlert]:
        raw = self._get(self._base + self.latest_zip_name())
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise DwdWarningsError(f"CAP feed zip is corrupt: {exc}") from exc
        alerts: list[NormalizedAlert] = []
        for member in zf.namelist():
            if not member.lower().endswith(".xml"):
                continue
            for alert in parse_cap_alerts(zf.read(member)):
                if warncell_ids is None or alert.warncell_id in warncell_ids:
                    alerts.append(alert)
        return alerts
