# BilingualSub

[English](README.md) | [繁體中文](README.zh-TW.md)

[![CI](https://github.com/Mapleeeeeeeeeee/bilingualsub/actions/workflows/ci.yml/badge.svg)](https://github.com/Mapleeeeeeeeeee/bilingualsub/actions/workflows/ci.yml) [![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)

YouTube 影片雙語字幕自動生成工具，支援高品質 LLM 翻譯。

## 功能特色

- 使用 yt-dlp 下載 YouTube 影片
- 透過 Groq Whisper (whisper-large-v3-turbo) 自動語音辨識
- 整合 Agno 框架進行高品質 LLM 翻譯（預設：groq:openai/gpt-oss-120b）
- 輸出 SRT 和 ASS 格式的雙語字幕
- 可選字幕燒錄功能，macOS 支援硬體加速（VideoToolbox）
- 透過 SSE 即時追蹤處理進度
- 網頁介面支援多語系（英文/繁體中文）
- Job-based 非同步架構，記憶體內儲存

## 快速開始

### Docker（推薦）

```bash
docker build -t bilingualsub . && docker run -p 7860:7860 -e GROQ_API_KEY=your_key_here bilingualsub
```

然後在瀏覽器開啟 http://localhost:7860。

### 選用：使用 CLIProxyAPI 的 Docker Compose

這個流程是選用的。只有當你想讓翻譯走本機 CLIProxyAPI container，並使用
自己的 Antigravity/Codex/Claude OAuth 登入狀態時才需要。上面的單純 Docker
流程不需要 CLIProxyAPI。

對 Antigravity/agy 來說，只要 host 已有 OAuth credentials，CLIProxyAPI 就能
開箱路由請求。先在 host 安裝 CLIProxyAPI 並登入。OAuth token 會建立在
`~/.cli-proxy-api`，之後由 compose 掛進 proxy container：

```bash
cliproxyapi -antigravity-login
```

從範例建立本機 `.env`，並至少設定 `GROQ_API_KEY`：

```bash
cp .env.example .env
```

Compose 模式請使用 OpenAI-compatible proxy model：

```env
TRANSLATOR_MODEL=openai:bilingualsub-gemini-flash
# 選填：只有 auth 目錄不是 ~/.cli-proxy-api 時才需要設定
# CLIPROXY_AUTH_DIR=/absolute/path/to/.cli-proxy-api
```

啟動兩個服務：

```bash
docker compose up --build
```

BilingualSub 會跑在 http://localhost:7860。它會透過 compose network 連到
`http://cli-proxy:8317/v1`，OAuth token 不會被打包進 image，也不會 commit
到 repo。proxy 對 host 只綁定 `127.0.0.1`；compose stack 內部固定使用本機
bearer key `bilingualsub-local`。

預設 alias 對應 Antigravity 的 `gemini-3.5-flash-low`，這是目前 CLIProxyAPI
版本中較穩定可發現的 Flash 變體。如果你的版本沒有這個 alias，可以列出可用
模型，並在 `.env` 設定 `TRANSLATOR_MODEL=openai:<model-id>`：

```bash
curl -H "Authorization: Bearer bilingualsub-local" http://localhost:8317/v1/models
```

### 本地開發

**前置需求**：Python 3.11+、FFmpeg、Node.js 18+、pnpm

```bash
# 1. 安裝後端依賴
uv sync --dev --extra e2e

# 2. 安裝前端依賴
cd frontend && pnpm install

# 3. 啟動後端伺服器（在一個終端機視窗）
uv run uvicorn bilingualsub.api.app:create_app --factory --reload

# 4. 啟動前端開發伺服器（在另一個終端機視窗）
cd frontend && pnpm dev
```

後端執行於 http://localhost:8000，前端執行於 http://localhost:5173。

## 環境變數設定

| 環境變數               | 說明                                  | 預設值                     | 必填 |
| ---------------------- | ------------------------------------- | -------------------------- | ---- |
| `GROQ_API_KEY`         | Groq API 金鑰，用於 Whisper 語音辨識  | -                          | 是   |
| `OPENAI_API_KEY`       | OpenAI API 金鑰（僅在使用 OpenAI 時） | -                          | 否   |
| `TRANSCRIBER_PROVIDER` | 語音辨識供應商                        | `groq`                     | 否   |
| `TRANSCRIBER_MODEL`    | 使用的 Whisper 模型                   | `whisper-large-v3-turbo`   | 否   |
| `TRANSLATOR_MODEL`     | 翻譯用的 LLM 模型                     | `groq:openai/gpt-oss-120b` | 否   |
| `OPENAI_BASE_URL`      | OpenAI-compatible proxy URL           | -                          | 否   |

## 架構說明

```
YouTube 網址 → 下載 (yt-dlp) → 擷取音訊 (FFmpeg) → 語音辨識 (Groq Whisper) →
翻譯 (Agno LLM) → 雙語字幕 (SRT/ASS) → 字幕燒錄 (FFmpeg，可選)
```

**後端**：FastAPI 搭配 job-based 非同步架構。透過 `POST /api/jobs` 建立任務，在背景執行處理，並透過 `GET /api/jobs/{id}/events` 使用 Server-Sent Events (SSE) 串流進度更新。任務資料儲存於記憶體中，TTL 為 30 分鐘。

**前端**：使用 Vite 8 建置的 React SPA。透過 `useJob` hook 管理狀態機（idle → submitting → processing → completed/failed）。API 通訊由 `ApiClient` 單例處理，支援 REST 和 SSE。透過 i18next 實現國際化。

## 技術棧

| 後端             | 前端           |
| ---------------- | -------------- |
| FastAPI          | Vite 8         |
| Python 3.11+     | React 19       |
| yt-dlp           | TypeScript 5.9 |
| FFmpeg           | Tailwind CSS 4 |
| Groq Whisper     | i18next        |
| Agno（LLM 框架） | pnpm           |

## 授權條款

[Apache License 2.0](LICENSE)
