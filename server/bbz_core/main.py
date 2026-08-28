"""Entrypoint for ``python -m bbz_core.main`` / container CMD."""

from __future__ import annotations

import uvicorn

from bbz_core.settings import get_settings


def main() -> None:
    s = get_settings()
    uvicorn.run(
        "bbz_core.app:app",
        host="0.0.0.0",
        port=8000,
        log_config=None,  # structlog owns logging
        reload=s.environment == "local",
    )


if __name__ == "__main__":
    main()
