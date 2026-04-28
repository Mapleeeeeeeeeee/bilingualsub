# Architecture: Visual Description Mode

## 概述

在現有 download → subtitle → burn 三階段管線上，新增一條平行的字幕生成路徑：當使用者選擇「視覺描述」模式時，subtitle phase 以 `describe_video()` 取代 `transcribe_audio()`。Gemini 3.1 Flash Lite Preview 直接讀取影片檔（`FileType.SOURCE_VIDEO`）並回傳帶時間戳的畫面描述，再由現有 `translate_subtitle()` 翻譯成目標語言。因為視覺描述不存在「原文字幕」概念，merge 步驟跳過，只序列化目標語言 SRT。

## Files to Create / Modify

### 新建

| 路徑                                                    | 說明                                                                                                    |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `src/bilingualsub/core/visual_describer.py`             | Gemini File API 封裝；對外唯一函數 `describe_video(video_path, *, source_lang) -> Subtitle`             |
| `tests/unit/core/test_visual_describer.py`              | UT：mock `google.genai.Client`，驗證解析邏輯與錯誤路徑                                                  |
| `tests/integration/test_visual_description_pipeline.py` | IT：Journey 1 端到端鏈（POST /jobs → POST /jobs/:id/subtitle 含 processing_mode → validate SRT exists） |

### 修改

| 路徑                                   | 修改內容                                                                                                                                                              |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/bilingualsub/api/constants.py`    | `SubtitleSource` 新增 `VISUAL_DESCRIPTION = "visual_description"`                                                                                                     |
| `src/bilingualsub/api/jobs.py`         | `Job` dataclass 新增 `processing_mode: str = "subtitle"` 和 `video_duration: float = 0.0`；`JobManager.create_job()` 新增 `processing_mode` 參數                      |
| `src/bilingualsub/api/schemas.py`      | `JobCreateRequest` 新增 `processing_mode: Literal["subtitle", "visual_description"] = "subtitle"`；`StartSubtitleRequest` 新增同欄位                                  |
| `src/bilingualsub/api/routes.py`       | `create_job()` 傳 `processing_mode`；`start_subtitle()` 覆寫 `job.processing_mode`                                                                                    |
| `src/bilingualsub/api/pipeline.py`     | `run_subtitle()` 依 `job.processing_mode` 分支；新增 `_run_visual_description_subtitle()` 和 `_serialize_translated_only()`；`_ERROR_MAP` 加 `VisualDescriptionError` |
| `src/bilingualsub/core/__init__.py`    | 匯出 `VisualDescriptionError`, `describe_video`                                                                                                                       |
| `src/bilingualsub/utils/config.py`     | `Settings` 新增 `gemini_api_key: str = ""`；新增 `get_gemini_api_key()` guard function                                                                                |
| `pyproject.toml`                       | `dependencies` 加 `google-genai>=1.0.0`；mypy override 加 `google.genai.*`                                                                                            |
| `frontend/src/types.ts`                | `JobCreateRequest` 新增 `processing_mode?: 'subtitle' \| 'visual_description'`                                                                                        |
| `frontend/src/components/UrlInput.tsx` | 新增 `processingMode` state 與 Toggle UI（參考 rangeEnabled 模式）                                                                                                    |
| `frontend/src/i18n/zh-TW.json`         | `form` 加 Toggle 相關 key；`progress` 加 `describing`；`error` 加 `visual_description_failed`                                                                         |
| `frontend/src/i18n/en.json`            | 同上英文 key                                                                                                                                                          |

## Responsibility Map

| 元件                                                     | 層級       | 負責                                                                | 不碰                          |
| -------------------------------------------------------- | ---------- | ------------------------------------------------------------------- | ----------------------------- |
| `core/visual_describer.py`                               | Core       | Gemini API 呼叫、response 解析、timestamp regex、回傳 `Subtitle`    | pipeline 進度、job 狀態、翻譯 |
| `api/pipeline.py` — `_run_visual_description_subtitle()` | Pipeline   | 進度管理、呼叫 describe_video + translate、影片時長驗證、SRT 序列化 | Gemini API 細節、前端狀態     |
| `api/pipeline.py` — `_serialize_translated_only()`       | Pipeline   | 單語 SRT 序列化、寫入 output_files                                  | 翻譯邏輯、merge 邏輯          |
| `api/routes.py`                                          | Controller | schema 驗證、`processing_mode` 傳遞給 Job 和 pipeline               | pipeline 邏輯、Gemini 細節    |
| `api/schemas.py`                                         | Schema     | request 驗證（`Literal["subtitle", "visual_description"]`）         | 業務邏輯                      |
| `frontend/UrlInput.tsx`                                  | View       | Toggle 渲染、`processing_mode` 附加到 request                       | API 呼叫、狀態管理            |

## Interface Design

### `describe_video` 函數簽名

```python
def describe_video(
    video_path: Path,
    *,
    source_lang: str = "en",
) -> Subtitle:
    """Analyze video frames with Gemini 3.1 Flash Lite Preview and return timestamped descriptions.

    Raises:
        VisualDescriptionError: If Gemini API fails or no segments can be parsed.
        ValueError: If GEMINI_API_KEY is not set or video_path doesn't exist.
    """
```

### `VisualDescriptionError`

```python
class VisualDescriptionError(Exception):
    """Raised when Gemini visual description fails."""
```

### `Settings` 新增欄位

```python
gemini_api_key: str = ""
```

### `get_gemini_api_key()`

```python
def get_gemini_api_key() -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set. "
            "Please set it with your Gemini API key."
        )
    return settings.gemini_api_key
```

### `JobCreateRequest` 更新

```python
processing_mode: Literal["subtitle", "visual_description"] = "subtitle"
```

### `StartSubtitleRequest` 更新

```python
processing_mode: Literal["subtitle", "visual_description"] | None = None
```

### 前端 `JobCreateRequest` 更新

```typescript
processing_mode?: 'subtitle' | 'visual_description';
```

## Data Flow

### 視覺描述路徑（Journey 1）

```
使用者切換 Toggle → processing_mode: "visual_description"
      │
POST /api/jobs { source_url, processing_mode: "visual_description" }
      │
  JobManager.create_job(processing_mode="visual_description")
      │
  run_download(job)
      ├── _acquire_video() → job.output_files[SOURCE_VIDEO], job.video_duration
      ├── _extract_audio_step()                ← 仍執行（架構簡單，多幾秒無害）
      └── _send_download_complete()
      │
前端 download_complete → 使用者點「產生字幕」
      │
POST /api/jobs/:id/subtitle { processing_mode: "visual_description" }
      │
  routes.start_subtitle() → job.processing_mode = "visual_description"
      │
  run_subtitle(job) → job.processing_mode == "visual_description"
      │
  _run_visual_description_subtitle(job)
      ├── validate video_duration <= 5400 (90 min)
      ├── progress 20% "describe" — "分析畫面內容中..."
      ├── describe_video(SOURCE_VIDEO, source_lang=job.source_lang) → Subtitle
      │       └── google-genai: files.upload → models.generate_content → parse timestamps
      ├── job.subtitle_source = VISUAL_DESCRIPTION
      ├── progress 50% "translate"
      ├── translate_subtitle(described_sub, ...) → translated_sub
      ├── progress 70% "serialize"
      ├── _serialize_translated_only(translated_sub)
      │       └── serialize_srt → subtitle.srt → job.output_files[SRT]
      └── _send_complete(job)
      │
前端 completed → SubtitleEditor 載入 SRT（單語，只有 translated 欄位）
      │
POST /api/jobs/:id/burn { srt_content } → run_burn()（完全複用）
```

### 語音字幕路徑（不受影響）

`job.processing_mode == "subtitle"` → 現有 `run_subtitle()` 主體邏輯不變。

## Build Sequence

### Phase 1：後端基礎（additive）

- `pyproject.toml`：加 `google-genai>=1.0.0` 依賴；加 mypy override
- `utils/config.py`：加 `gemini_api_key` 欄位、`get_gemini_api_key()` 函數
- `api/constants.py`：`SubtitleSource` 加 `VISUAL_DESCRIPTION`
- `api/jobs.py`：`Job` 加 `processing_mode`, `video_duration`；`JobManager.create_job()` 加 `processing_mode` 參數
- `api/pipeline.py`：`run_download()` 補存 `job.video_duration`

### Phase 2：Core 模組（additive）

- `core/visual_describer.py`：實作 `describe_video()`，含 `DESCRIBE_PROMPT`、timestamp regex parser、`VisualDescriptionError`
- `core/__init__.py`：匯出新符號

### Phase 3：Pipeline 分支（breaking — run_subtitle 需同步改動）

- `api/pipeline.py`：`_run_visual_description_subtitle()`；`_serialize_translated_only()`；`run_subtitle()` 加分支；`_ERROR_MAP` 加 `VisualDescriptionError`
- `api/schemas.py`：`JobCreateRequest` 加 `processing_mode`；`StartSubtitleRequest` 加 `processing_mode`
- `api/routes.py`：`create_job()` 傳 `processing_mode`；`start_subtitle()` 覆寫 `job.processing_mode`

### Phase 4：前端（additive）

- `frontend/src/types.ts`：`JobCreateRequest` 加 `processing_mode`
- `frontend/src/i18n/zh-TW.json` & `en.json`：加新 i18n key
- `frontend/src/components/UrlInput.tsx`：加 `processingMode` state 與 Toggle UI

### Phase 5：測試（additive）

- `tests/unit/core/test_visual_describer.py`
- `tests/integration/test_visual_description_pipeline.py`

## Infra Reuse

| 現有元件                        | 視覺描述路徑如何複用                                                  |
| ------------------------------- | --------------------------------------------------------------------- |
| `run_download()`                | 完全複用，`SOURCE_VIDEO` 已存於 `output_files`，補存 `video_duration` |
| `translate_subtitle()`          | 完全複用，`described_sub` 與 `original_sub` 型別相同（`Subtitle`）    |
| `serialize_srt()`               | 複用，只呼叫一次（翻譯後字幕）                                        |
| `run_burn()`                    | 完全複用，接受 SRT 字串即可，不感知生成路徑                           |
| `SubtitleEditor`                | 複用，`original` 欄位在視覺描述模式下留空                             |
| `_make_translate_progress_cb()` | 完全複用，仍映射 50-70%                                               |

## Test Strategy

### Unit Test 邊界

**`tests/unit/core/test_visual_describer.py`**

| 目標             | 測試行為                                                                       |
| ---------------- | ------------------------------------------------------------------------------ |
| `describe_video` | 有效 Gemini response（3 條 MM:SS 時間戳）→ `Subtitle` with 3 entries，時間正確 |
| `describe_video` | response 無法解析出任何 entry → 拋 `VisualDescriptionError`                    |
| `describe_video` | `generate_content` 拋 exception → 包裝成 `VisualDescriptionError`              |
| `describe_video` | `GEMINI_API_KEY` 未設 → `ValueError`                                           |
| `describe_video` | 傳入不存在的 `video_path` → `ValueError`                                       |
| `describe_video` | response 中混有不符格式的行 → 只保留可解析的 entries，不拋錯                   |

**`tests/unit/api/` — pipeline 視覺描述分支**

| 目標                               | 測試行為                                                          |
| ---------------------------------- | ----------------------------------------------------------------- |
| `_run_visual_description_subtitle` | `job.video_duration = 5401.0` → `PipelineError("video_too_long")` |
| `_serialize_translated_only`       | 只寫 `FileType.SRT`，`FileType.ASS` 不在 output_files             |

### Integration Test 邊界

**`tests/integration/test_visual_description_pipeline.py`**

| Journey 步驟                | Test Chain                                                                                                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 使用者選視覺描述 → 產出 SRT | POST /jobs (processing_mode=visual_description) → inject DOWNLOAD_COMPLETE state → POST /subtitle → poll until COMPLETED → GET /download/srt → 200, SRT 非空, ASS 不存在 |
| 影片超過 90 分鐘 → 失敗     | POST /jobs → inject video_duration=5401 → POST /subtitle → poll → status=failed, error_code="video_too_long"                                                             |
| 缺 GEMINI_API_KEY → 失敗    | monkeypatch.delenv GEMINI_API_KEY → POST /subtitle → status=failed                                                                                                       |

### Mock 決策

| 對象                      | Mock / Real            | 原因                                        |
| ------------------------- | ---------------------- | ------------------------------------------- |
| `google.genai.Client`     | Mock                   | 外部 API，不穩定且需付費                    |
| `translate_subtitle` (IT) | Mock                   | 避免呼叫 Groq/OpenAI，回傳固定 `Subtitle`   |
| `describe_video` (IT)     | Mock                   | 避免呼叫 Gemini，但驗證其輸出能正確流入下游 |
| `get_settings`            | Real + monkeypatch env | 驗證 env 讀取邏輯正確                       |

### Coverage 要求

- `core/visual_describer.py` ≥ 80%
- `api/pipeline.py` 視覺描述分支被 IT 覆蓋
- 整體 ≥ 80%

## 開放問題

1. **Gemini 時間戳格式**：實際輸出格式（`MM:SS` vs `HH:MM:SS`）需 API 測試確認。timestamp regex 應寬鬆設計，覆蓋兩種格式。
2. **audio extraction 是否跳過**：視覺描述不需要音訊，但 `run_download()` 不感知 `processing_mode`。選擇維持現狀（多幾秒但架構簡單）。
3. **SubtitleEditor 對空 `original` 的處理**：需確認渲染邏輯對空字串的容忍度（可能顯示單行而非雙行）。
4. **Gemini 上傳檔案清理**：`client.files.upload()` 上傳的檔案預設 TTL 48 小時。第一版不主動清理。
