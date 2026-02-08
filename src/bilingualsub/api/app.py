"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from bilingualsub.api.errors import ApiError
from bilingualsub.api.jobs import JobManager
from bilingualsub.api.logging import setup_logging
from bilingualsub.api.routes import router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: setup/teardown."""
    setup_logging()
    manager = JobManager()
    app.state.job_manager = manager
    await manager.start_cleanup_loop()
    yield
    await manager.stop_cleanup_loop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BilingualSub",
        description="YouTube bilingual subtitle generator",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global error handler
    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    # API routes
    app.include_router(router)

    # Serve frontend static files if built
    frontend_dist = (
        Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
    )
    if frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="static",
        )

    return app


app = create_app()
