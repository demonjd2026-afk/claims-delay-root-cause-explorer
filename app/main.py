"""Application entry point: API plus the static dashboard."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.data.store import get_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    store = get_store()  # builds the data on first run, then loads it once
    logging.getLogger("cde").info("loaded %s claims, as of %s", f"{len(store.claims):,}", store.as_of.date())
    yield


app = FastAPI(title="Claims Delay Root-Cause Explorer", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(settings.web_dir / "index.html")


app.mount("/", StaticFiles(directory=settings.web_dir), name="web")
