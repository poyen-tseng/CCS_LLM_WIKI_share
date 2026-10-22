# Jev 績效報告

這份文件記錄 `JEV_accel` 的實測：CCS 操作快了多少，以及 Jev 判斷得準不準、多快。目前用 `jev-latest`（2026-10-15 指向 `jev-1.13.0`）。2026-10-15 試過 `jev-1.14.0` 與看截圖的判讀，已放棄（見[最後一節](#截圖判讀jev-114-看圖-vs-opus-55-high2026-10-15)）。操作步驟與工具清單在 [README.md](README.md)。

## 怎麼讀這些數字

最終採用的答案，是 L0 規則已經有明確結論時的那一個。Jev 的意見會記下來，信心夠才在規則判斷不了時採用。所以表上的「最終答案」是整條工具的成績，「Jev 自己的答案」才是模型的成績。

示波器 A–E 的 fixture 和規則是一起寫的。L0 在那 36 題上的高分有一部分是照題目出規則，用途是回歸測試。看模型時，看「Jev 自己的答案」那一欄。

CCS 的時間有兩條基準，都來自這台電腦上的真實終端機：

- **冷啟動**（2026-10-06）：每次 `dss.bat`／`run.bat` 都重開 DebugServer。燒錄 Serial_Plotter 的 `150308` 是 48.1 秒，只做連線的 `253247` 是 47.4 秒。`533191`–`533198` 的 halt／load 每次 42–82 秒。
- **同一台已經暖機**（2026-10-07）：CloudAgent 已經在跑，`dss.bat` 連續燒錄兩次是 17.1 秒和 16.9 秒。

Daemon 的單步時間在 `results/ccs_runs.jsonl`。

## CCS 操作快了多少

常駐 debug session 聽在 `127.0.0.1:47011`。`initScripting` 只付一次：2026-10-07 是 3.74 秒，2026-10-08 是 3.67 秒。之後 halt、run、讀 PC 走同一條連線。

| 項目          | 以前                                    | 現在                                                         | 幅度                                | 出處                                                    |
| ----------- | ------------------------------------- | ---------------------------------------------------------- | --------------------------------- | ----------------------------------------------------- |
| halt        | 42–82 秒（整支 `run.bat`）                 | 80 毫秒（79.5、80.6、82.4）                                      | 約 500–1000 倍                      | `533191`–`98`；`ccs_runs.jsonl` 2026-10-07 23:36–23:40 |
| run         | 同上，每次重開                               | 13–20 毫秒                                                   | 約 2000–4000 倍                     | 同上                                                    |
| 讀 PC／status | 含在上面那支腳本裡                             | 8–16 毫秒                                                    | 低於 0.02 秒                         | `ccs_runs.jsonl` 的 `status`                           |
| 已連線時再載入 RAM | 42–82 秒                               | 3.9 秒，再載一次 2.6 秒                                           | 約 10–30 倍                         | GPIO_EX1，`ccs_runs.jsonl` 23:40                       |
| Flash 燒錄    | 冷啟動約 48 秒；暖機後的 `dss.bat` 約 17 秒       | LED_test 15.2 秒、Feedback_test 15.0 秒、Serial_Plotter 19.4 秒 | 對冷啟動約 2.5–3 倍。對暖機後的 `dss.bat` 差不多 | `150308`；2026-10-07 暖機對照；`ccs_runs.jsonl`             |
| 找工具路徑與探針主人  | 一次遞迴搜尋 38 秒，每個 session 再加 5–8 次 `dir` | `ccs-env` 一次 4.1 秒                                         | 那次 38 秒的搜尋約 9 倍                   | 終端機 `253244`；2026-10-08 `ccs-env`                     |
| 釋放探針        | 以前要等腳本結束才還                            | 約 240 毫秒                                                   | session 還在，探針已空出來                 | `ccs_runs.jsonl` 的 `release`（237–243 毫秒）              |

Flash 的 15 秒裡，寫入約 11–13 秒，reset 約 0.7 秒，verify 約 0.1 秒。這段和暖機後的 `dss.bat` 是同一件事。第一次使用還要加上面的 3.7 秒 `initScripting`，整段約 19–24 秒，對上冷啟動的 48 秒大約是 2–2.5 倍。Serial_Plotter 那次 19.4 秒含第一次 connect，PC 是 `0x8145d`，`.map` 檢查通過。

省下來的是不必為了 halt 或讀 PC 重開 DebugServer。LED_test 燒完後使用者確認 LED4／LED5 交替。Feedback_test 釋放探針後 `verify_com4.ps1` 為 `OVERALL: PASS`。Serial_Plotter 釋放後 COM4 驗證 6.8 秒，`OVERALL: PASS`，`probe_owner` 回到 `free`。

### 沒有變快的部分

- gmake 編譯時間。`ccs_build` 仍是跑 gmake。
- Flash 演算法本身。暖機後約 15 秒對 17 秒。
- `verify_*.ps1` 收資料的時間。Serial_Plotter 的串流檢查仍要 6.8 秒。

### 省掉的 Agent 回合

這些以前是多次工具呼叫，單次呼叫本身往往不到一秒，貴在來回。

| 以前                                               | 現在                                              |
| ------------------------------------------------ | ----------------------------------------------- |
| 每次建置對 `.map` 的 ENTRY POINT、ramfunc、UNPLACED 各搜一次 | 含在 `ccs_build`／`ccs_map` 的同一次回傳                 |
| 每次燒錄前後查 2–4 次 process，確認誰佔著 XDS110               | 含在 `ccs-env` 的那 4 秒                             |
| 每種建置或 DSS 錯誤讀 log 2–4 個回合                        | 已知句型由規則立即判；認不得的文字才問 Jev（p50 約 220–250 毫秒）       |
| 子代理中斷後翻 transcript 和終端機（有一次用了 8 次呼叫）             | 讀 `results/ccs_runs.jsonl` 最後一行（時間、程式、PC、成敗、耗時） |

daemon 佔著探針時，`dss.bat` 印出 Error -260，字面是 “no XDS110”。探針仍在裝置管理員時，規則判成 `probe_busy`。`ccs_release` 之後同一支 `dss.bat` 可以連上。

## Jev 判斷得如何

模型固定為 `jev-1.13.0`。Choice 信心門檻 0.8，Noul 是 0.85 判是、0.15 判否。低於門檻就退回 L0。

### 示波器 A–E（2026-10-07）

36 個 fixture。`--jev auto` 與 `--jev always` 最終都是 36/36。`--jev off` 是 35/36：C10 只有自由文字的預期（「QSEL=2 應該延遲約 33 µs」），L0 判斷不了，Jev 的 Noul 以 0.05 判成不符，抓到舊 build。

| bridge   | 案例  | 最終答案 | Jev 自己的答案   | Jev 錯且信心 ≥ 0.8          |
| -------- | --- | ---- | ----------- | ----------------------- |
| frame    | 12  | 12   | 7–9（三次重跑不同） | 0                       |
| diagnose | 10  | 10   | 6–7         | 2（D03、D10：把觸發準位被夾限當成根因） |
| flash    | 10  | 10   | 7           | 2（C05、C10 的 Choice 題）   |
| menu     | 4   | 4    | 3–4         | 0                       |

連續 102 次 Jev 呼叫：p50 243 毫秒、p95 382 毫秒、最慢 567 毫秒。第一次因為建立 TLS，約 530 毫秒。每次約 300–1,100 個 input tokens。

Jev 讀文字時信心多在 0.9–1.0 且答對（燒錄 log、畫面上的文字筆記）。純數值的畫面（置中、是否截斷）信心 0.2–0.7，同一輸入重跑答案會變。因此 `frame_ask` 設成 `notes_only`、`menu_ask` 設成 false：這兩類在 `auto` 模式直接用 L0，每次省下約 250 毫秒。

把門檻放進 state 之後，frame 上 Jev 自己的答對從 6/12 升到 8/12。D03 曾以 0.94 把探棒倍率設錯的症狀答成觸發準位超出範圍；規則已能直接判 `probe_ratio`，最終答案以規則為準。

### 建置與 DSS（2026-10-07 三次，2026-10-08 改規則後再跑一次）

三次 `--jev always` 只跑 build 與 dss（`results/replay_always_20261007_234606.json`、`234612.json`、`234619.json`），三次結果相同：

| bridge | 案例  | 最終答案       | Jev 自己的答案 | Jev 錯且信心 ≥ 0.8 | 延遲                    |
| ------ | --- | ---------- | --------- | -------------- | --------------------- |
| build  | 13  | 13/13      | 12/13     | 0              | p50 248 毫秒、p95 371 毫秒 |
| dss    | 9   | 8/9（漏 G07） | 8/9       | 0              | p50 219 毫秒、p95 246 毫秒 |

G07 是「Trouble Writing Memory」。Jev 答 `flash_fail`，信心 0.76，低於 0.8，所以那三次退回 `other_error`。這句是已知的 TI 訊息，已改由 L0 直接判成 `flash_fail`。2026-10-08 00:10 的完整 replay（六個 bridge，`results/replay_always_20261008_001059.json`）沒有漏判；dss 9/9 都由 L0 回答。同一次裡 Jev 對 G07 仍是 `flash_fail`，信心 0.70。

`auto` 模式下 Jev 補上的建置案例是 F12：GNU 風格的找不到 header，規則的 cl2000 句型對不上，Jev 判成 `include_path`。L0 已有結論時仍以 L0 為準，這兩筆 Jev 答錯但沒被採用：

- F11（Google Drive 路徑卡住）：Jev 以 0.42 答成 `other_error`，L0 是 `slow_path`。
- G04（daemon 佔探針時的 Error -260）：Jev 以 0.71 答成 `no_probe`，L0 是 `probe_busy`。

## 截圖判讀：Jev 1.14 看圖 vs Opus 5.5 high（2026-10-15）

沒有示波器，所以用舊截圖離線比較。這一節**不是硬體實測**。

### 條件

- 模型：`jev-1.14.0`（每張 3 次）、`jev-1.13.0`（每張 1 次，用來確認 1.13 也收圖），SDK `typesafe-sdk` 0.7.5，請求帶 `TypeSafe-Danger-Zone-Images: true`；Opus 用 Claude Code CLI 跑 `claude-opus-5-5`、`--effort high`，每張 1 次、依序執行。
- 題目：兩邊相同，`questions.screen_image_questions(require_white=True)`。三題：`menu_visible`（選單、游標框或對話框有沒有開著）、`report_ready`（能不能直接存成報告截圖）、`next_fix`（FRAME_FIXES 加上 `white_background`，選一個）。
- 公平性：Opus 只看到改名成 `screen.png` 的圖，在空資料夾執行，只開放 Read 工具，不讀倉庫的 CLAUDE.md。Jev 只收到圖片本身。
- 資料：66 張不重複截圖。17 張白底（13 張 RIGOL Timer、4 張 Keysight），49 張 RIGOL 黑底（GPIO 實驗報告圖與存檔）。其中 25 張開著選單或游標框。私人存檔的圖片沒有放進倉庫。
- 標註：由 Claude（Opus 5.5）標，依據有截圖旁的 `frame` JSON、`rules/menu.py` 像素統計與目視；使用者審核後加了一條規則：**報告截圖必須白底**，所以黑底一律「不可存」，下一步要能指出 `white_background`。標註鎖定在 `results/image_eval/labels.json`（sha256 `a3daff36…`）後才開跑。
- 限制：標註者和參賽的 Opus 是同一個模型，Opus 的分數可能偏高；樣本少，且 53/66 張答案是「不可存」。

指令：`python bench/image_eval.py --jev jev-1.14.0:3 --jev jev-1.13.0:1 --opus claude-opus-5-5:high`，結果在 `results/image_eval/20261015_171946/`（本機，不進 Git）。

### 結果

| | 選單開著 | 可存成報告 | 其中白底 17 張 | 下一步 | 耗時 p50／p95 | 費用 |
| --- | --- | --- | --- | --- | --- | --- |
| Jev 1.14（3 次合計） | **198/198** | 165/198 | 18/51 | 3/198 | **209／272 ms** | 約 2,500 input tokens／張 |
| Jev 1.13 | **66/66** | 64/66 | 15/17 | 16/66 | 219／255 ms | 同上 |
| Opus 5.5 high | **66/66** | **66/66** | **17/17** | **59/66** | 9.3／13.5 s | 共 US$1.56（約 0.024／張） |

- **選單有沒有開：三者全對。** Jev 1.14 有 161/198 次信心達門檻（≥0.85 或 ≤0.15），達門檻的全部答對。
- **能不能存成報告：Jev 1.14 實際上不可用。** 黑底 147/147 對，但白底的可存畫面幾乎都答「不可存」（機率 0.2–0.5）；分數高是因為大部分答案本來就是「不可存」。1.13 在白底反而比較好（15/17）。達門檻的回答都對（1.14：139/139；1.13：22/22）。
- **下一步：Jev 兩版都不可用。** 1.14 主要答 `move_trigger`／`fix_offset`／`fix_probe`，信心平均 0.19，從未選 `white_background`，也沒有一次達到 0.8 門檻，在工具裡會全部退回 L0。Opus 錯的 7 張都選了 `shift_timebase`（游標框或放大畫面，事件不在中央），信心 0.45–0.6。
- **一致性：** Jev 1.14 三次答案完全相同的只有 35/66 張，差異幾乎都在 `next_fix`。
- **時間：** Jev 比 Opus 快約 44 倍（整段時間）。Opus 每張 6.5–14.5 s，其中 CLI 啟動加一個簡單回合約 3.6–4.3 s；只看 API 時間是 p50 7.3 s。每張都是 2 個回合（讀圖、回答）。
- **1.13 也收圖：** 官方 Models 頁寫所有模型只收文字，但 1.13 帶上 header 一樣可以收圖。

### 文字 fixture 換成 1.14 後（同日）

`bench/replay.py --jev always`，58 題（`results/replay_always_20261015_170215.json`）：最終答案 58/58。Jev 自己的答案：frame 9/12、diagnose 6/10、flash 7/10、menu 4/4、build 13/13、dss 8/9。和上面 1.13 的數字相比持平或稍好；flash 的 Choice 題沒有再出現信心 ≥0.8 卻答錯的情況，diagnose 仍是 2 題。p50 170–190 ms。沒有看到退步；但因為下面的看圖結果，同日改回 `jev-latest`。

### 結論

2026-10-15 使用者決定不把圖片交給 Jev：取景的兩題不可用，選單判斷規則本來就能處理。看圖的程式（`jev.images` 開關、`questions` 的看圖題目、`bench/image_eval.py`、`tests/test_jev_images.py`）已移除，SDK 改回 0.7.2，模型改回 `jev-latest`。本機的 `results/image_eval/` 保留標註與原始結果，不進 Git。

## 數字從哪來

| 內容                             | 檔案                                                      |
| ------------------------------ | ------------------------------------------------------- |
| Daemon 每一步的毫秒                  | `results/ccs_runs.jsonl`                                |
| 2026-10-07 build／dss 三次 replay | `results/replay_always_20261007_2346*.json`             |
| 2026-10-08 六個 bridge、沒有漏判      | `results/replay_always_20261008_001059.json`            |
| 示波器 36 題、102 次延遲、硬體注入          | [README.md](README.md) 的 Replay 與硬體驗證                   |
| 冷啟動 48 秒、47 秒、42–82 秒、38 秒搜尋   | Cursor 終端機 `150308`、`253247`、`533191`–`533198`、`253244` |
