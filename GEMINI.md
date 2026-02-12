# BilingualSub - Project Context

## Project Overview

**BilingualSub** is an automated tool for generating bilingual subtitles for YouTube videos. It leverages **yt-dlp** for downloading, **Faster-Whisper** for speech-to-text, and high-quality LLMs (GPT-4o, Gemini, Claude) for translation. The final output can be SRT/ASS subtitle files or a video with burned-in subtitles.

### Tech Stack

- **Backend:** Python 3.11+ (FastAPI), AsyncIO, `uv` (dependency management).
- **Frontend:** React 19, Vite 7, TypeScript 5.9, Tailwind CSS 4.
- **Core Libraries:** `yt-dlp`, `ffmpeg-python`, `groq`, `agno`, `pydantic`.
- **Testing:** `pytest` (Unit, Integration, E2E w/ Playwright).

## Architecture

### Backend (FastAPI)

The backend operates on an asynchronous, job-based architecture:

1.  **Job Creation:** `POST /api/jobs` initiates a processing job.
2.  **Pipeline:**
    - `Download` (yt-dlp)
    - `Trim` (optional)
    - `Extract Audio`
    - `Transcribe` (Whisper)
    - `Translate` (LLM)
    - `Merge/Serialize` (SRT/ASS)
    - `Burn-in` (FFmpeg)
3.  **State Management:** In-memory job store (`TTL=30m`). Clients receive progress updates via SSE (`/api/jobs/{id}/events`).

### Frontend (React)

- **State Machine:** Uses a custom `useJob` hook to manage states: `idle` -> `submitting` -> `processing` -> `completed` / `failed`.
- **Communication:** `ApiClient` handles REST requests and Server-Sent Events (SSE).
- **UI:** Tailwind CSS v4 for styling.

## Getting Started

### Prerequisites

- Python >= 3.11
- Node.js & pnpm
- FFmpeg installed on system
- `uv` (Python package manager)

### Backend Setup

```bash
# Install dependencies
uv sync --dev --extra e2e

# Run development server
uv run uvicorn bilingualsub.api.app:create_app --factory --reload
```

### Frontend Setup

```bash
cd frontend
pnpm install
pnpm dev
```

### Docker

```bash
docker build -t bilingualsub .
```

## Development Workflow & Conventions

### Code Style & Quality

This project enforces strict code quality standards. Ensure all checks pass before committing.

- **Linting & Formatting (Python):**
  ```bash
  uv run ruff check src/ tests/
  uv run ruff format src/ tests/
  ```
- **Type Checking:**
  ```bash
  uv run mypy src/
  ```
- **Dead Code Detection:**
  ```bash
  uv run vulture src/bilingualsub --min-confidence=80
  ```
- **Frontend Linting:**
  ```bash
  cd frontend && pnpm lint
  # Prettier checks (if configured)
  npx prettier --check "**/*.{js,jsx,ts,tsx,json,yaml,md}"
  ```

### Testing

Testing is divided into three categories. Coverage must be >= 80%.

- **Unit Tests:** Fast, mocked dependencies.
  ```bash
  uv run pytest tests/unit -m unit
  ```
- **Integration Tests:** May use real dependencies.
  ```bash
  uv run pytest tests/integration -m integration
  ```
- **End-to-End (E2E) Tests:** Full workflow using Playwright.
  ```bash
  uv run playwright install chromium
  uv run pytest tests/e2e -m e2e
  ```

### Directory Structure

- `src/bilingualsub`: Main application package.
  - `api/`: FastAPI routes and schemas.
  - `core/`: Core logic (downloader, transcriber, etc.).
  - `formats/`: Subtitle format handling (SRT, ASS).
- `frontend/`: React application.
- `tests/`: Test suite mirroring the source structure.
- `.claude/hooks`: Quality gate scripts (useful reference for required checks).

## Important Constraints

- **TypeScript:** `enum` is forbidden due to `erasableSyntaxOnly: true`. Use `as const` + companion types instead.
- **Async:** Blocking operations in the backend must be wrapped in `asyncio.to_thread()`.
