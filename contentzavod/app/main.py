from fastapi import FastAPI
from .routes.generate import router

app = FastAPI(title="ContentZavod")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
