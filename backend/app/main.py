"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from .core.errors import AppError, app_error_handler
from .routes.major import router as major_router
from .routes.recommend import router as recommend_router


app = FastAPI(title="PlaNU Backend")
app.add_exception_handler(AppError, app_error_handler)
app.include_router(major_router)
app.include_router(recommend_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

