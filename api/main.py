"""FastAPI entry point.

``load_dotenv`` is invoked here and NOWHERE else in the codebase.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# -- Environment load (must run before any service import) ------------------
load_dotenv()
os.environ["_MDF_DOTENV_LOADED"] = "1"

# ruff: noqa: E402 — imports below intentionally follow load_dotenv().
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.extractor import router as extractor_router
from core.config import get_settings
from core.sync import bootstrap


def create_app() -> FastAPI:
    settings = get_settings()
    bootstrap()  # logging + capability detection

    app = FastAPI(
        title="MDF Dictionary Extractor",
        description=(
            "Convert indigenous-language dictionary PDFs (Maya, Popoluca, "
            "Iskonawa, Zapoteco, Nahuatl, etc.) into structured MDF entries."
        ),
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.include_router(extractor_router)

    @app.get("/", include_in_schema=False)
    def _root() -> dict[str, str]:
        return {"service": "mdf-extractor", "env": settings.app_env.value}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env.value == "development",
    )
