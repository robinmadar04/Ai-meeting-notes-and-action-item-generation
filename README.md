# Commonroom — AI Meeting Notes & Action Items

A local-first meeting workspace that turns text transcripts and TXT, PDF, and DOCX documents into editable meeting notes using NVIDIA NIM. Meeting records and action items persist in a relational database and export to PDF.

## Features

- Paste a transcript or upload TXT, text-based PDF, or DOCX (up to 10 MB).
- Generate grounded summaries, discussion points, explicit decisions, action items, owners, dates, and evidence using a backend-only NVIDIA API call.
- Edit titles, summaries, task fields, priorities, and statuses; add or delete tasks.
- Search saved meetings by title, summary, transcript, and task content with database pagination.
- Download a wrapped, printable PDF report.
- Dashboard and meeting archive.

## Stack

- React, Vite, TypeScript, React Router, custom responsive CSS.
- Python, FastAPI, Pydantic, SQLAlchemy, Alembic.
- SQLite for a zero-setup local development database; PostgreSQL is supported by configuring `DATABASE_URL` and installing the included psycopg driver.
- NVIDIA hosted NIM chat completions API.

## Setup

Prerequisites: Python 3.11+ and Node.js 20+.

1. Configure the backend from the repository root:

   ```powershell
   Copy-Item .env.example backend/.env
   # Edit backend/.env and set NVIDIA_API_KEY to your NVIDIA API key.
   cd backend
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```

2. In a second terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Open http://localhost:5173. FastAPI's interactive API documentation is at http://localhost:8000/docs. The frontend uses `VITE_API_URL` when set, otherwise `http://localhost:8000/api`.

## NVIDIA configuration

The backend calls `POST https://integrate.api.nvidia.com/v1/chat/completions` with Bearer authentication and the OpenAI-compatible messages payload. The default model is `nvidia/nemotron-3.5-lightning-30b-a3b`; NVIDIA currently lists it with a 1M token context and a hosted free endpoint. NVIDIA documents `max_tokens`, `reasoning_budget`, and request polling for `202 Accepted` responses. Hosted endpoint availability and quotas can depend on NVIDIA's current terms and the user's account. Set `NVIDIA_MODEL` to another available model if access differs. This implementation requests JSON in the prompt, validates the result with Pydantic, and makes one bounded retry for invalid output, rate limits, transient server failures, and timeouts. It does not fallback to another provider. The key is never sent to the browser.

Official references: [Nemotron 3.5 Lightning chat completions API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer), [Nemotron 3.5 Lightning model page](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b?nim=self-hosted), and [NVIDIA model catalog](https://build.nvidia.com/explore/discover).

## Database and migrations

The default SQLite database file is `backend/meetings.db`. To use PostgreSQL, create an empty database and set a SQLAlchemy URL such as `postgresql+psycopg://user:password@localhost:5432/meeting_notes` in `backend/.env`. Apply schema changes with `alembic upgrade head`; reverse the initial migration with `alembic downgrade base`. The schema uses JSON fields for generated discussion/decision lists and relational action item rows with cascading foreign keys.

This MVP has no authentication: records are shared by anyone with access to this running application instance. Do not expose it publicly with sensitive meeting content without adding authentication and access controls.

## Upload limits and known limitations

- Scanned/image-only PDFs are detected and rejected with an OCR message; OCR is not bundled.
- Relative deadlines are normalized only when unambiguous with the supplied meeting date; otherwise the model is asked to return null.
- No live NVIDIA call is made by automated tests. NVIDIA key, model entitlement, rate limits, and trial eligibility depend on the user's account; verify them from NVIDIA's service before deployment.
- The app is an unauthenticated single-instance MVP and requires network access to load the optional Google Fonts stylesheet; it falls back to system sans-serif fonts.

## Development and checks

Backend: `cd backend; uvicorn app.main:app --reload --port 8000`

Frontend: `cd frontend; npm run dev`

Frontend production build: `cd frontend; npm run build`

Backend tests: `cd backend; pytest`

