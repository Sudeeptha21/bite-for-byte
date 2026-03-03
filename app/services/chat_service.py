from app.config import settings
from app.services.food_pipeline import run_pipeline
from app.services.session_memory import get_history, add_turn


FOLLOW_UP_HINTS = (
    "it",
    "its",
    "this",
    "that",
    "same",
    "also",
    "what about",
)

GREETING_MESSAGES = {
    "hi",
    "hii",
    "hello",
    "hey",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
}

SMALL_TALK_MESSAGES = {
    "how are you",
    "how are you?",
    "what's up",
    "whats up",
}


def _simple_chat_reply(message: str) -> str | None:
    lower = " ".join(message.lower().strip().split())
    if lower in GREETING_MESSAGES:
        return "Hi! I can help with food analysis, nutrition questions, and product insights."
    if lower in SMALL_TALK_MESSAGES:
        return "I am doing well. Ask me about a food item, meal, or nutrition goal and I will help."
    return None


def _last_user_product(history: list[dict]) -> str | None:
    for turn in reversed(history):
        if turn.get("role") == "user" and turn.get("content"):
            return turn["content"]
    return None


def _resolve_query(history: list[dict], message: str) -> str:
    lower = message.lower().strip()
    if any(hint in lower for hint in FOLLOW_UP_HINTS):
        last_user = _last_user_product(history)
        if last_user and last_user.lower() != lower:
            return f"{last_user}. Follow-up question: {message}"
    return message


def handle_chat(session_id: str, message: str) -> dict:
    history = get_history(session_id)
    resolved_query = _resolve_query(history, message)

    simple_reply = _simple_chat_reply(message)
    if simple_reply is not None:
        reply = simple_reply
        source = "small_talk"
    else:
        pipeline_result = run_pipeline(resolved_query)
        reply = pipeline_result.get("insight", "No response")
        source = pipeline_result.get("source", "pipeline")

    add_turn(session_id, "user", message)
    add_turn(session_id, "assistant", reply)

    return {
        "session_id": session_id,
        "session_ttl_seconds": settings.SESSION_TTL_SECONDS,
        "source": source,
        "history_size": len(history) + 2,
        "reply": reply,
    }
