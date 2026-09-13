"""FastAPI application factory and console entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from market_intelligence import __version__
from market_intelligence.api.routes import router
from market_intelligence.config import get_settings
from market_intelligence.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="AI Infrastructure Market Intelligence API",
        summary="Citation-bearing normalized company evidence",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()


def run() -> None:
    """Run the API without development-only reload behavior."""

    uvicorn.run("market_intelligence.api.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
