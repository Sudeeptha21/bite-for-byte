# good-ai-analytics

Multi-modal AI assistant platform with chat, voice (STT/TTS), image Q&A, barcode scanning, session memory, and a basic admin metrics dashboard.

## Architecture (v1)

1. Frontend
- Chat UI: text, image upload, mic input, speaker output
- Admin UI: basic usage metrics

2. API
- `POST /chat`
- `POST /voice/stt`
- `POST /voice/tts`
- `POST /image/qa`
- `POST /image/barcode`
- `GET /admin/metrics`

3. Services
- LLM adapter
- Vision adapter
- Voice service
- Barcode service
- Food pipeline service
- Session memory service

4. Data
- Redis for session-only memory
- Postgres for analytics + logs

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
