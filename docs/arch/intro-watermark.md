# Architecture: 影片片頭與浮水印

## 概述

在現有三段管線（download → subtitle → burn）的 `run_burn` 完成後，加入兩個後置步驟：watermark burn（正片加浮水印）和 intro + concat（生成片頭，接合）。是否執行這兩個後置步驟由 `job.video_channel` 是否為空字串決定——本地上傳沒有頻道資訊故自動跳過，維持現有行為。

兩個新 FFmpeg 函數 `generate_intro()` 和 `concat_videos()` 加入 `src/bilingualsub/utils/ffmpeg.py`，均使用與 `burn_subtitles` 相同的 `subprocess.Popen + SpooledTemporaryFile + progress pipe` 模式。浮水印則是在現有 `burn_subtitles` 的 `-vf` filter chain 末端用逗號串接 `drawtext`，透過新增 `watermark_text: str | None = None` 可選參數實現，現有呼叫方不受影響。

`downloader.py` 的 `VideoMetadata` 加入 `channel: str = ""` 欄位，`download_video()` 從 info_dict 以 `channel` → `uploader` → `""` 的優先序擷取並寫入。`Job` dataclass 加入 `video_channel: str = ""` 和 `video_channel_url: str = ""`，`run_download` 在現有 metadata 寫入區段補存這兩個欄位。

字體策略：Inter 和 Noto Serif TC 不在所有系統預裝。`drawtext` 使用 `font=` 名稱而非 `fontfile=` 路徑，讓 FFmpeg 依系統 fontconfig 解析。設計規格的 Inter（無衬線）對應 `font='Arial'`，Noto Serif TC（衬線）對應 `font='serif'`。系統若缺字體 FFmpeg 自動回退到內建 monospace，視覺略差但不會失敗，符合降級精神。片頭生成強制使用 libx264（即使在 macOS 上），因為 VideoToolbox 不支援以 `lavfi color` 作為輸入源的硬體加速路徑，且 5 秒片頭的軟體編碼成本可接受。

## Files to Create / Modify

### 新建

| 路徑                                                 | 說明                                                                     |
| ---------------------------------------------------- | ------------------------------------------------------------------------ |
| `tests/unit/utils/test_ffmpeg_intro.py`              | UT：`generate_intro`、`concat_videos`、`burn_subtitles` watermark branch |
| `tests/integration/test_intro_watermark_pipeline.py` | IT：Journey 索引的因果鏈測試                                             |

### 修改

| 路徑                                  | 修改內容                                                                                                                           |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `src/bilingualsub/core/downloader.py` | `VideoMetadata` 加 `channel: str = ""`；`download_video()` 補加 channel 擷取；`_extract_metadata_from_info_dict()` 加 channel 欄位 |
| `src/bilingualsub/api/jobs.py`        | `Job` 加 `video_channel: str = ""` 和 `video_channel_url: str = ""`                                                                |
| `src/bilingualsub/api/constants.py`   | `FileType` 加 `INTRO_VIDEO = "intro_video"`                                                                                        |
| `src/bilingualsub/utils/ffmpeg.py`    | `burn_subtitles()` 加 `watermark_text` 參數；新增 `generate_intro()`；新增 `concat_videos()`                                       |
| `src/bilingualsub/api/pipeline.py`    | `run_download()` 補存 channel；`run_burn()` 加片頭流程和降級邏輯；burn 進度重映射                                                  |

## Responsibility Map

| 元件                                                      | 層級      | 負責                                                                                                          | 不碰                                  |
| --------------------------------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| `core/downloader.py` — `VideoMetadata.channel`            | Core Data | 持有頻道名稱；fallback 順序：`channel` → `uploader` → `""`                                                    | pipeline 邏輯、FFmpeg                 |
| `utils/ffmpeg.py` — `burn_subtitles(watermark_text=)`     | Utils     | 將 drawtext 串接到既有 vf_filter 末端；`None` 時行為與現在完全相同                                            | channel 來源判斷                      |
| `utils/ffmpeg.py` — `generate_intro()`                    | Utils     | 用 FFmpeg `color + drawtext + fade` 生成黑底片頭；回傳 Path；FFmpegError 向上拋                               | pipeline 進度、job 狀態、channel 決策 |
| `utils/ffmpeg.py` — `concat_videos()`                     | Utils     | 用 FFmpeg concat demuxer 接合兩段影片；回傳 Path；FFmpegError 向上拋                                          | 片頭內容決策                          |
| `api/pipeline.py` — `run_burn()` 後置邏輯                 | Pipeline  | 判斷 `job.video_channel` 是否有值；依序呼叫 burn（含 watermark）→ generate_intro → concat；降級邏輯；進度管理 | FFmpeg filter 細節                    |
| `api/jobs.py` — `Job.video_channel` / `video_channel_url` | State     | 跨 phase 攜帶頻道名稱和 URL                                                                                   | 決策邏輯                              |

## Interface Design

### `VideoMetadata` 新增欄位

```python
@dataclass
class VideoMetadata:
    title: str
    duration: float
    width: int
    height: int
    fps: float
    description: str = ""
    channel: str = ""      # 新增；空字串合法（本地上傳）
```

`__post_init__` 不驗證 `channel`，空字串不拋錯。

### channel 擷取邏輯（在 `download_video()` info_dict 覆寫區段末尾加入）

```python
channel_raw = info_dict.get("channel") or info_dict.get("uploader") or ""
metadata.channel = channel_raw.strip() if isinstance(channel_raw, str) else ""
```

### `Job` 新增欄位

```python
video_channel: str = ""        # 頻道名稱，空字串 → 跳過片頭流程
video_channel_url: str = ""    # 頻道 URL，空字串 → 片頭中不顯示頻道 URL 行
```

### `run_download()` 中的 channel_url 判斷

```python
raw_channel_url = info_dict.get("channel_url", "") or ""
is_youtube_source = "youtube.com" in (job.source_url or "")
job.video_channel_url = raw_channel_url if (is_youtube_source and raw_channel_url) else ""
```

### `burn_subtitles` 新增參數

```python
def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    *,
    on_progress: Callable[[float], None] | None = None,
    watermark_text: str | None = None,     # 新增；None → 不加浮水印
) -> Path:
```

watermark drawtext 串接邏輯（在既有 `vf_filter` 建立後加入）：

```python
if watermark_text is not None:
    safe_text = watermark_text.replace("'", "\\'").replace(":", "\\:")
    watermark_drawtext = (
        f"drawtext=text='{safe_text}'"
        ":font='Arial'"
        ":fontsize=12"
        ":fontcolor=white@0.45"
        ":shadowcolor=black@0.8"
        ":shadowx=1:shadowy=1"
        ":x=w-tw-20"
        ":y=18"
    )
    vf_filter = f"{vf_filter},{watermark_drawtext}"
```

### `generate_intro` 函數簽名

```python
def generate_intro(
    output_path: Path,
    *,
    width: int,
    height: int,
    fps: float,
    channel: str,
    video_title: str,
    video_url: str,
    channel_url: str = "",      # 空字串 → 不顯示頻道 URL 行
    duration: float = 5.0,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
```

FFmpeg 命令結構：

```
ffmpeg
  -f lavfi
  -i color=c=black:s={width}x{height}:r={fps}:d={duration}
  -vf "{drawtext_chain},fade=t=out:st={duration - 0.5}:d=0.5"
  -c:v libx264 -crf 23 -preset fast
  -an
  -progress pipe:1
  -y {output_path}
```

`drawtext_chain` 為多個 drawtext filter 以逗號串接，各 block 使用 `enable='between(t,{start},{end})'` 和 `alpha=` 表達式實現分段淡入效果。`channel_url` 為空時跳過對應的 drawtext filter。文字溢出透過 `drawtext` 的座標和 `fix_bounds=1` 參數限制顯示寬度。

### `concat_videos` 函數簽名

```python
def concat_videos(
    first_path: Path,
    second_path: Path,
    output_path: Path,
    *,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
```

FFmpeg 命令結構：

```
# 暫存 concat list 文件（output_path.parent / "concat_list.txt"）：
file '/absolute/path/to/intro.mp4'
file '/absolute/path/to/main.mp4'

ffmpeg
  -f concat -safe 0
  -i {concat_list_path}
  -c copy
  -progress pipe:1
  -y {output_path}
```

`-c copy` 不重新編碼。片頭固定 libx264，正片在 macOS 用 h264_videotoolbox，Linux 用 libx264，兩者均為 H.264，concat 後容器相容。暫存 concat list 文件在 `try/finally` 中刪除。

## Data Flow

### Journey 1：YouTube URL 燒錄流程（有頻道資訊）

```
POST /api/jobs { source_url: "https://youtube.com/..." }
      │
  run_download(job)
      ├── download_video() → VideoMetadata { channel: "3Blue1Brown", ... }
      ├── job.video_channel = "3Blue1Brown"
      ├── job.video_channel_url = "youtube.com/@3Blue1Brown"  ← is_youtube=True
      ├── job.video_width = 1920, job.video_height = 1080
      └── job.output_files[SOURCE_VIDEO] = work_dir/video.mp4
      │
  run_subtitle(job) → (unchanged)
      │
POST /api/jobs/:id/burn { srt_content }
      │
  run_burn(job, srt_content)
      │
      ├── [0%→80%] burn_subtitles(
      │       source_video, srt_path, work_dir/output.mp4,
      │       watermark_text="Source: 3Blue1Brown",
      │       on_progress=lambda p: _send_progress(..., p * 0.8),
      │   ) → work_dir/output.mp4
      │
      ├── job.video_channel 不為空 → 進入片頭流程
      │
      ├── [80%→90%] generate_intro(
      │       work_dir/intro.mp4,
      │       width=1920, height=1080, fps=30.0,
      │       channel="3Blue1Brown",
      │       video_title=job.video_title,
      │       video_url=job.source_url,
      │       channel_url="youtube.com/@3Blue1Brown",
      │   ) → work_dir/intro.mp4
      │
      ├── [90%→99%] concat_videos(
      │       work_dir/intro.mp4,
      │       work_dir/output.mp4,
      │       work_dir/final.mp4,
      │   ) → work_dir/final.mp4
      │
      ├── job.output_files[VIDEO] = work_dir/final.mp4
      └── _send_complete(job)  ← progress = 100%
```

### Journey 2：本地上傳（無頻道資訊）

```
  run_download(job)
      ├── _acquire_video() → extract_video_metadata()（無 channel）
      ├── job.video_channel = ""
      └── 其餘不變
      │
  run_burn(job, srt_content)
      ├── [0%→100%] burn_subtitles(..., watermark_text=None)  ← 行為與現在一致
      ├── job.video_channel == "" → 跳過片頭流程
      ├── job.output_files[VIDEO] = work_dir/output.mp4
      └── _send_complete(job)
```

### Journey 3：非 YouTube URL（有頻道名稱，無頻道 URL）

```
  run_download(job)
      ├── download_video() → VideoMetadata { channel: "Bilibili主播", ... }
      ├── job.video_channel = "Bilibili主播"
      └── job.video_channel_url = ""    ← is_youtube=False → 強制空字串
      │
  run_burn(job, srt_content)
      ├── generate_intro(..., channel_url="")  ← 不顯示頻道 URL 行
      └── 其餘同 Journey 1
```

### 降級路徑

```
  generate_intro() 拋 FFmpegError
      ├── log.warning("intro_generation_failed", error=str(exc))
      ├── 跳過 concat_videos
      ├── job.output_files[VIDEO] = output_video   ← 僅字幕正片
      └── _send_complete(job)

  concat_videos() 拋 FFmpegError（intro 已生成）
      ├── log.warning("concat_failed", error=str(exc))
      ├── job.output_files[VIDEO] = output_video   ← 降級為僅字幕正片
      └── _send_complete(job)
```

## Build Sequence

### Phase 1：Core Data 擴充（additive）

- `src/bilingualsub/core/downloader.py`：`VideoMetadata` 加 `channel: str = ""`；`download_video()` 補加 channel 擷取
- `src/bilingualsub/api/jobs.py`：`Job` 加 `video_channel: str = ""` 和 `video_channel_url: str = ""`
- `src/bilingualsub/api/constants.py`：`FileType` 加 `INTRO_VIDEO = "intro_video"`

### Phase 2：FFmpeg 工具函數（additive，向後相容）

- `src/bilingualsub/utils/ffmpeg.py`：
  - `burn_subtitles()` 加 `watermark_text: str | None = None` 參數
  - 新增 `generate_intro()`
  - 新增 `concat_videos()`

### Phase 3：Pipeline 整合（breaking — `run_burn` 行為改變）

- `src/bilingualsub/api/pipeline.py`：
  - `run_download()`：補存 `job.video_channel` 和 `job.video_channel_url`
  - `run_burn()`：加 watermark 參數、片頭流程、降級邏輯、進度重映射

### Phase 4：測試（additive）

- `tests/unit/utils/test_ffmpeg_intro.py`
- `tests/integration/test_intro_watermark_pipeline.py`
- 既有 pipeline tests 補充 channel 相關 cases

## Infra Reuse

| 現有元件                                          | 本功能如何複用                                                                   |
| ------------------------------------------------- | -------------------------------------------------------------------------------- |
| `subprocess.Popen + SpooledTemporaryFile` pattern | `generate_intro` 和 `concat_videos` 複製 `burn_subtitles` 的 subprocess 管理模式 |
| `_send_progress(job, JobStatus.BURNING, ...)`     | intro 和 concat 子步驟繼續用 `BURNING` status，前端不需改                        |
| `asyncio.to_thread()`                             | `generate_intro` 和 `concat_videos` 都是阻塞操作，用相同包裝模式                 |
| `extract_video_metadata()`                        | 解析度和 fps 由 job 欄位傳入，不需額外呼叫                                       |

## Test Strategy

### Unit Test 邊界

**`tests/unit/utils/test_ffmpeg_intro.py`**

| 目標                                           | 測試行為                                          |
| ---------------------------------------------- | ------------------------------------------------- |
| `burn_subtitles(watermark_text="Source: X")`   | `-vf` 包含逗號分隔的 drawtext                     |
| `burn_subtitles(watermark_text=None)`          | `-vf` 不含 drawtext（regression）                 |
| `burn_subtitles` watermark text 含 `:`         | drawtext 中 `:` 被 escape                         |
| `burn_subtitles` watermark text 含 `'`         | drawtext 中 `'` 被 escape                         |
| `generate_intro(..., channel_url="yt.com/@x")` | cmd 含 `color=` source；drawtext chain 含頻道 URL |
| `generate_intro(..., channel_url="")`          | drawtext chain 不含頻道 URL                       |
| `generate_intro` FFmpeg 失敗                   | 拋 `FFmpegError`                                  |
| `generate_intro` 固定用 libx264                | cmd 中 `-c:v libx264`，不受 platform 影響         |
| `concat_videos(first, second, output)`         | cmd 含 `-f concat`、`-c copy`；concat list 正確   |
| `concat_videos` 輸入不存在                     | 拋 `FFmpegError`                                  |

**`tests/unit/api/test_pipeline.py` 補充**

| 目標                             | 測試行為                                            |
| -------------------------------- | --------------------------------------------------- |
| `run_burn` channel 不為空        | watermark_text 傳入；generate_intro + concat 被呼叫 |
| `run_burn` channel 為空          | watermark_text=None；generate_intro 未被呼叫        |
| `run_burn` generate_intro 失敗   | log warning；concat 未被呼叫；仍 COMPLETE           |
| `run_burn` concat 失敗           | log warning；仍 COMPLETE；VIDEO = output.mp4        |
| `run_download` YouTube + channel | job.video_channel 正確                              |
| `run_download` fallback uploader | job.video_channel = uploader                        |
| `run_download` 本地上傳          | job.video_channel = ""                              |

### Integration Test 邊界

**`tests/integration/test_intro_watermark_pipeline.py`**

| Journey                         | Test Chain                                                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| J1：YouTube → 完整片頭+浮水印   | POST /jobs → run_download (mock) → run_burn → assert burn with watermark → assert generate_intro called → assert concat → VIDEO = final.mp4 |
| J2：本地上傳 → 無片頭無浮水印   | POST /jobs (local) → run_burn → assert burn without watermark → generate_intro never called                                                 |
| J3：非 YouTube → 片頭無頻道 URL | run_burn → assert generate_intro(channel_url="")                                                                                            |
| 降級：intro 失敗                | generate_intro raises → still COMPLETED → VIDEO = output.mp4                                                                                |
| 降級：concat 失敗               | concat raises → still COMPLETED → VIDEO = output.mp4                                                                                        |

### Mock 決策

| 對象                                                  | Mock / Real                  | 原因                           |
| ----------------------------------------------------- | ---------------------------- | ------------------------------ |
| `subprocess.Popen`                                    | Mock                         | 避免真實 FFmpeg；驗證 cmd 結構 |
| `burn_subtitles` / `generate_intro` / `concat_videos` | Mock + spy（pipeline tests） | 隔離 run_burn 邏輯             |
| `download_video`                                      | Mock（沿用現有）             | 避免網路請求                   |

### Coverage 要求

核心邏輯 ≥ 90%，整體 ≥ 80%
