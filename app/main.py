import base64
import io
import wave
import secrets
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from app.config import settings
from app.agent import graph

ROOT = Path(__file__).resolve().parent.parent
TTS_MODEL = 'gemini-2.5-flash-preview-tts'   # Gemini text-to-speech model

app = FastAPI(title='Medical Agent Educational API', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(','),
    allow_credentials=False,
    allow_methods=['GET', 'POST'],
    allow_headers=['Authorization', 'Content-Type', 'X-Conversation-ID'],
)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@lru_cache()
def gemini():
    # one shared Gemini client (timeout is in milliseconds)
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=45000),
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=10)
    image_data: str | None = None


def auth(authorization: str | None):
    tokens = settings.api_tokens
    if isinstance(tokens, str):
        tokens = [t.strip() for t in tokens.split(',') if t.strip()]
    if tokens and not any(
        secrets.compare_digest(authorization or '', f'Bearer {t}') for t in tokens
    ):
        raise HTTPException(status_code=401, detail='Invalid API token')


def inspect_image(data):
    if not data:
        return ''
    try:
        header, payload = data.split(',', 1)
        mime = header.split(';')[0].split(':')[1]
        raw = base64.b64decode(payload, validate=True)
        if mime not in ('image/jpeg', 'image/png', 'image/webp') or len(raw) > 5_000_000:
            raise ValueError('Only JPEG/PNG/WebP under 5MB supported')
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=f'Invalid image: {exc}')

    result = gemini().models.generate_content(
        model=settings.gemini_vision_model,
        contents=[
            types.Part.from_bytes(data=raw, mime_type=mime),
            'Describe only objectively visible medical-relevant features. '
            'Do not diagnose, estimate severity, or assert absence of illness. '
            'If image unclear, say so.',
        ],
        config=types.GenerateContentConfig(max_output_tokens=500),
    )
    return result.text or ''


@app.get('/', response_class=HTMLResponse)
def home():
    return (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')


@app.get('/api/health')
def health():
    return {
        'status': 'ok',
        'configured': bool(settings.gemini_api_key and settings.pinecone_api_key),
        'tavily': bool(settings.tavily_api_key),
    }


@app.post('/api/chat')
def chat(
    payload: ChatRequest,
    authorization: str | None = Header(default=None),
    conversation_id: str | None = Header(default=None, alias='X-Conversation-ID'),
):
    auth(authorization)

    if not settings.gemini_api_key or not settings.pinecone_api_key:
        raise HTTPException(503, 'Set GEMINI_API_KEY and PINECONE_API_KEY in .env')

    history = [
        x for x in payload.history
        if x.get('role') in ('user', 'assistant') and isinstance(x.get('content'), str)
    ][:10]

    # SQLite persistent memory: reuse the same conversation thread
    thread_id = conversation_id or str(uuid4())
    config = {'configurable': {'thread_id': thread_id}}

    try:
        observation = inspect_image(payload.image_data)

        state = graph.invoke(
            {
                'question': payload.message,
                'history': history,
                'image_description': observation,
                'kb': [],
                'web': [],
                'answer': '',
                'route': '',
            },
            config=config,
        )

        return {
            'answer': state['answer'],
            'sources': [{'type': 'pdf', 'page': x['page'], 'score': x['score']} for x in state['kb']]
                     + [{'type': 'web', 'url': x['url'], 'title': x['title']} for x in state['web']],
            'tools': ['pinecone']
                     + (['tavily'] if state['route'] == 'web' and settings.tavily_api_key else [])
                     + (['vision'] if observation else []),
            'conversation_id': thread_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print('Chat error:', repr(exc), flush=True)
        raise HTTPException(
            502,
            'AI service failed. Check server logs, credentials, Pinecone index, and connectivity.',
        )


@app.post('/api/transcribe')
async def transcribe(file: UploadFile = File(...), authorization: str | None = Header(default=None)):
    auth(authorization)
    data = await file.read(10_000_001)
    if len(data) > 10_000_000:
        raise HTTPException(413, 'Audio exceeds 10 MB')
    try:
        result = await gemini().aio.models.generate_content(
            model=settings.gemini_vision_model,   # Gemini models can listen to audio too
            contents=[
                types.Part.from_bytes(data=data, mime_type=file.content_type or 'audio/webm'),
                'Transcribe this audio exactly. Return only the spoken words, nothing else.',
            ],
        )
        return {'text': (result.text or '').strip()}
    except Exception as exc:
        print('Transcribe error:', repr(exc), flush=True)
        raise HTTPException(502, 'Speech transcription unavailable')


@app.post('/api/speak')
def speak(payload: dict, authorization: str | None = Header(default=None)):
    auth(authorization)
    text = str(payload.get('text', ''))[:3000]
    if not text:
        raise HTTPException(400, 'Missing text')
    try:
        result = gemini().models.generate_content(
            model=TTS_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=['AUDIO'],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Kore')
                    )
                ),
            ),
        )
        pcm = result.candidates[0].content.parts[0].inline_data.data

        # Gemini returns raw audio; wrap it as a WAV file so browsers can play it
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm)
        return Response(content=buf.getvalue(), media_type='audio/wav')
    except Exception as exc:
        print('Speak error:', repr(exc), flush=True)
        raise HTTPException(502, 'Speech synthesis unavailable')