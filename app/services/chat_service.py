from app.services.food_pipeline import run_pipeline
from app.services.session_memory import get_history, add_turn


def handle_chat(session_id: str, message: str) -> dict:
    history = get_history(session_id)
    pipeline_result = run_pipeline(message)
    reply = pipeline_result.get("insight", "No response")

    add_turn(session_id, "user", message)
    add_turn(session_id, "assistant", reply)

    return {
        "session_id": session_id,
        "source": pipeline_result.get("source", "pipeline"),
        "history_size": len(history) + 2,
        "reply": reply,
    }
