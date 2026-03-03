import json
import time
from collections import defaultdict
from app.config import settings

try:
    import redis
except ImportError:
    redis = None


_memory = defaultdict(list)
_memory_expiry = {}
_redis_client = None

if redis:
    try:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _redis_client.ping()
    except Exception:
        _redis_client = None


def _redis_key(session_id: str) -> str:
    return f"session:{session_id}:history"


def _purge_if_expired(session_id: str):
    exp = _memory_expiry.get(session_id)
    if exp and time.time() > exp:
        _memory.pop(session_id, None)
        _memory_expiry.pop(session_id, None)


def get_history(session_id: str):
    if _redis_client:
        rows = _redis_client.lrange(_redis_key(session_id), 0, -1)
        history = []
        for item in rows:
            try:
                history.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        return history

    _purge_if_expired(session_id)
    return _memory[session_id]


def add_turn(session_id: str, role: str, content: str):
    turn = {"role": role, "content": content}
    if _redis_client:
        key = _redis_key(session_id)
        _redis_client.rpush(key, json.dumps(turn))
        _redis_client.expire(key, settings.SESSION_TTL_SECONDS)
        return

    _purge_if_expired(session_id)
    _memory[session_id].append(turn)
    _memory_expiry[session_id] = time.time() + settings.SESSION_TTL_SECONDS
