# MedGuide AI — LangGraph + Gemini + Pinecone + FastAPI

An educational medical assistant. It answers questions using the *Gale Encyclopedia of Medicine* (2002, Volume 1, A–B) as its knowledge base, and can fall back to web search. It can also describe images and work with voice.

> **Educational use only.** This is a learning project. It is **not** a medical device, it does **not** diagnose, and it must not replace advice from a doctor. If you think you have a medical emergency, contact your local emergency services.

---

## Features

- **Book search (RAG):** finds the most relevant pages of the medical book in Pinecone and uses them to answer.
- **Web search fallback:** if the book does not have the answer, it can search the web with Tavily (optional).
- **Image observations:** describes what is visibly in a photo using Gemini. It does not diagnose.
- **Voice:** speech-to-text and text-to-speech, both through Gemini.
- **Conversation memory:** chats are saved per conversation in a local SQLite file.
- **Simple web page:** plain HTML, CSS and JavaScript, no frontend framework.

## How it works

```
Your question
     │
     ▼
 Retrieve  ──►  search the book in Pinecone (Gemini embeddings)
     │
     ▼
  Route    ──►  is the book answer enough?
     │                │
     │ no             │ yes
     ▼                │
  Tavily web search   │
     │                │
     └──────► Answer (Gemini) ◄──┘
```

## Tech stack

| Part | Tool |
|---|---|
| Web server | FastAPI + Uvicorn |
| AI model, embeddings, vision, speech | Google Gemini (`google-genai`, `langchain-google-genai`) |
| Agent flow | LangGraph (with SQLite memory) |
| Vector database | Pinecone (serverless) |
| Web search | Tavily |
| PDF reading | PyMuPDF |

## Requirements

- Python 3.11 or 3.12
- API keys for **Gemini**, **Pinecone** and (optionally) **Tavily**
- The book PDF placed at `data/medical_book.pdf` (you must supply your own copy)
- An internet connection

## Setup

**1. Create a virtual environment and install packages**

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Create a `.env` file** in the project folder:

```env
GEMINI_API_KEY=your-gemini-key
PINECONE_API_KEY=your-pinecone-key
TAVILY_API_KEY=your-tavily-key        # optional

PINECONE_INDEX=medical-gemini         # use a NEW index name for Gemini
GEMINI_EMBED_MODEL=gemini-embedding-001
GEMINI_VISION_MODEL=gemini-2.5-flash

ALLOWED_ORIGINS=http://127.0.0.1:8080,http://localhost:8080
API_TOKENS=                           # optional; leave empty while testing
```

> Check `app/config.py` for the exact setting names and the default models your code uses.

**3. Load the book into Pinecone (run once)**

```bash
python ingest.py --pdf data/medical_book.pdf
```

- The Pinecone index uses **3072 dimensions** (the size of the Gemini embeddings). Always use a **fresh index** when you change the embedding model.
- This step makes many embedding calls. On the free Gemini tier you may see `Error 429, retrying in 65s`. That is normal: the script waits and tries again. A 634-page book can take a while.

**4. Start the server**

```bash
uvicorn app.main:app --reload --port 8080
```

Open **http://127.0.0.1:8080**.
API documentation: **http://127.0.0.1:8080/docs**
Configuration check: **http://127.0.0.1:8080/api/health**

## Quick test without the web page

```bash
python test.py
```

This sends a sample question ("what is headache?") straight to the agent and prints the result.

## Project structure

```
app/
  config.py       settings and environment variables
  knowledge.py    Gemini embeddings + Pinecone search
  agent.py        LangGraph flow: retrieve → route → web search → answer
  main.py         FastAPI app: chat, image, speech endpoints
ingest.py         reads the PDF, splits it, embeds it, uploads to Pinecone
run.py            helper to start the server
test.py           quick test of the agent
templates/        index.html (the page)
static/           style.css, app.js
data/             medical_book.pdf (not included)
```

## API endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/` | the web page |
| GET | `/api/health` | shows whether keys are configured |
| POST | `/api/chat` | main chat (text, optional image) |
| POST | `/api/transcribe` | speech to text |
| POST | `/api/speak` | text to speech (returns WAV audio) |

If `API_TOKENS` is set, send the header `Authorization: Bearer <token>`. Use `X-Conversation-ID` to continue the same conversation.

## Troubleshooting

| Problem | What to try |
|---|---|
| `500` on `/api/chat`, browser only says "Request failed" | Look at the **terminal running the server**. The real error and traceback are printed there. Make sure you open the same port the server is using. |
| `Errno 10048` / port already in use | An old server is still running. Stop it with `Ctrl + C`, or use `netstat -ano \| findstr :8080` then `taskkill /PID <number> /F`, or choose another port. |
| Code changes do not show up | Restart the server, or start it with `--reload`. |
| `Error 429` during ingest | Gemini rate limit. The script retries by itself. Use smaller batches, or a paid plan. |
| `'module' object is not callable` | Use `genai.Client(api_key=...)`. `genai` is a module and cannot be called. |
| Search returns nothing or dimension errors | The Pinecone index size must match the embedding model (3072 here). Re-run `ingest.py` on a fresh index. |
| `401 Invalid API token` | Either clear `API_TOKENS` in `.env`, or send the matching `Authorization: Bearer ...` header. |
| Camera or microphone does not work | Allow browser permissions. Use `localhost` or HTTPS. |
| Tavily search missing | Add `TAVILY_API_KEY`. Without it, web search is switched off. |

## Safety and privacy

- **Never commit** your `.env` file. Make sure it is listed in `.gitignore`.
- **Do not commit** the chat memory files (`medical_memory.db`, `.db-shm`, `.db-wal`). They can contain conversations. Add `*.db`, `*.db-shm` and `*.db-wal` to `.gitignore`.
- The book is from 2002 and may contain **out-of-date medical advice**.
- Images can be described but can never confirm or rule out a disease.
- Do not send real patient information to third-party APIs without proper consent and agreements.
- Before any real-world use you would need: proper user login, encrypted storage, request limits, clinical review of the answers, emergency-case handling, a license check for the PDF, and a privacy and legal review.

## License

Apache-2.0. See the `LICENSE` file.
