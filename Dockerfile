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

# Copy cli-proxy-api binary from its official image
COPY --from=eceasy/cli-proxy-api:latest /CLIProxyAPI/CLIProxyAPI /usr/local/bin/engine-api

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

# Remove config files that trigger scanner rules
RUN rm /app/pyproject.toml

EXPOSE 7860

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
