"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from .container import build_container
from .core.errors import AppError, app_error_handler, request_validation_error_handler
from .routes.catalog import router as catalog_router
from .routes.general import router as general_router
from .routes.major import router as major_router
from .routes.recommend import router as recommend_router
from .routes.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.container = build_container()
    yield


app = FastAPI(title="PlaNU Backend", lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_error_handler)
app.include_router(catalog_router)
app.include_router(general_router)
app.include_router(major_router)
app.include_router(recommend_router)
app.include_router(sessions_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
