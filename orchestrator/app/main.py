from fastapi import FastAPI
from .routes.content import router as content_router
from .database import engine, Base
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Orchestrator", lifespan=lifespan)
app.include_router(content_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
