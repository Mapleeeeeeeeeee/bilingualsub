# BilingualSub

YouTube 雙語字幕自動生成工具，支援高品質 LLM 翻譯。

## 功能

- YouTube 影片下載（yt-dlp）
- 自動語音轉文字（Faster-Whisper）
- 高品質 LLM 翻譯（GPT-4o / Gemini / Claude）
- 雙語字幕輸出（SRT / ASS）
- 字幕燒錄到影片（FFmpeg）

## 安裝

```bash
# 使用 uv
uv sync

# 安裝 Playwright（E2E 測試用）
uv run playwright install chromium
```

## 使用

```bash
# CLI 使用
bilingualsub process "https://youtube.com/watch?v=xxx" --output ./output

# 或使用 uv
uv run bilingualsub process "https://youtube.com/watch?v=xxx"
```

## 開發

```bash
# 安裝開發依賴
uv sync --dev --extra e2e

# 安裝 pre-commit hooks
uv run pre-commit install

# 執行測試
uv run pytest

# Lint 檢查
uv run ruff check src/ tests/

# Type 檢查
uv run mypy src/

# Dead code 檢查
uv run vulture src/bilingualsub --min-confidence=80
```

## 授權

Apache 2.0
