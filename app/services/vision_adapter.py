import base64
from groq import Groq
from app.config import settings


client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


def answer_image_question(image_bytes: bytes, question: str) -> str:
    if not question.strip():
        return "Question is required"

    if not image_bytes:
        return "Image file is required"

    if not client:
        return "Vision unavailable: GROQ_API_KEY is missing"

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "You are an assistant for food and product understanding. "
        "Answer the user's image question clearly in 2-4 concise sentences. "
        "If uncertain, state uncertainty explicitly."
    )

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
            ],
        )
        return completion.choices[0].message.content or "No answer generated"
    except Exception as exc:
        return f"Vision error: {exc}"
