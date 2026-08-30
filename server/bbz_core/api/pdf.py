"""A tiny dependency-free PDF writer for the optional event-export PDF (E20-06).

Not a general PDF library — it lays out pre-formatted text (the pretty-printed
JSON bundle) in Courier across Letter pages. It exists so the flag-gated PDF
export produces a genuine ``application/pdf`` without pulling in a rendering
dependency. ``render_text_pdf`` returns the file bytes.
"""

from __future__ import annotations

_PAGE_W, _PAGE_H = 612, 792  # US Letter, points
_MARGIN = 40
_FONT_SIZE = 8
_LEADING = 10
_LINES_PER_PAGE = (_PAGE_H - 2 * _MARGIN) // _LEADING
_MAX_COLS = 110


def _escape(text: str) -> str:
    out = text.encode("latin-1", "replace").decode("latin-1")
    return out.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(lines: list[str]) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        expanded = line.replace("\t", "    ")
        if not expanded:
            wrapped.append("")
        while len(expanded) > _MAX_COLS:
            wrapped.append(expanded[:_MAX_COLS])
            expanded = expanded[_MAX_COLS:]
        if expanded or not line:
            wrapped.append(expanded)
    return wrapped


def _content_stream(page_lines: list[str]) -> bytes:
    body = ["BT", f"/F1 {_FONT_SIZE} Tf", f"{_LEADING} TL", f"{_MARGIN} {_PAGE_H - _MARGIN} Td"]
    for i, line in enumerate(page_lines):
        if i:
            body.append("T*")
        body.append(f"({_escape(line)}) Tj")
    body.append("ET")
    return "\n".join(body).encode("latin-1", "replace")


def render_text_pdf(text: str) -> bytes:
    lines = _wrap(text.splitlines() or [""])
    pages = [lines[i : i + _LINES_PER_PAGE] for i in range(0, len(lines), _LINES_PER_PAGE)] or [
        [""]
    ]

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)  # 1-based object number

    font_no = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    page_nos: list[int] = []
    # reserve the /Pages object now (its /Kids need the page numbers), patch later
    pages_no = add(b"")
    for page_lines in pages:
        stream = _content_stream(page_lines)
        content_no = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        page_nos.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_no, _PAGE_W, _PAGE_H, font_no, content_no)
            )
        )
    kids = " ".join(f"{n} 0 R" for n in page_nos)
    objects[pages_no - 1] = f"<< /Type /Pages /Count {len(page_nos)} /Kids [{kids}] >>".encode(
        "latin-1"
    )
    catalog_no = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_no)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_no} 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF".encode("latin-1")
    )
    return bytes(out)
