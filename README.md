# BilingualSub

[English](README.md) | [繁體中文](README.zh-TW.md)

[![CI](https://github.com/Mapleeeeeeeeeee/bilingualsub/actions/workflows/ci.yml/badge.svg)](https://github.com/Mapleeeeeeeeeee/bilingualsub/actions/workflows/ci.yml) [![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)

Automated bilingual subtitle generator for YouTube videos with high-quality LLM translation.

## Features

- Download YouTube videos with yt-dlp
- Automatic speech recognition using Groq Whisper (whisper-large-v3-turbo)
- High-quality LLM translation via Agno framework (default: groq:openai/gpt-oss-120b)
- Bilingual subtitle output in SRT and ASS formats
- Optional subtitle burn-in with hardware acceleration (VideoToolbox on macOS)
- Real-time progress tracking via SSE
- Web-based UI with i18n support (English/繁體中文)
- Job-based async architecture with in-memory storage

## Quick Start

### Docker (Recommended)

```bash
docker build -t bilingualsub . && docker run -p 7860:7860 -e GROQ_API_KEY=your_key_here bilingualsub
```

Then open http://localhost:7860 in your browser.

### Local Development

**Prerequisites**: Python 3.11+, FFmpeg, Node.js 18+, pnpm

```bash
# 1. Install backend dependencies
uv sync --dev --extra e2e

# 2. Install frontend dependencies
cd frontend && pnpm install

# 3. Start backend server (in one terminal)
uv run uvicorn bilingualsub.api.app:create_app --factory --reload

# 4. Start frontend dev server (in another terminal)
cd frontend && pnpm dev
```

Backend runs at http://localhost:8000, frontend at http://localhost:5173.

## Configuration

| Environment Variable   | Description                                    | Default                    | Required |
| ---------------------- | ---------------------------------------------- | -------------------------- | -------- |
| `GROQ_API_KEY`         | Groq API key for Whisper transcription         | -                          | Yes      |
| `OPENAI_API_KEY`       | OpenAI API key (only if using OpenAI provider) | -                          | No       |
| `TRANSCRIBER_PROVIDER` | Transcription provider                         | `groq`                     | No       |
| `TRANSCRIBER_MODEL`    | Whisper model to use                           | `whisper-large-v3-turbo`   | No       |
| `TRANSLATOR_MODEL`     | LLM model for translation                      | `groq:openai/gpt-oss-120b` | No       |

## Architecture

```
YouTube URL → Download (yt-dlp) → Extract Audio (FFmpeg) → Transcribe (Groq Whisper) →
Translate (LLM via Agno) → Bilingual Subtitles (SRT/ASS) → Optional Burn-in (FFmpeg)
```

**Backend**: FastAPI with job-based async architecture. Jobs are created via `POST /api/jobs`, processed in the background, and stream progress updates through `GET /api/jobs/{id}/events` using Server-Sent Events (SSE). Job data is stored in-memory with a 30-minute TTL.

**Frontend**: React SPA built with Vite 7. State management via `useJob` hook (idle → submitting → processing → completed/failed). API communication handled by `ApiClient` singleton with REST and SSE support. Internationalization via i18next.

## Tech Stack

| Backend              | Frontend       |
| -------------------- | -------------- |
| FastAPI              | Vite 7         |
| Python 3.11+         | React 19       |
| yt-dlp               | TypeScript 5.9 |
| FFmpeg               | Tailwind CSS 4 |
| Groq Whisper         | i18next        |
| Agno (LLM framework) | pnpm           |

## License

[Apache License 2.0](LICENSE)
