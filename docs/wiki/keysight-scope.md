# Keysight DSO-X 4034A 遠端控制與截圖

用 LAN 控制 Keysight InfiniiVision DSO-X 4034A（4 通道、350 MHz，`*IDN?` 顯示 AGILENT），截出置中、有游標的白底波形圖。下面的規則都來自 2026-10-12 用內建 Demo 訊號自我回授的實測結果。這次沒有接 F280049C。MCP 伺服器見 [tools/MCP/scope-keysight-dsox4000](../../tools/MCP/scope-keysight-dsox4000/README.md)，腳本在 [tools/MCP/scope-keysight-dsox4000/tools](../../tools/MCP/scope-keysight-dsox4000/tools)。

截圖、診斷、選單與自動取景先照 [jev.md](jev.md) 呼叫 `jev-scope`（`tools/JEV_accel/config.json` 的 `scope.model` 是 `keysight`）。`ready=true` 才截一張圖。

回到 [README.md](README.md)。RIGOL 的對應規則見 [rigol-scope.md](rigol-scope.md)。

## 連線

IP、DNS、面板與 Windows 網卡設定統一見 [示波器網路設定](scope-network-setup.md)。倉庫預設 Keysight `192.168.137.60:5025`，電腦 `192.168.137.1/24`。

- `keysight` MCP／`keysight.py` 的 `KS_ADDR` 覆寫工具位址；PyVISA 連線未使用讀入的 bind，依 Windows 路由。`KS_BIND` 用於 socket 腳本；JEV 使用自己的 `SCOPE_BIND`。
- 2026-10-12 實測時 5024（telnet）、111（VXI-11）、4880（HiSLIP）、80（網頁）也開著。VXI-11 用來解除解析器卡住，見「不要在等觸發時讀資料」；這不代表目前各埠都可用。
- 網路設定使用面板；本倉庫紀錄未提供可用的 `:LAN` 指令。先查本次 `*IDN?`，不能依舊紀錄認定已連線。

## 選配

`*OPT?`：MEMUP、FRA、PWR、SGM、MASK、EDK、ADVMATH、DVM、RML、USBPD、D4000PWRA。

- **沒有 WaveGen（WGN）**。`:WGEN` 開頭的指令都回 `-241,"Hardware missing"`。
- 有 EDK，所以前面板 Demo 1／Demo 2 端子可以輸出訓練訊號，當作自我測試的訊號源。

## 自我回授接線與 Demo 訊號

CH1 探棒接 Demo 1，CH2 探棒接 Demo 2，接地夾夾旁邊的接地片，兩支都是 10:1 被動探棒（會自動偵測成 10:1）。`:DEMO:FUNC <名稱>`、`:DEMO:OUTP 1`，或用 `ks_demo`。輸出時畫面上方會出現橘色「示範模式」橫幅，它不在格線區內，不影響截圖判斷。

| 名稱 | 實測／用途 |
| --- | --- |
| `CLK` | 只有 Demo 1。約 3.57 MHz、0–2.1 V 方波，上升時間約 39–45 ns。拿來練邊緣置中與 10–90 % 游標 |
| `GLIT` | 時脈串之間夾一個窄脈衝。GLITCH 觸發 `LESS 60e-9`、`POS`、準位 1.05 V 可以抓到 |
| `PHAS` | Demo 1、Demo 2 各一個約 1 kHz 正弦，相差約 92°。拿來測雙通道的 `DEL`、`PHAS` |
| `RUNT`、`SING`、`BURS`、`TRAN`、`SHOL` | 欠幅、單次、叢發、轉換時間、建立／保持 |
| `SIN`、`NOIS`、`RING`、`AM`、`LFS`、`FMB`、`HARM`、`COUP`、`ETE`、`RFB` | 其他波形 |

韌體 07.30 拒絕 `MSO`、各種序列匯流排、`SQU`、`PULS`、`RAMP`、`DC`（`-220`／`-224`）。

## 和 RIGOL 不同的 SCPI

| 項目 | Keysight DSO-X 4034A | RIGOL MSO5104 |
| --- | --- | --- |
| 通道 offset | 螢幕**中心**的電壓。0–3.3 V 置中用 `:CHAN1:OFFS 1.65` | 正負相反，用 `-1.65` |
| 時基 | `:TIM:SCAL`、`:TIM:POS`（中心點的時間）、`:TIM:REF CENT` | `:TIM:MAIN:SCAL`、`:TIM:MAIN:OFFS` |
| 最快時基 | 2 ns/div（1 ns 回 `-222`） | 5 ns/div |
| 觸發狀態 | 沒有 `:TRIG:STAT?`，`:RSTate?` 不存在。用 `:OPER:COND?`（bit3 Run）加 `:TER?` 判斷，見下節 | `:TRIG:STAT?` |
| 量測 | `:MEAS:VTOP? CHAN1`、`VBAS`、`RIS`、`FALL`、`VAV DISP,`、`VRMS DISP,DC,`、`DUTY`；雙通道 `:MEAS:DEL? CHAN1,CHAN2`、`PHAS` | `:MEAS:ITEM? VTOP,CHAN1` |
| 量測無效 | `+99E+36`（≥ 9.9e37 視為無效） | 9.9E37 |
| 清量測 | `:MEAS:CLE` | `:MEAS:CLE ALL` |
| 波形換算 | `V = (raw - yref) * yinc + yorigin`，yref = 128，yorigin = 通道 offset | `(raw - yorig - yref) * yinc` |
| 畫面上的 raw | 8..248；超出畫面讀成 1 或 255，所以 ≤3／≥252 的截斷規則照用 | 同 |
| NORM 波形點數 | `:WAV:POIN 1000`，快時基時實際較少（20 ns/div 只有 640 點） | 固定 1000 |
| 截圖 | `:DISP:DATA? PNG,COL`，800×632 PNG。區塊後面多一個換行要讀掉 | BMP，要另外轉 PNG |
| 白底 | `:HARD:INKS 1`（Ink Saver）。黑白切換要約 2 秒 | invert 參數 |
| 游標 | `:MARK:MODE MAN`／`WAV`、`:MARK:X1P`、`X2P`、`Y1P`、`Y2P`、`X1Y1`、`X2Y2`、`XDEL?`、`YDEL?` | `:CURS:TRACk:*` |
| 觸發準位超出範圍 | 回 `-222` 拒絕，準位不變 | 夾到邊界 |
| 錯誤佇列 | `+0,"No error"` | `0,"No error"` |
| 未知查詢 | **完全不回應**，只會逾時；錯誤佇列留 `-113` | 回錯誤 |
| 關選單 | 沒有 SCPI 能關對話框，要請人按 [Back] | `:SYST:KEY:PRES MOFF`（切換） |

`:MEAS:xxx?` 查詢不會把量測項加到側欄。

## 觸發狀態怎麼判斷

`:OPER:COND?` 的 bit3（8）是 Run，bit5（32）是 Wait Trig。只靠 bit5 不可靠：同樣在 NORM 下持續觸發，一次讀到 0x18，另一次一直是 0x38；改設定之後 bit5 也會短暫清掉。所以驅動這樣判斷（字彙對齊 RIGOL，規則可以共用）：

- Run 位元為 0：`STOP`
- sweep 是 AUTO：`AUTO`（自動觸發也會設 `:TER?`，分不出真假觸發）
- sweep 是 NORM：先讀一次 `:TER?` 清掉舊的鎖存，0.25 秒內 `:TER?` 變成 1 就是 `TD`，否則 `WAIT`

## 不要在等觸發時讀資料

**sweep 是 NORM、沒有觸發（`WAIT`）時，任何波形或量測查詢（`:WAV:PRE?`、`:WAV:POIN?`、`:MEAS:VMAX?` …）都會卡住，而且卡住的是整台示波器的 SCPI 解析器，換新連線也一樣，直到下一個觸發。** 2026-10-12 把觸發準位設在訊號上方時重現了三次。

- `ks_*` 工具在 `WAIT` 時直接拒絕量測與擷取，並說明該怎麼做：停止（讀最後一次擷取）、強制觸發、修正準位，或改 AUTO。
- `:STOP` 之後量測與波形都能讀，用的是最後一次擷取。
- `:DISP:DATA?` 截圖與一般設定查詢在 `WAIT` 時不會卡。
- `jev_check_frame` 在 `WAIT` 時不讀資料，直接回 `diagnose`，不會把已經 arm 好的單次觸發弄掉。`jev_diagnose_capture` 與 `jev_autoframe` 會暫時切到 AUTO 讀即時電平，結束時改回 NORM，回報的觸發狀態仍是原本的 `WAIT`。
- 已經卡住時：`python keysight.py recover`（或 MCP 遇到逾時會自動做）。它開一條 VXI-11 連線送 device clear、`:TRIG:FORC`，約 0.3 秒恢復，錯誤佇列會留一筆 `+109,"No Data For Operation"`。

## 置中、游標與截圖的步驟

1. `ks_status` 看探棒（10:1）、通道、觸發與 `run_state`。
2. `jev_autoframe`：依實測 VTOP／VBASE 設 V/div（非標準檔位自動開 vernier）、offset（螢幕中心電壓）、觸發準位（實際擺幅的 50 %）與時基（上升時間跨 2 格，最快 2 ns/div）。Demo CLK 實測得到 0.4 V/div、`:CHAN1:OFFS 1.085`、20 ns/div。
3. `jev_check_frame` 回 `ready=true` 才往下。
4. 要定格：`ks_set_trigger(sweep="NORM")`，`ks_run_control("single", wait_s=2)` 回 `STOP`。
5. `ks_markers(auto="rise_10_90")`：從畫面波形在本機算 10 %／90 % 點，放上波形追蹤游標。實測 ΔX 39.5 ns，對照 `:MEAS:RIS?` 39.3 ns。`auto="swing"` 則把 Y 游標放在高低準位。
6. `ks_screenshot()`：白底 PNG。

不經 MCP 時，`tools/capture_edge.py` 一次做完 4–6，存成 `<prefix>_10_90.png` 與 `<prefix>_swing.png`。之後接 F280049C 時加 `--go-file`，搭配 `edge_run.js` 的 go 檔流程，`--center 1.65` 給 3.3 V GPIO。

## 選單／對話框偵測

Keysight 的軟鍵在底部（y 575–632），側欄在右邊（x 660–800），都在格線外。會弄壞報告截圖的是蓋在格線上的對話框，例如 LAN 組態。

黑底截圖上，對話框是**透明的**：只有外框、標題列和白字，波形看得到。所以偵測格線區（x 20–650、y 100–565）裡的白字：一列有至少 4 個亮且無色的像素（最小通道 ≥ 180、最大減最小 ≤ 25）就算一列。實測對話框開著 176–203 列，關著 0 列。門檻沿用 RIGOL：大於 80 列是開，小於 10 列是關。格線是 (50,50,50) 的實線，不會被算進去。

沒有 SCPI 能關對話框。`jev_menu_visible(hide=true)` 會回 `hide_supported=false`，這時請使用者按 [Back]。
