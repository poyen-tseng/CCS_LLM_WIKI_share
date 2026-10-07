# JEV_accel：用 L0 規則加 Jev 加速 TI F280049C＋RIGOL MSO5104 的操作

這個專案把 `Oscilloscope_read\JEV_ACCELERATION.md` 列出的 A–E 橋段做成工具，並加上 CCS 的建置、燒錄與探針判斷。用法有三種：Python 套件、CLI、MCP server（`jev-scope`、`jev-ccs`）。

目標是讓 Agent **呼叫一次工具**，就拿到三樣東西：量測狀態、判斷結果、可以直接送出的 SCPI 或下一步指令。不必再「拍照 → 看圖 → 猜原因 → 再拍」。

加速幅度、Jev 的判斷正確率與延遲見 [JEV_PERFORMANCE.md](JEV_PERFORMANCE.md)。

## 三層分工

| 層 | 誰 | 什麼時候用 |
|---|---|---|
| L0 | `src/jev_accel/rules/*` 的確定性規則（約 0 ms） | 先跑。規則只有一個明確結論時，直接回傳 |
| L1 | Jev（TypeSafe，`typesafe-sdk` 0.7.2；Choice、Noul） | L0 判斷不了時才呼叫：多個違規要排優先、數值在門檻邊緣、需要讀自由文字 |
| L2 | Cursor / Claude 本身 | Jev 信心不足時、需要寫程式、需要看圖確認時 |

- 送給 Jev 的 state 只包含量測值和衍生指標，**不包含 L0 的結論**，所以 Jev 的判斷是獨立的。
- 每次呼叫 Jev 都會記錄到 `results/decisions.jsonl`，供日後檢查校準是否可信。
- 沒有 `TYPESAFE_API_KEY`，或 API 出錯時，自動退回 L0 的答案。

## 五個工具

| 代號 | CLI | MCP | 回傳 |
|---|---|---|---|
| A 截圖驗收 | `check-frame [--view edge\|delay] [--apply]` | `jev_check_frame` | `ready`、`next_fix`（見下方）、`scpi`、`metrics` |
| B 無觸發診斷 | `diagnose [--level-set V] [--pc 0x..]` | `jev_diagnose_capture` | `root_cause`（見下方）、`fix`、`fix_is_software` |
| C 燒錄狀態 | `flash-state <log> [--expected LO HI --measured X] [--expectation 文字]` | `jev_flash_state` | `state`（見下方）、`next_step` |
| D 側選單 | `menu [--hide]` | `jev_menu_visible` | `visible`；`--hide` 只有在選單開著時才按 MOFF |
| E 自動取景 | `autoframe [--mode edge\|delay --delay s] [--dry-run]` | `jev_autoframe` | 設定 probe、V/div、offset、觸發準位、時基，並讀回確認（只用規則） |

各工具的可能回傳值：

- **A `next_fix`**：`diagnose`、`fix_probe`、`hide_menu`、`fix_offset`、`change_vdiv`、`move_trigger`、`shift_timebase`、`clear_meas`、`rescreen`、`ok`
- **B `root_cause`**：`pc_in_bootrom`、`stale_build`、`probe_ratio`、`trig_level_out_of_range`、`sweep_mode`、`wiring`（`wiring` 永遠排最後）
- **C `state`**：`ok_running`、`waiting_go`、`at_bootrom`、`retry`、`fallback_dss`、`rebuild_needed`

所有命令都接受 `--jev auto|always|off`：
- `auto`（預設）：L0 判斷不了時才問 Jev。
- `always`：每次都問，用於 benchmark。
- `off`：完全不問。

```powershell
cd D:\code\_TI_CCS_no_chinese\JEV_accel
.\.venv\Scripts\python.exe -m jev_accel check-frame
.\.venv\Scripts\python.exe -m jev_accel flash-state path\to\terminal.txt --expected 2e-5 5e-5 --measured 2.4e-7
.\.venv\Scripts\python.exe -m jev_accel ping-jev
.\.venv\Scripts\python.exe -m jev_accel ccs-env
.\.venv\Scripts\python.exe -m jev_accel ccs-load Serial_Plotter
```

## 安裝與設定

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
setx TYPESAFE_API_KEY "<你的 key>"   # 設定後重開終端機、Cursor、Claude Code
```

- **`config.json`** 裡可以調：
  - `rigol_mso_dir`：重用 `CCS_LLM_WIKI_share\MCP\rigol-mso\tools\scope_lan.py`，它會 bind 192.168.137.1，避免走 Wi-Fi。
  - 示波器位址。
  - Jev 的 `model`。預設 `jev-latest`；第一次跑完 replay 後，建議改成回傳的實際版本並固定下來。
  - 各項門檻。
- **個人覆寫**放在 `config.local.json`，不進 git。環境變數 `SCOPE_ADDR`、`SCOPE_BIND` 的優先權最高。
- **MCP 已註冊**在 Cursor 使用者設定與 Claude Code 的 user scope：`jev-scope`（示波器）、`jev-ccs`（CCS）。
- **連線方式**：每個工具都用短連線（開啟、查詢、關閉），盡量不和長時間連線的 `scope` MCP 搶 5555 port。

## 測試

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not jev and not hw"   # 離線：L0 規則與 replay（Jev 關閉）
.\.venv\Scripts\python.exe -m pytest -m jev                    # 需要 TYPESAFE_API_KEY：用真的 Jev 跑 replay
.\.venv\Scripts\python.exe -m pytest -m hw                     # 示波器開機才會跑；只讀取，不改任何設定
.\.venv\Scripts\python.exe bench\replay.py --jev always         # 準確率、延遲 p50/p95、信心度、tokens
```

`tests/fixtures/*.jsonl` 共 36 個案例，每個都註明來源：
- Cursor transcript 的第幾行。
- `terminals\*.txt` 的哪份真實燒錄紀錄。
- 2026-10-07 在真實示波器上量到的狀態（D09、D10），以及 `tests/fixtures/menu_band_*.npy` 兩張真實選單截圖的像素。

少數是補齊類別用的合成案例，已標為 `synthetic`。

### Replay 結果（2026-10-07，模型 `jev-1.13.0`）

| bridge | 案例數 | 最終答案正確 | Jev 自己的答案正確（不論信心） | Jev 錯但信心 ≥ 0.8 |
|---|---|---|---|---|
| frame | 12 | 12 | 7–9（三次重跑結果不同） | 0 |
| diagnose | 10 | 10 | 6–7 | 2（D03、D10：都是把觸發準位被夾限當成根因） |
| flash | 10 | 10 | 7 | 2（C05、C10 的 Choice 題） |
| menu | 4 | 4 | 3–4 | 0 |

- **「最終答案正確」**：`--jev auto` 和 `--jev always` 都是 36/36；`--jev off` 是 35/36，因為 C10 只有 Jev 能解，見下方說明。
- **`pytest -m jev`**：3/3 通過。
- **延遲**：連續 102 次 Jev 呼叫，p50 243 ms、p95 382 ms、最慢 567 ms。第一次呼叫因為要建立 TLS 連線，約 530 ms。
- **tokens**：每次約 300–1,100 個 input tokens。

**從實測學到的事，以及對應的設計：**

1. **Jev 擅長讀文字，不擅長判斷數值。**
   - 讀燒錄 log（C01–C07）時，信心多在 0.9–1.0，而且答對。
   - 讀使用者寫的 notes（例如「RTIM 疊圖還在」「畫面沒刷新」）時，信心約 0.9，也答對。
   - 判斷純數值的畫面時（置中誤差、是否截斷），信心只有 0.2–0.7，同樣的輸入重跑三次，答案還會不一樣。
   - 因此 `config.json` 設 `frame_ask: "notes_only"`（畫面只在有 notes 時才問 Jev），以及 `menu_ask: false`（選單判斷不問 Jev）。這兩類在 `auto` 模式下直接用 L0，省下每次約 250 ms。
2. **把判斷標準一起放進 state，Jev 答得比較好。** 第一版只給數值、沒給門檻，Jev 在 frame 的答對數是 6/12；把門檻放進 `limits` 之後提升到 8/12。
3. **Jev 會在缺少關鍵資訊時信心很高地答錯。**
   - C08：第一版沒把 `expected_range` 放進 state，Jev 以 0.9 的信心回答 `ok_running`。
   - D03：Jev 以 0.94 的信心把觸發準位被夾限，當成根因。實際上那只是探棒倍率設錯造成的症狀。
   - 因此設下規則：**L0 已有明確結論時，一律以 L0 為準**。Jev 的意見只記錄下來，不採用。D03 的情況則改成 L0 直接判定 `probe_ratio`。
4. **Jev 在 `auto` 模式下真正發揮作用的地方是 C10**：沒有數值範圍、只有自由文字的預期描述（「QSEL=2 應該延遲約 33 µs」）。這時 Noul `behavior_matches_source` 以 0.05 判斷「不符」，正確抓到舊 build；L0 在這種情況下判斷不了。
5. **信心門檻維持 0.8**（Choice）以及 0.85/0.15（Noul）。重跑時答案會改變的案例，信心全都低於 0.5，所以門檻能把它們擋掉。

> ⚠️ 這批 fixtures 和規則是同時寫的，所以 L0 的高分有一部分是「照題目出規則」，主要用途是回歸測試。比較能反映實際情況的數字，是「Jev 自己的答案正確率」和下方的硬體結果。

## 硬體驗證

連不上示波器時，先照 [SCOPE_IP_SETUP.md](SCOPE_IP_SETUP.md) 檢查網路與 IP 設定。

### 已執行（2026-10-07，示波器 MSO5104）

**第一輪：CH1 沒接訊號（唯讀）**

| 項目 | 結果 |
|---|---|
| `pytest -m hw` | 3/3 通過 |
| `check-frame` | `diagnose`（畫面是平線），正確 |
| `diagnose` | 第一版答錯：L0 和 Jev（信心 0.89）都回答 `probe_ratio`。修正後回答 `wiring`（沒有訊號），倍率問題列在 `also_fix`。已加入 fixture D09 |

**第二輪：CH1 接前面板的探棒校正訊號（約 3 V、1 kHz；實體探棒是 10×）**

開始前先記下設定，結束後全部還原；還原後與原設定比對，差異為空。

| 注入 | 預期 | 實測 | 耗時 |
|---|---|---|---|
| E `autoframe`，起點是 PROB 1×、1 µs/div、觸發準位 0 V | 取到置中畫面 | **第一版做不到**：起點下 VTOP/VBASE 量不到，而且是在改探棒倍率之前就先量。修正後依序執行：先改探棒倍率 → 有截斷或量不到時做粗調 → 細調。結果 0.5 V/div、offset −1.481、觸發 1.481 V、1 µs/div，接著 `check-frame` 回傳 `ready=true` | 4.5 s |
| A `:CHAN1:OFFS 1.65` → `check-frame` | `fix_offset` | 標籤正確。但**第一版建議的數值反而更糟**：畫面被截斷時 VTOP/VBASE 量到的是螢幕邊緣，算出 0.2 V/div、offset −0.507，套用後仍然截斷。修正：截斷時不給數值，改成 `--apply` 直接重新取景。修正後 `--apply` 一次，下一次 `check-frame` 就回傳 `ready=true` | 2.8 s；`--apply` 7.8 s |
| B `PROB 1` + `:SING` @1.5 V → `diagnose --level-set 1.5` | `probe_ratio` | ✅ 規則直接判定 `probe_ratio`。示波器把 1.5 V 的觸發準位**默默夾成 0.398 V**，與 transcript 裡的 D03 情境相同。Jev（`always` 模式）又以 0.92 的信心答成觸發準位超出範圍，但規則已有明確結論，最終答案以規則為準。已加入 fixture D10 | 0.2 s |
| D 選單：關 → 按 MOFF → `menu` → `menu --hide` → `menu` | 關 → 開 → 只按一次 → 關 | **第一版偵測失效**：Measure 選單的邊框顏色是 (0,44,90)，wiki 的 b>120 門檻在開、關兩種情況都是 0 列，所以先前的「選單是關的」並沒有根據。改成 b>70 之後，開 340 列、關 0 列，整個流程如預期 | 0.3 s；hide 1.4 s |

**硬體測試發現的其他事：**
- **白底截圖**：`:DISP:DATA? ON,ON,PNG`、`ON,1,PNG`、`1,1,BMP24` 回傳的都是同一張黑底圖（平均亮度約 9），沒有任何 SCPI 錯誤。`Oscilloscope_read` 裡先前的截圖也都是黑底。所以 wiki 和 `scope` MCP 說明裡「invert ON 就是白底」在這台示波器上不成立，白底要靠截圖後把影像反相。
- **量測會改到畫面**：本工具用 `:MEAS:ITEM? X,CHANn` 量測時，示波器會把這些項目加到畫面下方的量測列；如果量的是隱藏的通道，還會把那個通道打開。報告截圖前請先 `:MEAS:CLE ALL`，再只加回需要的項目。
- **連線速度**：示波器正常連上時，網卡同樣顯示 1 Gbps（見 SCOPE_IP_SETUP.md 的更正）。

## CCS：建置、燒錄、驗證

示波器的 A–E 之外，Agent 操作 CCS 時最花時間的是每次 `dss.bat`／`run.bat` 都重開 DebugServer，以及反覆搜尋路徑、重讀 gmake log、對 `.map` 跑 `Select-String`。這部分由常駐的 debug session 和一次呼叫的工具處理。Jev 只讀規則認不得的錯誤文字。

`ccs_daemon.py` 用 CCS 內附的 Python 3.14 執行（venv 的 3.11 不能 import scripting），聽 `127.0.0.1:47011`。`ccs_client` 在 daemon 沒在跑時會把它拉起來。閒置 10 分鐘後釋放探針並結束。

| 工作 | CLI | MCP | 回傳 |
|---|---|---|---|
| 路徑與探針 | `ccs-env` | `ccs_env` | 工具路徑、XDS110、COM、`probe_owner`、daemon、各專案 `.out` |
| 建置 | `ccs-build <proj> [--clean]` | `ccs_build` | `result`（見下方）、`next_step`；成功時附 `.map` 檢查 |
| `.map` | `ccs-map <proj>` | `ccs_map_check` | entry、codestart、`.TI.ramfunc`、UNPLACED、`ok` |
| 燒錄 | `ccs-load <proj>` | `ccs_load` | `state`、PC、各步驟秒數 |
| 執行控制 | `ccs-ctl run\|halt\|reset\|restart\|status\|read_reg\|read_mem\|write_mem` | `ccs_run_control` | halted、PC 或記憶體值 |
| 釋放探針 | `ccs-release [--shutdown]` | `ccs_release` | 斷線；`--shutdown` 連 daemon 一起停 |
| 板級驗證 | `ccs-verify <proj>` | `ccs_verify` | 各項 `PASS`／`FAIL` 與 `OVERALL` |
| 建置檔差異 | `ccs-drift <proj> [--set-baseline]` | `ccs_project_drift` | 關鍵旗標是否改變 |
| 外部 DSS log | `ccs-dss <log>` | `ccs_dss_state` | `state`（見下方）、`next_step` |

- **建置 `result`**：`missing_compiler`、`slow_path`、`include_path`、`syntax_error`、`undefined_symbol`、`memory_placement`、`stale_build`、`other_error`、`ok`
- **DSS `state`**：`no_probe`、`probe_busy`、`target_power`、`connect_fail`、`flash_fail`、`run_fail`、`timeout`、`other_error`、`flash_ok`、`connect_ok`

`config.json` 的 `ccs` 區段記載 CCS 根目錄、編譯器、daemon port、以及 GPIO_EX1（RAM）、LED_test、Feedback_test、Serial_Plotter（後三者為 FLASH，後兩者有 `tools/verify_*.ps1`）。

### 板子實測（2026-10-07）

同一台已經暖機的電腦。歷史上每次 `run.bat` halt／load 是 42–82 s，`dss.bat` 冷啟動燒錄約 48 s。

| 步驟 | 耗時 |
|---|---|
| daemon `initScripting` | 3.74 s |
| LED_test 燒錄（reset + load + verify，含第一次 connect） | 15.2 s；使用者確認 LED4／LED5 交替 |
| halt／run／status（session 已連上） | 80 ms／13 ms／8 ms |
| Feedback_test 燒錄 | 15.0 s；`ccs_release` 後 `verify_com4.ps1` 為 `OVERALL: PASS` |
| 同一台暖機電腦上 `dss.bat` 連續燒錄兩次 | 17.1 s、16.9 s |
| GPIO_EX1 RAM 載入，再載一次 | 3.9 s、2.6 s |
| 還原 Serial_Plotter：`ccs-load` → `ccs-release` → `ccs-verify` | 燒錄 19.4 s（PC `0x8145d`，`.map` ok）；COM4 驗證 6.8 s，`OVERALL: PASS`；之後 `probe_owner` 為 `free` |

Flash 寫入本身大約 15 s，和暖機後的 `dss.bat` 接近。省下的時間是 halt、讀 PC、再次載入：不必為每一步重開 DebugServer。daemon 佔著探針時，`dss.bat` 印出 Error -260（字面是 “no XDS110”）；探針仍在裝置管理員時，規則判成 `probe_busy`。`ccs_release` 之後同一支 `dss.bat` 可以連上，`probe_owner` 回到 `free`。

### Replay（2026-10-07，`jev-1.13.0`，build 與 dss 各跑三次）

| bridge | 案例 | 最終答案 | Jev 自己的答案 | Jev 錯且信心 ≥ 0.8 |
|---|---|---|---|---|
| build | 13 | 13/13 | 12/13 | 0 |
| dss | 9 | 三次都是 8/9，漏的是 G07 | 8/9（G07 答對但信心 0.76） | 0 |

延遲與第一階段相近：build p50 248 ms、p95 371 ms；dss p50 219 ms、p95 246 ms。

Jev 讀得準的是它沒看過的編譯器文句（F12：GNU 風格的找不到 header，三次都判成 `include_path`）。L0 已經有結論時仍以 L0 為準：F11 的 Google Drive 路徑，Jev 以 0.42 答成 `other_error`；G04 的 Error -260，Jev 以 0.71 答成 `no_probe`。信心門檻維持 0.8。G07「Trouble Writing Memory」Jev 答對但只有 0.76，所以改由 L0 直接判成 `flash_fail`，`auto` 模式不再把這句交給 Jev。規則改完後的完整 replay（2026-10-08 00:10，六個 bridge、沒有漏判）裡，dss 9/9 都由 L0 回答；Jev 對 G07 仍是 `flash_fail`，信心 0.70。

`tests/fixtures/` 在原本 36 個 A–E 案例之外，另有 13 個 build、9 個 dss。

## 目錄

```
src/jev_accel/   jev.py、questions.py、rules/（含 build.py、ccs.py）、tools.py、tools_ccs.py、
                 cli.py、mcp_server.py（jev-scope）、mcp_ccs.py（jev-ccs）、
                 ccs_daemon.py、ccs_client.py、replay.py
tests/           fixtures、離線/jev/hw 測試
bench/replay.py  批次 replay 與統計
results/         decisions.jsonl、ccs_runs.jsonl、replay_*.json（不進 git）
```
