from collections import defaultdict
from app.config import settings

try:
    import redis
except ImportError:
    redis = None


_memory = defaultdict(list)
_redis_client = None

if redis:
    try:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _redis_client.ping()
    except Exception:
        _redis_client = None


def _redis_key(session_id: str) -> str:
    return f"session:{session_id}:history"


def get_history(session_id: str):
    if _redis_client:
        rows = _redis_client.lrange(_redis_key(session_id), 0, -1)
        return [eval(item) for item in rows]
    return _memory[session_id]


def add_turn(session_id: str, role: str, content: str):
    turn = {"role": role, "content": content}
    if _redis_client:
        key = _redis_key(session_id)
        _redis_client.rpush(key, str(turn))
        _redis_client.expire(key, settings.SESSION_TTL_SECONDS)
        return
    _memory[session_id].append(turn)
