FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    nodejs \
    npm \
    && npm install -g pnpm \
    && curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
       -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Python dependencies
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen

# Build frontend
COPY frontend/ frontend/
RUN cd frontend && pnpm install --frozen-lockfile && pnpm build

# Copy source
COPY src/ src/

EXPOSE 7860

CMD ["uv", "run", "uvicorn", "bilingualsub.api.app:app", "--host", "0.0.0.0", "--port", "7860"]
