"""Every self-built image must run as a non-root user (E23-08, SECURITY.md §22).

Static check: for each ``**/Dockerfile`` in the repo, the **effective** final
``USER`` (the last ``USER`` in the last build stage) must be present and resolve
to something other than root (``root`` / ``0`` / ``0:0``). A stage with no
``USER`` inherits root, so a multi-stage file must set it in the *runtime* stage.

The CI job also builds the image and ``docker inspect``s ``Config.User`` for the
real answer; this catches the mistake in review, before a build.

    python tools/security/check_dockerfiles.py         # exit 1 on any violation
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ROOT_USERS = {"", "root", "0", "0:0", "root:root"}
_SKIP = {".venv", "node_modules", ".git"}


def _stages(lines: list[str]) -> list[list[str]]:
    """Split a Dockerfile into build stages (each starting at a FROM)."""
    stages: list[list[str]] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("FROM "):
            stages.append([])
        if stages:
            stages[-1].append(line)
    return stages


def effective_user(text: str) -> str | None:
    """The USER the final stage runs as, or None if it never sets one."""
    stages = _stages(text.splitlines())
    if not stages:
        return None
    user: str | None = None
    for line in stages[-1]:
        if line.upper().startswith("USER "):
            user = line.split(None, 1)[1].strip().strip('"')
    return user


def violations(root: Path = _ROOT) -> list[str]:
    out: list[str] = []
    for path in sorted(root.rglob("Dockerfile*")):
        if any(part in _SKIP for part in path.parts) or not path.is_file():
            continue
        rel = path.relative_to(root)
        user = effective_user(path.read_text(encoding="utf-8"))
        if user is None:
            out.append(f"{rel}: no USER in the final stage — runs as root")
        elif user.lower() in _ROOT_USERS or user.split(":", 1)[0] in _ROOT_USERS:
            out.append(f"{rel}: final USER is {user!r} — must be non-root")
    return out


def main() -> int:
    found = violations()
    if found:
        print("Dockerfiles that would run as root:", file=sys.stderr)
        for v in found:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("all Dockerfiles run as a non-root user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
