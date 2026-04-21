# MDF Dictionary Extractor

Convert printed **indigenous-language dictionary PDFs** (Maya, Popoluca,
Iskonawa, Zapotec, Nahuatl, and related families) into structured
[Machine-Readable Dictionary Format](https://software.sil.org/toolbox/) (MDF)
entries using multi-provider LLMs (OpenAI, Anthropic, Google Gemini, Mistral),
with an automatic Tesseract OCR fallback for scanned documents.

> A full walkthrough — architecture, data flow, MDF tag reference, API
> contract, configuration, development workflow — lives in
> [**GUIDE.md**](./GUIDE.md).

---

## Authors

- **Hernandez Villarreal Juan Manuel**
- **Corona Alvarado Jesus Daniel**

---

## What it does

Given a dictionary PDF, the system:

1. **Detects** whether the document is text-based, image-based, or mixed
   by sampling pages and measuring character density.
2. **Extracts** text page by page with PyMuPDF, falling back to Tesseract
   OCR automatically when native extraction yields nothing usable.
3. **Structures** each page into MDF lexical entries through a LangGraph
   agent that enforces a strict Pydantic schema. Every textual field is
   tagged with an `ai_generated` provenance flag so inferred values are
   auditable.
4. **Prices** the job up-front: the `/quote` endpoint returns a
   cheapest-first ranking of every LLM whose API key is configured.
5. **Returns** a single JSON document with metadata, entries, warnings,
   and per-page error reports.

---

## Project layout

```
mdf/
├── api/                     FastAPI backend (Python 3.12)
│   ├── api/routes/          HTTP route handlers
│   ├── core/                Configuration + bootstrap
│   ├── schemas/             Pydantic models (MDF + endpoint contracts)
│   ├── services/            PDF extractor, LLM router, LangGraph agent
│   ├── tests/               Pytest suite
│   ├── main.py              ASGI entry point
│   ├── Dockerfile
│   └── requirements.txt
├── web/                     React 19 + TypeScript + Vite SPA
│   ├── src/components/      UI components
│   ├── src/types.ts         Shared API types
│   ├── Dockerfile           Multi-stage (Node build → Nginx serve)
│   └── nginx.conf
├── docker-compose.yml       Full stack (api + web)
├── GUIDE.md                 Technical + practical guide
└── README.md
```

---

## Quickstart (Docker)

The fastest path: one compose file, both services, Tesseract preinstalled.

```bash
# 1. Configure secrets
cp api/.env.example api/.env
# edit api/.env and fill in at least one of:
#   OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, MISTRAL_API_KEY

# 2. Build and start the stack
docker compose up --build
```

Once the stack is healthy:

- **Web UI** — http://localhost:8080
- **API** — http://localhost:8000
- **Interactive docs (Swagger)** — http://localhost:8000/docs
- **Health** — http://localhost:8000/api/v1/health

Stop the stack with `docker compose down`.

---

## Quickstart (local, no Docker)

### Backend

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # fill in at least one API key
python main.py                             # uvicorn with reload in development
```

OCR fallback requires a local `tesseract` binary. On Debian/Ubuntu:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng
```

### Frontend

```bash
cd web
pnpm install
pnpm dev                                   # http://localhost:5173
```

The dev server reads `VITE_API_BASE_URL` from `web/.env` (defaults to
`http://localhost:8000`).

---

## API endpoints (at a glance)

| Method | Path               | Purpose                                          |
|--------|--------------------|--------------------------------------------------|
| GET    | `/api/v1/health`   | Providers + OCR capability snapshot              |
| GET    | `/api/v1/models`   | List LLM models enabled by the configured keys   |
| POST   | `/api/v1/quote`    | Estimate extraction cost across models           |
| POST   | `/api/v1/extract`  | Upload a PDF and receive MDF JSON                |

Full request/response schemas are documented in [GUIDE.md](./GUIDE.md#api-reference)
and interactively at `/docs`.

---

## Configuration

Every knob is an environment variable read by `api/core/config.py`.
Start from `api/.env.example`; the most relevant ones are:

| Variable                         | Default          | Purpose                                         |
|----------------------------------|------------------|-------------------------------------------------|
| `APP_ENV`                        | `development`    | `development` enables uvicorn auto-reload       |
| `APP_PORT`                       | `8000`           | Backend port                                    |
| `MAX_UPLOAD_MB`                  | `50`             | Hard cap on uploaded PDF size                   |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `MISTRAL_API_KEY` | *(empty)* | Only providers with a key are exposed |
| `TESSERACT_CMD`                  | *(auto)*         | Override if tesseract is not on `$PATH`         |
| `OCR_LANGUAGES`                  | `spa+eng`        | Tesseract language packs to load                |
| `AGENT_MAX_RETRIES`              | `2`              | Per-page retries on schema validation failure   |
| `AGENT_MAX_CONCURRENCY`          | `5`              | Parallel LLM calls across pages                 |

See [`api/.env.example`](./api/.env.example) for the full list.

---

## Tech stack

- **Backend** — FastAPI · Pydantic v2 · PyMuPDF · pytesseract · LangChain ·
  LangGraph · tiktoken · httpx.
- **Frontend** — React 19 · TypeScript · Vite 8 · Tailwind CSS 4 · Motion ·
  React Icons.
- **Infrastructure** — Docker · Nginx · Tesseract OCR (spa + eng).

---

## License

See [LICENSE](./LICENSE).
