FROM python:3.11-slim AS base

# System dependencies + Node.js 22 LTS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g pnpm@9 \
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
COPY assets/ assets/
COPY src/ src/

EXPOSE 7860

CMD ["uv", "run", "uvicorn", "bilingualsub.api.app:app", "--host", "0.0.0.0", "--port", "7860"]
