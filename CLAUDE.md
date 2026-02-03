# BilingualSub 開發指南

## 專案概述

YouTube 雙語字幕自動生成工具：
```
YouTube URL → 下載 → Whisper ASR → LLM 翻譯 → 雙語字幕 → 燒錄影片
```

## 開發環境設定

```bash
# 1. 安裝依賴
uv sync --dev --extra e2e

# 2. 安裝 pre-commit hooks
uv run pre-commit install

# 3. 安裝 Playwright（E2E 測試用）
uv run playwright install chromium
```

## 品質檢查（Hard Rules）

所有代碼必須通過以下檢查：

| 檢查項目 | 指令 | 說明 |
|---------|------|------|
| Ruff lint | `uv run ruff check src/ tests/` | 程式碼風格 |
| Ruff format | `uv run ruff format --check src/ tests/` | 格式化 |
| Mypy | `uv run mypy src/` | 靜態類型檢查 |
| Vulture | `uv run vulture src/bilingualsub --min-confidence=80` | Dead code 偵測 |
| Prettier | `npx prettier --check "**/*.{js,jsx,ts,tsx,json,yaml,md}"` | 前端格式化 |
| Unit tests | `uv run pytest tests/unit -m unit` | 單元測試 |
| Coverage | >= 80% | 測試覆蓋率 |

## Claude Hooks

專案已配置以下自動化 hooks：

1. **PostToolUse (Edit/Write)**: 自動執行 ruff 檢查和格式化
2. **PreToolUse (git commit)**: 自動執行品質檢查
3. **Quality Gate**: 完整品質檢查 `.claude/hooks/quality-gate.sh`

## 測試策略

```bash
# 單元測試（快速，mock 外部依賴）
uv run pytest tests/unit -m unit

# 整合測試（使用真實依賴）
uv run pytest tests/integration -m integration

# E2E 測試（完整工作流程）
uv run pytest tests/e2e -m e2e

# 全部測試
uv run pytest
```

## 開發流程

### 使用 Ralph Loop 開發模組
```bash
/ralph-loop "實作 downloader 模組，通過所有測試" \
  --completion-promise 'ALL TESTS PASS' \
  --max-iterations 20
```

### 每個模組的完成標準
1. 單元測試通過
2. 整合測試通過
3. Lint/Format 通過
4. Type check 通過
5. Dead code 檢查通過
6. 覆蓋率 >= 80%

## 專案結構

```
src/bilingualsub/
├── core/           # 核心業務邏輯
│   ├── downloader.py
│   ├── transcriber.py
│   ├── translator.py
│   └── merger.py
├── formats/        # 字幕格式處理
│   ├── srt.py
│   └── ass.py
├── utils/          # 工具函數
│   ├── ffmpeg.py
│   └── config.py
├── cli.py          # CLI 入口
└── api.py          # Web API 入口
```

## 環境變數

```bash
# .env（不要 commit）
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=xxx
```

## 常用指令

```bash
# 執行品質檢查
.claude/hooks/quality-gate.sh

# 格式化代碼
uv run ruff format src/ tests/
npx prettier --write "**/*.{js,jsx,ts,tsx,json,yaml,md}"

# 修復 lint 問題
uv run ruff check src/ tests/ --fix
```
