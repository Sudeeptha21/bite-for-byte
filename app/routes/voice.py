from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from app.services.voice_service import transcribe_audio, synthesize_speech

router = APIRouter(prefix="/voice", tags=["voice"])


class TTSRequest(BaseModel):
    text: str


@router.post("/stt")
async def stt(file: UploadFile = File(...)):
    data = await file.read()
    return {"text": transcribe_audio(data)}


@router.post("/tts")
def tts(req: TTSRequest):
    audio = synthesize_speech(req.text)
    return {"audio_bytes": len(audio)}
