# Tektronix MSO2014 遠端控制

用 USB 控制 Tektronix MSO2014（MSO／DPO2000 系列：4 類比通道、100 MHz、每筆 125 k 或 1 M 點，韌體 `FV:v1.39`）。下面的規則都來自 2026-10-22 的實測：四支 10:1 被動探棒都接前面板 PROBE COMP（約 5 V、980 Hz 方波），沒有接 F280049C，也沒有接數位探棒 P6316。MCP 伺服器見 [tools/MCP/scope-tek-mso2000](../../tools/MCP/scope-tek-mso2000/README.md)。

16 個數位通道還沒有工具。這台沒有函數產生器。`jev-scope`（[jev.md](jev.md)）目前只支援 RIGOL 與 Keysight。

回到 [README.md](README.md)。其他示波器見 [tek-scope.md](tek-scope.md)（TDS2014B）、[keysight-scope.md](keysight-scope.md)、[rigol-scope.md](rigol-scope.md)。

## 連線：USB、WinUSB 與 pyvisa-py

做法和 TDS2014B 相同（見 [tek-scope.md](tek-scope.md#連線usbwinusb-與-pyvisa-py)）：以 Zadig 把「MSO2014」（USB ID `0699 0377`）綁 WinUSB，之後 pyvisa-py 列出 `USB0::1689::887::<序號>::0::INSTR`（887 = 0x0377）。`config.json` 用 `"auto"` 依 VID／PID 找示波器，序號不寫進倉庫。兩台 Tek 同時接上時，各自的工具只會抓自己的 PID。

### USB 卡住（2026-10-22 實測）

AUTOSET 執行時（約 8 s）示波器不處理 USB。當時一支探測腳本在 AUTOSET 之後立刻送 `*ESR?`，2 s 逾時並在傳輸中途結束。之後每次寫入都逾時（bulk OUT timeout）：

- pyvisa-py 的 `clear()` 不支援 USB。
- 直接用 pyusb 送 USBTMC `INITIATE_CLEAR`（回 success）、清 endpoint halt，之後變成 pipe error。
- pyusb `reset()` 沒有用。

**只有拔插 USB 線**才恢復。所以：

- AUTOSET 只用 `mso_autoscale`：寫入後只等一次 30 s 逾時的 `*OPC?`，中間不查錯。
- `mso_scpi` 拒絕 `AUTOS`。
- 任何工具若連 `*IDN?` 都逾時，請人拔插示波器的 USB 線。

## 速度（USB，2026-10-22 實測）

| 動作 | 時間 |
| --- | --- |
| 一次簡單查詢 | 25–50 ms（TDS2014B 的 1/3） |
| 第一次連線 | 約 1.6 s |
| `mso_status` | 約 1.5 s |
| 一個 `MEASU:IMM:VAL?` | 50–100 ms；工具每項含設定與查錯約 260 ms |
| `mso_capture` SCREEN（約 5200 點）／FULL（125 k 點） | 約 0.25 s／0.5 s 傳輸；工具含檢查約 2 s／2.6 s |
| `AUTOS EXEC` | 約 8.5 s |
| 不支援的查詢 | 約 2.1 s（沒有 TDS 那種多 5 s 的 abort 等待） |
| 設定觸發、通道、時基 | 0.5–1.5 s：工具會等 `*OPC?` 再等 0.4 s，見「觸發狀態」 |

## 和其他示波器不同的 SCPI

| 項目 | MSO2014 | TDS2014B |
| --- | --- | --- |
| 垂直 | `CH<n>:OFFS` 是真正的電壓偏移，`CH<n>:POS` 是格；中心電壓 = offset − position × scale | 只有 `POS`（格） |
| 探棒 | `CH<n>:PRO:GAIN` = 1／衰減比（10:1 → 0.1）。這些探棒沒有 ID 腳（`"No Probe Detected"`），要手動設 | `CH<n>:PRO 10` |
| 頻寬 | `CH<n>:BAN TWE|FUL`，查詢回 Hz（20E6／100E6） | `BANDW ON|OFF` |
| 時基 | `HOR:SCA`（1-2-4 序列：要 250 µs 會變 200 µs）、`HOR:POS`（觸發在畫面的百分比）、`HOR:DEL:MOD`、`HOR:DEL:TIM`、`HOR:RECO 125000|1000000`（100000 會變 125000） | `HOR:MAI:SCA/POS` |
| 取樣率 | 跟著紀錄長度：200 µs/div 時 125 k → 62.5 MSa/s，1 M → 500 MSa/s | 固定 2500 點 |
| 觸發 | `TRIG:A:TYP EDG|PULS`（`PUL` 回 141）、`TRIG:A:MOD AUTO|NORM`、準位依通道存 `TRIG:A:LEV:CH<n>`、holdoff `TRIG:A:HOLD:TIM` | `TRIG:MAI:…` |
| 邊緣 | 斜率只有 `RIS`／`FALL`（`EITH` 回 141）；耦合 `DC`、`HFR`、`LFR`、`NOISE`（沒有 AC） | |
| 脈寬 | `TRIG:A:PUL:CLA WID`；`TRIG:A:PULSEW:SOU/POL POS|NEG/WHE LESS|MORE|EQ|UNEQ/WID`；門檻就是 `TRIG:A:LEV:CH<n>` | `TRIG:MAI:PUL:WID:…`，極性要全字 |
| 波形 | `DAT:RESO REDU|FULL`、`DAT:SOU/ENC RIB/WID 1/STAR/STOP`、`WFMO:`（XIN、PT_O、XZE、YMU、YOF、YZE）、`CURV?` | `WFMP:`，2500 點 |
| 截圖 | `HARDC STAR` 經 USBTMC **不回任何資料**（30 s 逾時；這個韌體只送給印表機）。要插隨身碟：`SAV:IMAG "E:/…"`、`FILES:READF`、`FILES:DELE` | `HARDC STAR` 回 BMP |

錯誤處理和 TDS 相同：`*ESR?` 之後讀 `ALLEV?`，連線時 `HEAD OFF`。

## 觸發狀態

`TRIG:STATE?` 實測看過 `AUTO`、`ARMED`、`READY`、`TRIG`、`SAV`。單看它會誤判：例如脈寬條件不成立時仍短暫出現 `TRIG`。工具判斷方式和 TDS 相同：

- `ACQ:STATE?` 是 0 → `STOP`。
- `TRIG:A:MOD?` 是 AUTO → `AUTO`。
- NORM 模式下 0.4 s 內 `ACQ:NUMAC?` 有增加 → `TD`，否則 `WAIT`。

**改設定後要先等**：改了觸發條件，前幾筆擷取仍照舊條件，`ACQ:NUMAC?` 會數到。只用 0.25 s 窗時，脈寬 LESS 200 µs 誤報 `TD`、LESS 1 ms 誤報 `WAIT`，兩個方向都錯。所以設定工具在讀狀態前，先等 `*OPC?` 再等 0.4 s。

改 V/div 之後，第一次量測也會帶舊設定的 `541 Low signal amplitude` 警告，所以通道與時基工具也做同樣的等待。

## 量測項目

`MEASU:IMM:TYP` 接受：`AMP`、`AREA`、`BURST`、`CAREA`、`CMEAN`、`CRMS`、`DEL`、`FALL`、`FREQ`、`HIGH`、`LOW`、`MAX`、`MEAN`、`MINI`、`NDU`、`NOV`、`NWI`、`PDU`、`PERI`、`PHA`、`PK2P`、`POV`、`PWI`、`RIS`、`RMS`、`NEDGECOUNT`、`PEDGECOUNT`、`NPULSECOUNT`、`PPULSECOUNT`。`PK2`（TDS 的寫法）和 `TOVERSHOOT` 回 `141 Invalid enumeration`。

- 工具接受 RIGOL 名稱：`VPP`→`PK2P`、`VTOP`→`HIGH`、`VBASE`→`LOW`、`VAMP`→`AMP`、`VMAX`→`MAX`、`OVER`→`POV`、`PDUT`→`PDU`、`DEL`、`PHAS`→`PHA`。
- 雙通道項目用 `MEASU:IMM:SOU1`／`SOU2`。
- 無法量測回 `9.9E37`。
- 警告 `541`（振幅太小）、`543`（解析度不足，例如 200 µs/div 下量 0.5 µs 的上升時間）照樣回傳數值並列在 `warnings`。

## 實測驗證（2026-10-22，PROBE COMP，四通道 10:1、2 V/div、中心 2.8 V）

| 項目 | 結果 |
| --- | --- |
| 接上時的狀態 | 只顯示 CH2；CH1–CH3 探棒增益 1（10:1 探棒量到 0.5 V），CH4 是 0.1。改成 `probe_ratio=10` 後四通道一致 |
| `mso_measure` CH1–CH4 | FREQ 980.3–980.8 Hz；VPP 5.2–5.6 V；VTOP 4.88–4.96 V；VBASE 0–0.16 V；VAMP 4.88–4.96 V；PWID 510.4–510.6 µs；PDUT 50.03–50.06 %；VAVG 2.45–2.55 V |
| DEL／PHAS CH1→CH2 | −23.8 ns（543 警告）／−0.012° |
| `mso_set_channel` | AC、20 MHz 頻寬、反相改後讀回正確，再改回 |
| `mso_set_timebase` | 延遲 100 µs、位置 50 %、1 M 點（500 MSa/s）、回 125 k 都讀回正確 |
| EDGE NORM 準位 8 V | `WAIT`；量測與擷取拒絕；`force` 擷取一筆；stop 後 FULL 擷取 10000 點 |
| single（下降緣） | 0.6 s 內 `STOP`、`triggered: true` |
| PULSE（脈寬 510 µs） | LESS 1 ms、MORE 200 µs、EQ 510 µs、負脈衝 LESS 1 ms → `TD`；LESS 200 µs、MORE 1 ms、UNEQ 510 µs、EQ 200 µs → `WAIT`（每 1 s 約 175 次擷取 vs 0 次） |
| `mso_capture` | SCREEN 5208 點；FULL 125000 點、62.5 MSa/s，v_pp 與量測一致 |
| `mso_autoscale` | 8.5 s，USB 沒有卡住。四通道上下分開、10 V/div |
| `mso_scpi` | `*RST`、`AUTOS EXEC` 被擋；`FOO?` 約 2.1 s 回報 `113 Undefined header` |
| `mso_screenshot` | 沒插隨身碟時回報需要隨身碟；`HARDC STAR` 經 USB 讀不到資料 |

## 尚未做

- 數位通道 D0–D15（`SEL:D<n>`、`D<n>:THR`、邏輯／匯流排觸發）。
- 隨身碟截圖的實測（程式已寫，未插隨身碟驗證）。
- 游標工具、`jev-scope` 支援、接 F280049C 的實際訊號。
