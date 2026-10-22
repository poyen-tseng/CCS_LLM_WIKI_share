# Tektronix TDS2014B 遠端控制與截圖

用 USB 控制 Tektronix TDS2014B（4 通道、100 MHz、每筆 2500 點，韌體 `FV:v22.01`）。下面的規則都來自 2026-10-22 的實測：四支 10:1 探棒都接前面板 PROBE COMP（約 5 V、1 kHz 方波），沒有接 F280049C。MCP 伺服器見 [tools/MCP/scope-tek-tds2000b](../../tools/MCP/scope-tek-tds2000b/README.md)。

這台沒有函數產生器，也沒有 LAN。`jev-scope`（[jev.md](jev.md)）目前只支援 RIGOL 與 Keysight，還不能用在這台。

回到 [README.md](README.md)。RIGOL、Keysight 的對應規則見 [rigol-scope.md](rigol-scope.md)、[keysight-scope.md](keysight-scope.md)。

## 連線：USB、WinUSB 與 pyvisa-py

後面板 USB 裝置埠接電腦。示波器列舉為 `USB\VID_0699&PID_0368`（USBTMC 類別 FE/03/01）。Windows 10 沒有內建 USBTMC 驅動，裝置管理員會顯示錯誤碼 28（沒有驅動）。本機也沒有 VISA runtime（沒有 `visa64.dll`）。

採用的做法是讓 pyvisa-py 直接用 libusb 存取，不必安裝 NI-VISA 或 TekVISA：

1. 以系統管理員執行 [Zadig](https://zadig.akeo.ie)（2026-10-22 用 2.9：簽章為 Akeo Consulting，來源是 `pbatard/libwdi` 的 GitHub release）。
2. Options → List All Devices，選「Tektronix TDS2014B」（USB ID `0699 0368`），目標驅動選 **WinUSB**，按 Install Driver。
3. 裝置管理員狀態變成 OK 後，`python -I tek.py list` 會列出 `USB0::1689::872::<序號>::0::INSTR`。pyvisa-py 用十進位寫 VID／PID（1689 = 0x0699，872 = 0x0368）。

- 驅動綁的是這台示波器的這個 USB 序號。換一台 TDS 或換 VISA 廠商驅動，要重新設定。
- 要還原：裝置管理員 → 解除安裝這個裝置，並勾選刪除驅動程式。之後若安裝 TekVISA／NI-VISA，就改用它們的 USBTMC 驅動。
- `config.json` 的 `"resource": "auto"` 依 VID／PID 自動找到示波器，所以序號不會寫進倉庫。要固定位址時，寫在 `config.local.json`（git 忽略）或環境變數 `TEK_RESOURCE`。
- pyvisa-py 列資源時會對 TCPIP 提示要安裝 psutil／zeroconf；只用 USB，可以忽略（`tek.py` 已過濾這些提示）。

## 速度（USB，2026-10-22 實測）

| 動作 | 時間 |
| --- | --- |
| 一次簡單查詢（`*IDN?`、`CH1:SCA?`） | 50–120 ms |
| 複合查詢（`CH1?`、`TRIG:MAI?`） | 回應越長越慢，約每個欄位 50 ms；沒有比分開查快 |
| 第一次連線（列資源、開啟、`HEAD OFF`） | 約 1.5 s |
| `tek_status`（約 45 個查詢） | 約 4 s |
| 一個 `MEASU:IMM:VAL?` | 約 1.1 s（韌體計算時間）；PDUT／NDUT 要兩次 |
| `tek_capture`（2500 點） | 約 1.5 s |
| `tek_screenshot`（BMP 320×240） | 約 8.5 s |
| `AUTOS EXEC` | 約 8.5 s |
| 不支援的查詢 | 逾時 + 約 5 s。pyvisa-py 的 `_abort_bulk_in` 固定等 5 s，2 s 逾時實際約 7 s |

所以一次 `tek_status` 比多次 `tek_scpi` 好。複合查詢的回應若超過逾時，下一個指令會留下 `410 "Query INTERRUPTED"`。

## 和 RIGOL／Keysight 不同的 SCPI

| 項目 | TDS2014B | RIGOL／Keysight |
| --- | --- | --- |
| 錯誤 | `*ESR?` 之後讀 `ALLEV?`；沒有 `:SYST:ERR?` | `:SYST:ERR?` |
| 標頭 | 連線時送 `HEAD OFF`，回應才不會帶指令名稱 | 不帶標頭 |
| 垂直位置 | `CH<n>:POS` 單位是**格**；畫面中心電壓 = −位置 × V/div | RIGOL offset 與中心反號；Keysight `:OFFS` 是中心電壓 |
| 顯示通道 | `SEL:CH<n> ON|OFF` | `:CHAN<n>:DISP` |
| 單位／探棒 | `CH<n>:YUN "V"|"A"`；電壓探棒比 `CH<n>:PRO`，電流探棒比 `CH<n>:CURRENTPRO` | 自動偵測或 `:PROB` |
| 時基 | `HOR:MAI:SCA`、`HOR:MAI:POS`（中心相對觸發的時間） | `:TIM:SCAL`、`:TIM:POS` |
| 觸發 | `TRIG:MAI:TYP EDGE|PUL`、`TRIG:MAI:MOD AUTO|NORM`、`TRIG:MAI:LEV`、holdoff `TRIG:MAI:HOLDO:VAL`（`HOLD:VAL` 不認得） | `:TRIG:SWE` 等 |
| run／stop／single | `ACQ:STATE RUN|STOP`；single = `ACQ:STOPA SEQ` + `ACQ:STATE RUN`；run 要先 `ACQ:STOPA RUNST` | `:RUN`、`:STOP`、`:SING` |
| 強制觸發 | `TRIG FORC` | Keysight `:TRIG:FORC` |
| 波形 | `DAT:SOU`、`DAT:ENC RIB`、`DAT:WID 1`、`CURV?`；volts = (raw − YOF) × YMU + YZE；固定 2500 點 | `:WAV:DATA?`，點數可選 |
| 截圖 | `HARDC:FORM BMP`、`HARDC:INKS ON`、`HARDC STAR` 後讀 raw BMP，再轉 PNG | `:DISP:DATA?` 直接給 PNG |
| 函數產生器 | 沒有。自我測試用 PROBE COMP | RIGOL 有；Keysight 用 Demo 端子 |

## 觸發狀態

`TRIG:STATE?` 實測看過：`SCAN`（100 ms/div 以上的捲動模式）、`TRIGGER`、`READY`（NORM 模式在等觸發）、`SAVE`（已停止）。工具換成 RIGOL 用字：

- `ACQ:STATE?` 是 0 → `STOP`。
- `TRIG:MAI:MOD?` 是 AUTO → `AUTO`。
- NORM 模式下 0.25 s 內 `ACQ:NUMAC?` 有增加 → `TD`，否則 `WAIT`。

NORM 模式等不到觸發時（例如準位 8 V），`tek_measure` 與 `tek_capture` 會拒絕，以免把舊資料當成即時訊號；先 stop 再讀最後一筆。`force` 會擷取一筆，之後 NORM 繼續等，所以回傳 `run_state: WAIT`、`triggered: true`。

## 量測項目

韌體 v22.01 的 `MEASU:IMM:TYP` 只接受：`FREQ`、`PERI`、`PK2`、`MAXI`、`MINI`、`MEAN`、`RMS`、`CRMS`、`RIS`、`FALL`、`PWI`、`NWI`。`AMP`、`HIGH`、`LOW`、`POV`／`NOV`、`PDU`／`NDU`、`DELAY`、`PHASE`、`AREA`、`BURST`、`CMEAN` 都回 `102 "Syntax error"`。

- `tek_measure` 接受 RIGOL 名稱。`VRMS` 對應整筆紀錄的 `RMS`，`CRMS` 是一個週期的 RMS。
- `PDUT`／`NDUT` 是工具算的：`PWI`（或 `NWI`）÷ `PERI` × 100。
- 沒有雙通道的延遲與相位量測。
- 無法量測時回 `9.9E37`，工具改成 `invalid` 字串。
- 量測值之後會有警告事件：`541 "Low signal amplitude"`（波形太小）、`543 "Low resolution"`（上升時間比取樣間隔短）。它們不是錯誤，工具照樣回傳數值，並在 `warnings` 列出。

## 探棒與 Autoset 的坑（2026-10-22）

- 接上時 CH2–CH4 的探棒設定是 1×，但探棒實際是 10×，量到的是 1/10（0.56 V）。CH4 還被設成電流探棒（畫面標 `CH4 2.00A`，`CH4:YUN?` 回 `"A"`），讀數不對。用 `tek_set_channel(units="V", probe_ratio=10)` 改正，並看 `tek_status` 的 `units`、`probe` 欄位。
- `AUTOS EXEC` 會把四條線上下分開，各設 10 V/div。5 V 方波只佔 0.5 格，量測會帶 541 警告。要準確就改 2 V/div、`offset_v_center=2.8`。
- 截圖會暫改 `HARDC:FORM`、`HARDC:INKS`、`HARDC:LAY`，這些也是前面板 PRINT 鍵的設定，所以完成後會還原（實測原本是 JPEG）。

## 實測驗證（2026-10-22，PROBE COMP，四通道都 10× / 2 V/div）

| 項目 | 結果 |
| --- | --- |
| `tek_idn` | `TEKTRONIX,TDS 2014B,<序號>,CF:91.1CT FV:v22.01` |
| `tek_measure` CH1–CH4 | FREQ 999.99–1000.01 Hz；VPP 5.04–5.12 V；VMAX 5.04 V；VMIN −0.08–0 V；PDUT 49.995–50.003 % |
| `tek_capture` CH2 | 2500 點、1 MSa/s、v_pp 5.04 V，與 `tek_measure` 一致 |
| `tek_set_channel`／`tek_set_timebase`／`tek_set_trigger` | 回讀值都和設定相同（含 AC、BW 20 MHz、反相後還原） |
| EDGE NORM 準位 8 V | `WAIT`；量測與擷取拒絕；`force` 擷取一筆；stop 後可以擷取 |
| single（下降緣） | 1.1 s 內 `STOP`、`triggered: true` |
| PULSE 正脈衝（500 µs） | EQ 500 µs、INS 1 ms、OUT 200 µs → `TD`；EQ 200 µs、INS 200 µs、OUT 1 ms → `WAIT`；負脈衝 EQ 500 µs → `TD` |
| `tek_screenshot` | 白底與黑底 PNG 都正確，PRINT 設定還原 |
| `tek_scpi` | `*RST`、`ACQ:STATE RUN;FAC` 被擋；`FOO?` 約 7 s 回報 `113 Undefined header` |
| `tek_autoscale` | 約 13 s（含讀回狀態） |

脈衝寬度的 `WHEN` 參數：`EQ`／`NOTE`（在／不在設定值 ±5 % 內）、`INS`（比設定窄）、`OUT`（比設定寬）。`LESS`、`MORE` 不接受。極性要寫全字 `POSITIVE`／`NEGATIVE`（`POS`、`POSI` 都會回 102）。

## 尚未做

- 游標（`CURS:`）工具；Keysight 的 `ks_markers` 在這台沒有對應的 MCP 工具。
- 讓 `jev-scope` 支援這台。
- 接 F280049C 的實際訊號。
