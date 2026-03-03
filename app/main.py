from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from app.db import init_schema
from app.middleware.metrics import MetricsMiddleware
from app.routes.chat import router as chat_router
from app.routes.voice import router as voice_router
from app.routes.image import router as image_router
from app.routes.admin import router as admin_router

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="food-ai-analytics", version="0.1.0")
app.add_middleware(MetricsMiddleware)


@app.on_event("startup")
def startup_init():
    try:
        init_schema()
    except Exception:
        pass


app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(image_router)
app.include_router(admin_router)


@app.get("/")
def health():
    return {"status": "ok", "ui": "/ui"}


@app.get("/ui")
def chat_ui():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin-ui")
def admin_ui():
    return FileResponse(FRONTEND_DIR / "admin.html")

@app.post("/chat")
def chat_endpoint(message: str, session_id: str):
    from app.services.chat_service import handle_chat

    return handle_chat(session_id, message)

@app.post("/voice/stt")
def stt_endpoint(file: bytes):
    from app.services.voice_service import transcribe_audio

    return {"text": transcribe_audio(file)}

@app .post("/image/barcode")
def barcode_endpoint(image: bytes):
    from app.services.barcode_service import scan_barcode

    return scan_barcode(image)

