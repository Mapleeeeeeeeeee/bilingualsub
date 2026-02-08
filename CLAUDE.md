# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

YouTube 雙語字幕自動生成工具：

```
YouTube URL → 下載 → Whisper ASR → LLM 翻譯 → 雙語字幕 → 燒錄影片
```

## 開發環境設定

```bash
# 1. 安裝後端依賴
uv sync --dev --extra e2e

# 2. 安裝 pre-commit hooks
uv run pre-commit install

# 3. 安裝 Playwright（E2E 測試用）
uv run playwright install chromium

# 4. 安裝前端依賴
cd frontend && pnpm install
```

## 常用指令

| 用途                | 指令                                                                        |
| ------------------- | --------------------------------------------------------------------------- |
| 啟動後端 dev server | `uv run uvicorn bilingualsub.api.app:create_app --factory --reload`         |
| 啟動前端 dev server | `cd frontend && pnpm dev`                                                   |
| 執行單一測試檔      | `uv run pytest tests/unit/path/to/test_file.py -m unit`                     |
| 執行單一測試函數    | `uv run pytest tests/unit/path/to/test_file.py::test_function_name -m unit` |
| 完整品質檢查        | `.claude/hooks/quality-gate.sh`                                             |
| Ruff lint           | `uv run ruff check src/ tests/`                                             |
| Ruff format         | `uv run ruff format --check src/ tests/`                                    |
| 格式化代碼          | `uv run ruff format src/ tests/`                                            |
| 修復 lint 問題      | `uv run ruff check src/ tests/ --fix`                                       |
| Mypy                | `uv run mypy src/`                                                          |
| Vulture             | `uv run vulture src/bilingualsub --min-confidence=80`                       |
| Prettier 檢查       | `npx prettier --check "**/*.{js,jsx,ts,tsx,json,yaml,md}"`                  |
| Prettier 格式化     | `npx prettier --write "**/*.{js,jsx,ts,tsx,json,yaml,md}"`                  |
| 單元測試            | `uv run pytest tests/unit -m unit`                                          |

**品質要求**: 所有代碼必須通過 ruff、mypy、vulture、prettier 檢查，單元測試覆蓋率 >= 80%。

## 架構

### 後端 (FastAPI)

- **Job-based 非同步架構**: `POST /api/jobs` 建立 job → 背景執行 pipeline → `GET /api/jobs/{id}/events` 透過 SSE 串流進度
- **Pipeline 步驟** (pipeline.py): download → trim → extract audio → transcribe → translate → merge/serialize → burn
- **進度對應**: 0% → 15%(extract audio) → 20%(transcribe) → 50%(translate) → 70%(merge) → 80%(burn) → 100%
- **Job Store**: In-memory (jobs.py)，TTL 30 分鐘，無資料庫
- **非阻塞處理**: 阻塞操作用 `asyncio.to_thread()` 包裝
- **Core 模組**: downloader(yt-dlp)、transcriber(Groq Whisper)、translator(Agno+Groq)、merger 各自獨立

### 前端 (React + Vite)

- **技術棧**: Vite 7 + React 19 + TypeScript 5.9 + Tailwind CSS 4
- **狀態管理**: `useJob` hook 管理狀態機：idle → submitting → processing → completed/failed
- **API 通訊**: `ApiClient` 單例處理 REST 請求和 SSE 連線
- **國際化**: i18next（預設 zh-TW）
- **路徑別名**: `@/*` → `./src/*`
- **API 代理**: `/api` → `http://localhost:8000`（開發模式）
- **重要限制**: TypeScript 5.9 + `erasableSyntaxOnly: true` 禁止使用 `enum`，改用 `as const` + companion type

## 測試策略

```bash
uv run pytest tests/unit -m unit          # 單元測試（mock 外部依賴）
uv run pytest tests/integration -m integration  # 整合測試
uv run pytest tests/e2e -m e2e            # E2E 測試
```

- Coverage 要求 >= 80%
- `asyncio_mode="auto"` 已配置在 pytest.ini

## Claude Hooks

專案已配置以下自動化 hooks：

1. **PostToolUse (Edit/Write)**: 自動執行 ruff 檢查和格式化
2. **PreToolUse (git commit)**: 自動執行品質檢查
3. **Quality Gate**: 完整品質檢查 `.claude/hooks/quality-gate.sh`
