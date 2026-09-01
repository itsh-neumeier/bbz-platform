"""DWD radar / precipitation frame series (roadmap E18-03, ADR-0026).

Source: the DWD GeoServer WMS ``maps.dwd.de/geoserver/dwd/wms``, layer
``Radar_rv_product_1x1km_ger`` ("Deutsches Radarkomposit Analyse und Vorhersage
(RV)") — a 5-minute step series with an ISO8601 ``time`` dimension
(``<start>/<end>/PT5M``). We do **not** proxy the images: a frame is a
``GetMap`` **URL** the client fetches directly from DWD, clipped to the
Mittelfranken bounding box. The E18-06 refresh puts the series in the per-node
``weather_read.RADAR_CACHE``; E18-07 serves it.

``GetCapabilities`` is parsed with stdlib ``ElementTree``; the fetch is stdlib
``urllib`` in a worker thread — no new runtime dependency.
"""

from __future__ import annotations

import datetime as _dt
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from xml.etree import ElementTree as ET

DEFAULT_WMS_URL = "https://maps.dwd.de/geoserver/dwd/wms"
DEFAULT_LAYER = "Radar_rv_product_1x1km_ger"
#: minLon, minLat, maxLon, maxLat (WGS84) — the Mittelfranken clip
DEFAULT_BBOX: tuple[float, float, float, float] = (10.0, 48.9, 11.7, 49.8)
DEFAULT_FRAME_COUNT = 12
DEFAULT_SIZE = (512, 512)

_MAX_BYTES = 1 * 1024 * 1024
_TIMEOUT = 30
_STEP_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?$")


class DwdRadarError(RuntimeError):
    """A fetch or parse of the DWD radar WMS failed."""


@dataclass(frozen=True)
class RadarFrame:
    frame_time: _dt.datetime
    #: a ready-to-fetch WMS GetMap URL (PNG, transparent, clipped)
    image_ref: str

    def as_item(self) -> dict[str, object]:
        return {"frame_time": self.frame_time.isoformat(), "image_ref": self.image_ref}


def _parse_iso(value: str) -> _dt.datetime:
    parsed = _dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return parsed.astimezone(_dt.UTC) if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)


def parse_time_dimension(
    caps_xml: bytes | str, *, layer: str
) -> tuple[_dt.datetime, _dt.timedelta]:
    """Return ``(latest_frame_time, step)`` from the layer's ``time`` dimension
    (``<start>/<end>/PT..``). Raises if the layer or a usable interval is absent."""
    if isinstance(caps_xml, str):
        caps_xml = caps_xml.encode("utf-8")
    try:
        root = ET.fromstring(caps_xml)
    except ET.ParseError as exc:
        raise DwdRadarError(f"malformed WMS GetCapabilities: {exc}") from exc

    for lyr in root.iter():
        if not lyr.tag.endswith("Layer"):
            continue
        name = next((c.text for c in lyr if c.tag.endswith("Name")), None)
        if name != layer:
            continue
        for dim in lyr:
            if not dim.tag.endswith("Dimension") or dim.get("name") != "time" or not dim.text:
                continue
            spec = dim.text.strip().split(",")[-1]  # an interval, or a list → take the last item
            parts = spec.split("/")
            if len(parts) == 3:
                end, step = _parse_iso(parts[1]), _parse_step(parts[2])
                return end, step
            if len(parts) == 1:
                return _parse_iso(parts[0]), _dt.timedelta(minutes=5)
    raise DwdRadarError(f"no usable time dimension for layer {layer!r}")


def _parse_step(token: str) -> _dt.timedelta:
    m = _STEP_RE.match(token.strip())
    if not m:
        return _dt.timedelta(minutes=5)
    hours, minutes = int(m.group(1) or 0), int(m.group(2) or 0)
    return _dt.timedelta(hours=hours, minutes=minutes) or _dt.timedelta(minutes=5)


def build_frames(
    latest: _dt.datetime,
    step: _dt.timedelta,
    *,
    count: int,
    wms_url: str,
    layer: str,
    bbox: tuple[float, float, float, float],
    size: tuple[int, int],
) -> list[RadarFrame]:
    """The last ``count`` frame URLs, oldest → newest."""
    width, height = size
    base_params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": layer,
        "styles": "",
        "format": "image/png",
        "transparent": "true",
        "crs": "CRS:84",
        "bbox": ",".join(str(c) for c in bbox),
        "width": str(width),
        "height": str(height),
    }
    frames: list[RadarFrame] = []
    for i in range(count - 1, -1, -1):
        t = latest - step * i
        params = {**base_params, "time": t.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
        frames.append(
            RadarFrame(frame_time=t, image_ref=f"{wms_url}?{urllib.parse.urlencode(params)}")
        )
    return frames


class DwdRadarClient:
    """Transport only — reads GetCapabilities. The layer / bbox / size are
    per-call so a caller's config always wins over any default."""

    def __init__(self, wms_url: str = DEFAULT_WMS_URL, *, timeout: int = _TIMEOUT) -> None:
        self._wms = wms_url
        self._timeout = timeout

    def _get_capabilities(self) -> bytes:
        params = {"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"}
        url = f"{self._wms}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "bbz-platform/dwd"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data: bytes = resp.read(_MAX_BYTES * 8 + 1)
        except (OSError, ValueError) as exc:
            raise DwdRadarError(f"GET {url} failed: {exc}") from exc
        return data

    def frames(
        self,
        *,
        count: int = DEFAULT_FRAME_COUNT,
        layer: str = DEFAULT_LAYER,
        bbox: tuple[float, float, float, float] = DEFAULT_BBOX,
        size: tuple[int, int] = DEFAULT_SIZE,
    ) -> list[RadarFrame]:
        latest, step = parse_time_dimension(self._get_capabilities(), layer=layer)
        return build_frames(
            latest,
            step,
            count=max(1, count),
            wms_url=self._wms,
            layer=layer,
            bbox=bbox,
            size=size,
        )
