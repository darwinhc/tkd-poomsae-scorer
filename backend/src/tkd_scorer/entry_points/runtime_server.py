from __future__ import annotations

from typing import NoReturn

import uvicorn

from tkd_scorer.infra.config.settings import get_settings


def _fatal(message: str) -> NoReturn:
    print("")
    print("SERVER STARTUP ERROR")
    print(message)
    print("")
    raise SystemExit(1)


def main() -> None:
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - startup failure path
        _fatal(str(exc))

    try:
        from tkd_scorer.entry_points.fastapi.app import app
    except Exception as exc:  # pragma: no cover - startup failure path
        _fatal(str(exc))

    try:
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            proxy_headers=settings.admin_trust_proxy_headers,
        )
    except OSError as exc:  # pragma: no cover - startup failure path
        _fatal(f"Could not start the server (host/port): {exc}")
    except Exception as exc:  # pragma: no cover - startup failure path
        _fatal(f"Unexpected error while starting the server: {exc}")


if __name__ == "__main__":
    main()
