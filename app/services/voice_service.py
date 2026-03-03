import base64
from io import BytesIO
from groq import Groq
from app.config import settings


try:
    from gtts import gTTS
except ImportError:
    gTTS = None


client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


def transcribe_audio(file_bytes: bytes, filename: str = "audio.wav") -> str:
    if not client:
        return "STT unavailable: GROQ_API_KEY is missing"

    try:
        result = client.audio.transcriptions.create(
            file=(filename, file_bytes),
            model="whisper-large-v3",
        )
        text = getattr(result, "text", "")
        return text or "No speech detected"
    except Exception as exc:
        return f"STT error: {exc}"


def synthesize_speech(text: str) -> tuple[str, str]:
    if not text.strip():
        return "", "audio/mpeg"

    if not gTTS:
        return "", "audio/mpeg"

    try:
        fp = BytesIO()
        gTTS(text=text, lang="en").write_to_fp(fp)
        audio_bytes = fp.getvalue()
        return base64.b64encode(audio_bytes).decode("utf-8"), "audio/mpeg"
    except Exception:
        return "", "audio/mpeg"
