# V2: 智慧字幕管線升級

## 背景與問題

BilingualSub 目前的管線是「一條路」：所有影片都經過 Whisper 轉錄 → LLM 翻譯 → 合併。這帶來三個痛點：

1. **時間戳偏移**：Groq Whisper 對非 0 秒起始的音訊會把時間戳歸零（如音訊 03 秒開始 → 轉錄判定為 00 秒），這是 Whisper 架構的已知限制
2. **專有名詞被亂翻**：技術詞彙如 Agent、Skills、Claude Code 被翻成「代理人」「技能」，翻譯 prompt 沒有術語保留機制
3. **無語音影片無法處理**：螢幕錄製、操作教學等沒有旁白的影片完全無法產生字幕

另外前端 Vite 7 需要升級到 Vite 8。

## 使用者角色

使用者：需要將外語 YouTube 影片加上雙語字幕的個人使用者。痛點是翻譯品質不穩定、某些影片根本無法處理。

## 需求情境

- 使用者：When 影片有 YouTube 手動上傳字幕時，I want to 直接使用那些字幕來翻譯，so I can 避免 Whisper 的時間戳偏移問題且獲得更準確的原文
- 使用者：When 翻譯結果把專有名詞翻錯時，I want to 建立一組術語表讓系統記住，so I can 不用每次都手動修正相同的錯誤
- 使用者：When 影片沒有語音時，I want to 系統自動辨識畫面內容並產生描述性字幕，so I can 為操作教學等影片加上字幕

## 設計意圖

- **優先 YouTube 手動字幕、不用自動字幕** → 研究顯示 YouTube 自動字幕準確率僅 60-70%，Whisper 有 95%+。手動上傳字幕通常最準確，但自動生成的比 Whisper 差，所以只下載手動字幕
- **Glossary 用 JSON 而非 SQLite** → 專案目前無資料庫（in-memory job store），JSON 和現有架構一致，百筆術語綽綽有餘
- **Vision 模型不限定 provider** → 遵循現有 translator 用 Agno 抽象的模式，由環境變數切換
- **靜音偵測自動分流** → 使用者不需要手動選擇管線模式，系統自動判斷

## User Journey

### Journey 1：使用者 — 有手動字幕的影片

前置條件：影片在 YouTube 上有創作者上傳的字幕

1. 使用者貼上 YouTube URL → 系統開始下載影片
2. 系統用 yt-dlp 檢查是否有手動上傳字幕 → 發現有英文手動字幕
3. 進度顯示「使用 YouTube 字幕」→ 系統下載 SRT 字幕並解析
4. 跳過 Whisper 轉錄 → 直接進入翻譯步驟
5. 翻譯完成 → 使用者在編輯器中檢視雙語字幕
   → 時間戳來自 YouTube 原始字幕，精準度高

### Journey 2：使用者 — 無手動字幕的影片（有語音）

前置條件：影片沒有手動字幕但有語音

1. 使用者貼上 YouTube URL → 系統下載影片
2. 系統檢查手動字幕 → 無可用字幕
3. 進度顯示「正在轉錄（Whisper）」→ 走既有 Whisper 管線
4. 後續流程不變（翻譯 → 合併 → 燒錄）

### Journey 3：使用者 — 管理術語表

前置條件：使用者翻譯過影片，發現某些專有名詞被翻錯

1. 使用者在字幕編輯器中看到 "Agent" 被翻成「代理人」
2. 使用者點選該字幕條目的「加入術語表」按鈕
3. 彈出輸入框：原文 "Agent"、目標 "Agent"（保留原文）→ 確認
4. 術語被儲存到 glossary.json → 下次翻譯時 LLM prompt 會包含此術語
5. 使用者也可以從工具列打開「術語表管理」面板，批次新增/編輯/刪除術語

### Journey 4：使用者 — 術語表生效

前置條件：術語表中已有 "Agent → Agent"、"Skills → Skills"

1. 使用者提交新影片翻譯
2. 系統載入 glossary.json，將術語表注入翻譯 prompt
3. LLM 翻譯時保留 "Agent"、"Skills" 不翻譯
4. 使用者檢視結果 → 專有名詞正確保留

### Journey 5：使用者 — 無語音影片（視覺描述）

前置條件：影片是螢幕錄製或操作教學，沒有旁白

1. 使用者貼上影片 URL → 系統下載影片
2. 系統擷取音訊 → 偵測到幾乎全靜音
3. 進度顯示「偵測到無語音影片，正在分析畫面」
4. 系統每 5 秒擷取一個關鍵幀 → 送到 vision 模型分析
5. Vision 模型產生描述（如「打開設定頁面，點擊帳號選項」）
6. 描述轉換為字幕格式 → 進入翻譯 → 合併為雙語字幕

## 替代流程

- **yt-dlp 字幕下載失敗**：記錄 warning，靜默 fallback 到 Whisper 轉錄
- **靜音偵測誤判**（有語音但判為靜音）：使用者可在前端手動觸發重新轉錄（未來可加 force_transcribe 參數）
- **Vision 模型不可用**：回傳錯誤提示「此影片無語音且未設定視覺模型，請設定 VISION_MODEL 環境變數」
- **Glossary 檔案損壞/不存在**：系統啟動時建立空 glossary，損壞時重建並記錄 warning

## 錯誤情境

### 系統錯誤

- yt-dlp 字幕 API 回傳格式異常 → 解析失敗後 fallback Whisper
- Vision 模型 API 超時/額度不足 → 回傳明確錯誤碼
- glossary.json 寫入失敗（磁碟滿）→ 回傳 500 錯誤

### 使用者誤操作

- 在術語表中新增空白原文 → 前後端驗證，拒絕空值
- 在術語表中新增重複原文 → 更新既有條目而非新增

### 惡意行為

- Glossary 注入（用極長文字或 prompt injection 內容作為術語）→ 限制單一術語長度 100 字元，glossary 總量上限 500 筆

## Out of Scope

- 多使用者 glossary 隔離（目前是單一 glossary 全域共用）
- Glossary 分類標籤或群組
- WhisperX 本地端對齊（需要 GPU，架構差異太大）
- YouTube 自動生成字幕的使用（研究顯示品質不如 Whisper）
- 即時串流字幕
- Vite 8 升級細節（純基礎設施變更，不影響功能設計）

## 整合點

| 系統                | 用途                                        | 備註                            |
| ------------------- | ------------------------------------------- | ------------------------------- |
| yt-dlp              | 影片下載 + 字幕下載                         | 新增 `writesubtitles` 選項      |
| Groq Whisper API    | 語音轉錄                                    | 既有，作為 fallback             |
| Agno + LLM          | 翻譯                                        | 既有，新增 glossary prompt 注入 |
| Agno + Vision Model | 畫面描述                                    | 新增，provider TBD              |
| FFmpeg              | 音訊擷取 + 靜音偵測 + 關鍵幀擷取 + 字幕燒錄 | 新增靜音偵測和幀擷取            |
| JSON 檔案系統       | Glossary 持久化                             | 新增                            |

## Acceptance Criteria

### 字幕來源

- Given 影片有 YouTube 手動上傳的英文字幕
  When 使用者提交該影片進行翻譯
  Then 系統下載手動字幕並跳過 Whisper 轉錄，進度顯示「使用 YouTube 字幕」

- Given 影片只有 YouTube 自動生成字幕（無手動字幕）
  When 使用者提交該影片進行翻譯
  Then 系統使用 Whisper 轉錄，不使用自動生成字幕

- Given 影片既無手動也無自動字幕
  When 使用者提交該影片進行翻譯
  Then 系統使用 Whisper 轉錄

- Given yt-dlp 字幕下載過程中發生錯誤
  When 系統嘗試取得字幕
  Then 自動 fallback 到 Whisper 轉錄，不中斷流程

### 術語表

- Given 術語表中有 "Agent → Agent"
  When 翻譯包含 "Agent" 的字幕
  Then 翻譯結果保留 "Agent" 不翻譯

- Given 使用者在字幕編輯器中選擇一個條目
  When 點擊「加入術語表」
  Then 彈出輸入框讓使用者確認原文和目標翻譯，確認後儲存到 glossary.json

- Given 使用者打開術語表管理面板
  When 新增/編輯/刪除術語
  Then 變更即時生效，並持久化到 glossary.json

- Given 術語表有 500 筆條目
  When 使用者嘗試新增第 501 筆
  Then 系統拒絕並提示「術語表已達上限」

### 視覺描述

- Given 影片音訊 90% 以上為靜音
  When 系統完成靜音偵測
  Then 自動切換到視覺描述管線，擷取關鍵幀並產生描述性字幕

- Given 視覺模型未設定（無 VISION_MODEL 環境變數）
  When 系統偵測到靜音影片
  Then 回傳明確錯誤訊息提示使用者設定視覺模型

- Given 視覺描述管線完成
  When 描述性字幕產生後
  Then 字幕進入翻譯和合併流程，最終輸出雙語字幕

## 開放問題

1. Vision 模型選擇 — 等使用者 TBD 確認，目前架構先用 Agno 抽象支援多 provider
2. 靜音偵測的閾值 (-40dB) 和比例 (90%) 是否需要可設定？初版先寫死觀察
3. 關鍵幀擷取間隔（5 秒）是否適合所有影片？操作快速的影片可能需要更短間隔
4. Glossary 是否需要 import/export 功能？初版先不做
