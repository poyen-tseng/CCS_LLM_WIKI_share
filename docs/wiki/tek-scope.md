# Tektronix TDS2014B 遠端控制與截圖

用 USB 控制 Tektronix TDS2014B（4 通道、100 MHz、每筆 2500 點，韌體 `FV:v22.01`）。下面的規則都來自 2026-10-22 的實測：四支 10:1 探棒都接前面板 PROBE COMP（約 5 V、1 kHz 方波），沒有接 F280049C。MCP 伺服器見 [tools/MCP/scope-tek-tds2000b](../../tools/MCP/scope-tek-tds2000b/README.md)。

這台沒有函數產生器，也沒有 LAN。`jev-scope`（[jev.md](jev.md)）自 2026-11-03 起支援這台（`scope.model = "tek"`），見下方 [jev-scope 加速模組](#jev-scope-加速模組tek2026-11-03)。

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

## jev-scope 加速模組（tek，2026-11-03）

`tools/JEV_accel` 以 `SCOPE_MODEL=tek`（或 `config.local.json` 的 `{"scope": {"model": "tek"}}`）使用這台。程式在 `scope_io.py` 的 `TekDialect`／`TekScope`，USB 存取重用 `tools/MCP/scope-tek-tds2000b/tek.py`。JEV `.venv` 要另裝 `pip install -e ".[tek]"`（PyVISA、PyVISA-py、pyusb、libusb-package，版本與 MCP 相同）。通道寫 `CH2` 或 `CHAN2` 都可以。

**同一時間只有一個程序能開這台的 USB。** `tek` MCP 一旦連過就一直占著；JEV 開不了時，先結束那個 MCP 的會話。

實測（F280049C `TIMER0_EX`，GPIO0 → J8 Pin 80 → CH2 10X 探棒）得到、並已寫進程式的規則：

| 項目 | 實測 | JEV 的處理 |
| --- | --- | --- |
| offset 換算 | 中心電壓 = −`CH<n>:POS` × V/div；JEV 規則的 offset = −中心電壓 | `position = offset ÷ V/div`。`TekDialect.cmd_offset` 需要當時的 V/div，呼叫端都會傳 |
| 位置與觸發準位的步進 | `CH2:POS -1.65` 讀回 `-1.64`（0.04 格）；觸發準位 0.02 格（1 V/div 時 0.02 V；1.65 V 讀回 1.64 V） | 讀回比對容許 0.021 |
| V/div | 0.6、0.7、1.5 等細調值直接接受 | 沒有 vernier 指令（回空字串，呼叫端會略過） |
| 時基 | 1-2.5-5 序列，5 ns～50 s/div；`2e-4` 變成 `2.5e-4`，`2e-9` 變成 `5e-9` | `cmd_tdiv` 先往上取到 1-2.5-5 |
| 波形 `CURV?` | int8，每格 25 碼，螢幕是 ±100（±4 格）。置中的 0–3.3 V 是 −41～43；0 V 在螢幕下方 0.5 格時讀 −112，電壓仍正確（ADC 涵蓋約 ±5.1 格）；超過時飽和在 +127 | `raw + 128` 轉成 0–255，另外把 \|碼\| ≥ 99（碰到螢幕上下緣）設成 0／255。所以規則的 `clipped`（≤3／≥252）代表「截圖上被切掉」，不只是 ADC 飽和 |
| VTOP／VBASE | 韌體沒有這兩項 | 從同一筆 2500 點紀錄取：高於／低於極值中點的樣本中位數（忽略過衝）。VMAX／VMIN／VPP 也從紀錄算，一次 `CURV?` 約 0.5 s，取代每項約 0.65–1.1 s 的 `MEASU:IMM` |
| PDUT | 韌體沒有 | `PWI ÷ PERI × 100`，單位是 %（RIGOL 回的是比例，`timer_flow` 只對 RIGOL 乘 100） |
| NORM 等觸發 | 2.5 Hz 方波每 0.4 s 才觸發一次 | `run_state` 判 WAIT 的觀察窗至少 0.6 s（100 ms/div 時 2.25 s），否則跑著的 Timer 訊號會被當成 WAIT |
| diagnose 偷看電平 | 100 ms/div 以上切 AUTO 會進 SCAN 捲動，半滿的紀錄讀到 VMAX 3.36／VMIN −3.48 V，建議出錯誤的 `TRIG:MAI:LEV -0.060` | 100 ms/div 以上改用 `TRIG FORC` 擷取一筆完整紀錄（不用還原）；較快時基仍暫切 AUTO，結束時切回 NORM |
| autoframe edge | 粗調 250 µs/div 量到 VMAX−VMIN 3.36 V；換到 250 ns/div 後邊緣過衝讓擺幅變 3.76 V，0.5 V/div 時碰到螢幕邊緣 | 套用計畫後在新時基再讀一次，截斷或超過 7.6 格就放大一級 V/div（例：0.5 → 0.6），中心不變。只對 `tek` 啟用 |
| 選單 | 側選單在格線右邊自己的欄位（x 262–319），不會蓋到波形；SCPI 無法關閉選單或訊息框，也沒有 `MESS:` 指令 | `menu.kind = "tek_graticule"`：先遮掉格線固定圖樣（x%5==0、y%25==12、中心軸、外框刻度），再依背景亮度數格線區的中性文字／框線列（原生白底 `HARDC:INKS ON` 數深色中性列，黑底 `INKS OFF` 數亮白列）。實際畫面 0 列；合成的訊息框測試為開。`menu.in_frame=false`：`check_frame` 不截圖（一張 8.5 s），疊圖檢查交給 `jev_menu_visible` 或最後的報告截圖 |
| 量測疊圖 | `MEASU:IMM` 不會畫在螢幕上 | `clear_meas = None` |
| 每次寫入 | 每個寫入 0.08–0.64 s，值沒變也一樣（`CH2:COUP DC` 0.64 s、`TRIG:MAI:EDGE:COUP DC` 0.54 s）；查詢約 0.06 s | `TekScope.ensure()` 先讀，只寫不同的設定 |
| 長的串接指令 | 一個訊息串 18 個指令後 USB 卡死，連 `*IDN?` 都逾時 | 不串接。卡死時用 USBTMC 類別請求 `INITIATE_CLEAR`（bRequest 5，再以 6 查到完成）就能恢復，不必重開機；pyvisa-py 沒有 device clear |
| 連續截圖与原生白底 | 同一個 USB 會話緊接第二次 `HARDC STAR`，有一次讀取逾時；黑底截圖若做 RGB 反相會把深藍外框 `(0,0,170)` 變成亮黃外框 `(255,255,85)`、CH2 青色變成紅色 | `TekScope.screenshot_bmp(white=True)` 預設使用硬體原生白底（`HARDC:INKS ON`，外框全白、CH1 橘黃、CH2 青色），`timer_flow.py` 直接存檔、不做 `ImageOps.invert`；逾時時重開會話再試一次 |

`diagnose` 的 `fix` 會改寫成這台的語法（`CH2:PRO 10`、`TRIG:MAI:LEV 1.680`、`TRIG:MAI:MOD NORM` + `ACQ:STOPA SEQ` + `ACQ:STATE RUN`）。`autoframe` 不改觸發來源；量 CH2 前先把 `TRIG:MAI:EDGE:SOU` 設成 CH2。

### 實機驗證（2026-11-03）

條件：LAUNCHXL-F280049C 以 `ccs-load TIMER0_EX` 載入 RAM 執行；CH2 10X 探棒接 J8 Pin 80（GPIO0，2.5 Hz 方波）；CH1 接 J8 Pin 79（GPIO1），本次未使用。每一步都是新的 CLI 程序（等同一次 agent 工具呼叫），`--jev off`。原始紀錄在 `tools/JEV_accel/results/tek_hw_20261103_v2/hw_log.json`（不進 Git）。

| 注入 | 結果 | 耗時 |
| --- | --- | --- |
| `pytest -m hw`（SCOPE_MODEL=tek） | 3/3 通過 | 24 s |
| CH2 觸發 NORM、準位 5 V → `check-frame --view period` | `diagnose`（WAIT，不讀舊資料） | 6.7 s |
| `diagnose --level-set 5` | `trig_level_out_of_range`，`fix: TRIG:MAI:LEV 1.680`；之後觸發模式讀回 `NORMAL` | 6.6 s |
| `CH2:PRO 1` → `diagnose` | `probe_ratio`，`fix: CH2:PRO 10` | 6.5 s |
| 起點：探棒 1×、0.2 V/div、位置 +3 格、1 µs/div → `autoframe --channel CH2` | 先改探棒 → 粗調 → 計畫 0.5 V/div → 驗證放大到 0.6 V/div、`CH2:POS -2.76`、5 ns/div；接著 `check-frame` 回 `ready=true`（center_err 0.08 格、edge 0.23 格） | 11.8 s |
| 位置 +1 格 → `check-frame` → `--apply` → `check-frame` | `fix_offset`（clipped，提示重新取景）→ apply 走 autoframe → `ready=true` | 6.6 s／12.8 s／6.4 s |
| Timer 設定、單次擷取 → `check-frame --view period` | `ready=true`，2.5 個週期、center_err 0.04 格 | 5.9 s |
| 0.2 V/div、中心 1.5 V（截斷）→ 同上 | `ready=false`、`clipped=true`；韌體在截斷時拒絕 PERI（9.9E37），所以標籤是 `diagnose`，並附「截斷、恢復已知垂直設定」提示 | 5.7 s |
| NORM 連續執行（100 ms/div）→ 同上 | `ready=true`，沒有誤判 WAIT | 7.0 s |
| `menu`、`menu --hide` | `visible=false`（0 列）、`hide_supported=false`，沒有送任何按鍵 | 9.6 s |

第一輪（`tek_hw_20261103/`）抓到兩個問題並已修正：100 ms/div 下 diagnose 建議 `-0.060 V`（SCAN 半滿紀錄），以及 autoframe 後因過衝而截斷、`--apply` 不收斂。

結束時把 CH2、時基、觸發設定還原成開始前的狀態，與開始前的 `tek_status` 比對沒有差異；`HARDC` 設定維持 INKS ON、JPEG。

### Timer 流程（baseline vs optimized）

`bench/timer_flow.py --mode baseline|optimized --runs 5 --channel CH2`，`SCOPE_MODEL=tek`。每次都含增量建置、RAM 載入與校驗、設定與讀回、新的單次擷取（NORM、100 ms/div）、period 畫面閘門、七項量測和最終截圖。兩批各 5 次全部通過驗收（頻率、週期、高低脈寬 ±1%，PDUT 49–51%）。

| 項目（5 次中位數） | baseline | optimized |
| --- | --- | --- |
| 完整流程 | 33.199 s（32.861–33.873） | **21.015 s**（20.941–21.556） |
| 建置／載入 | 0.079／1.981 s | 0.085／1.982 s |
| 設定與讀回 | 6.520 s | 3.559 s |
| 單次擷取 | 2.083 s | 1.756 s |
| 畫面檢查 | 4.312 s | 2.790 s |
| 七項量測 | 4.162 s | 1.524 s |
| 最終截圖與核對 | 8.143 s | 8.142 s |
| Scope 連線數 | 5 | 1 |
| 明確等待 | 3.65 s | 1.50 s |

中位數加速 **1.58 倍**，耗時減少 **36.7%**。optimized 的差別：同一條 USB 連線（每次開啟約 1.2 s）、設定只寫有變的（`ensure`）、STOP 後不再等 1.5 s、PER／VTOP／VBASE 沿用畫面檢查時同一筆凍結紀錄的值、PDUT 由同一筆的 PWID／PER 算（不再量兩次）。建置、載入、硬體擷取和 8.1 s 的 hardcopy 沒有變快。量測值：FREQ 2.50000–2.50003 Hz、PER 0.39999–0.40000 s、PWID 0.20001 s、NWID 0.19998–0.19999 s、PDUT 50.002–50.003 %、VTOP 3.32 V、VBASE 0.04 V。`scope_commands` 計數不含 `TekScope.measure` 內部直接送的 USB 指令，所以兩邊不能直接比指令數。

原始資料：`tools/JEV_accel/results/tek_timer_baseline_20261103/`、`tek_timer_optimized_20261103/`、`tek_timer_comparison_20261103.json`。報告截圖一律使用預設的硬體原生白底（`HARDC:INKS ON`、`white=True`、`tek_screenshot(white_background=True)`），禁止對黑底截圖做 `ImageOps.invert` 反相。

## 尚未做

- 游標（`CURS:`）工具；Keysight 的 `ks_markers` 在這台沒有對應的 MCP 工具。
- 選單偵測的「開啟」狀態只用合成影像驗證：沒有 SCPI 能在畫面上叫出訊息框，需要有人按 HELP 等鍵時再補一張真實截圖校準。
- `TIMER_HW`（CH1 100 Hz、CH2 1 kHz ISR 脈衝）還沒用 JEV 量過。
- `autoframe` 的過衝驗證只在 `tek` 啟用；RIGOL／Keysight 是否也需要，要在那兩台上實測。
