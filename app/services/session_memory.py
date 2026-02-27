from collections import defaultdict

_memory = defaultdict(list)


def get_history(session_id: str):
    return _memory[session_id]


def add_turn(session_id: str, role: str, content: str):
    _memory[session_id].append({"role": role, "content": content})
