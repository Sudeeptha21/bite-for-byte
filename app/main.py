from fastapi import FastAPI
from app.db import init_schema
from app.middleware.metrics import MetricsMiddleware
from app.routes.chat import router as chat_router
from app.routes.voice import router as voice_router
from app.routes.image import router as image_router
from app.routes.admin import router as admin_router

app = FastAPI(title="good-ai-analytics", version="0.1.0")
app.add_middleware(MetricsMiddleware)


@app.on_event("startup")
def startup_init():
    try:
        init_schema()
    except Exception:
        # Keep API booting even if DB is temporarily unavailable.
        pass


app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(image_router)
app.include_router(admin_router)


@app.get("/")
def health():
    return {"status": "ok"}
