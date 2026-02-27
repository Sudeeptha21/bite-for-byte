from uuid import uuid4
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.chat_service import handle_chat

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.post("")
def chat(req: ChatRequest):
    sid = req.session_id or str(uuid4())
    return handle_chat(sid, req.message)
