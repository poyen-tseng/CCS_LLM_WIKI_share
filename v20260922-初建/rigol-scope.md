# RIGOL MSO5104 遠端截圖

用 LAN 控制 RIGOL MSO5104，截出波形置中、放大、有量測線的圖。下面的規則都來自 2026-10-07 實際量 GPIO0 上升緣的結果。MCP 伺服器見 [MCP/rigol-mso](../MCP/rigol-mso/README.md)，這頁用到的腳本在 [MCP/rigol-mso/tools](../MCP/rigol-mso/tools)。

回到 [README.md](README.md)。

## 連線

- SCPI 走原始 TCP，`192.168.137.50:5555`。位址寫在 `MCP/rigol-mso/config.json`。
- Windows 可能把 192.168.137.x 路由到 Wi-Fi。連線前先把 client socket 綁在本機有線／熱點位址 `192.168.137.1`，再 `connect`。
- 靜態 IP 用下面這串設定，重開機後仍有效：

```text
:LAN:DHCP OFF
:LAN:AUToip OFF
:LAN:MANual ON
:LAN:IPADdress 192.168.137.50
:LAN:SMASk 255.255.255.0
:LAN:GATeway 192.168.137.1
:LAN:APPLy
```

## 探棒比例

用 10X 探棒時要下 `:CHANn:PROB 10`。沒設的話 3.3 V 信號只讀到約 0.33 V，1.65 V 的觸發永遠不會發生。

## 垂直置中

- RIGOL 的通道 offset 是正值時波形往上移。0–3.3 V 的信號用 `:CHAN1:OFFS -1.65`，1.65 V 才會落在中線。曾經用 +1.65，3.3 V 那一段跑出畫面上緣。
- 畫面上下各 4 格。V/div 要留給過衝的空間。GPIO0 上升緣會衝到約 3.7 V：500 mV/div 頂端被切掉，600 mV/div 才放得下。
- 非標準檔位（例如 600 mV/div）要先 `:CHANn:VERN ON`，再設 `:CHANn:SCAL`。

## 水平置中

- `:TIM:MAIN:OFFS 0`，觸發點才在畫面正中央。曾經留著 3.5 ns 的延遲，邊緣就偏離中線。
- 觸發準位設在實際擺幅的 50%，不要用標稱的 1.65 V。實測 VBASE 約 0.17 V、VTOP 約 3.66 V，所以設約 1.95 V。這樣 50% 交越點才會落在中線。
- 上升時間約 11 ns 時用 5 ns/div，上下兩段平台都看得到。

## 單次擷取與 CCS 同步

`GPIO_EX1` 只把 GPIO0 拉高一次就空轉，所以邊緣只在程式剛開始時出現。這個專案不在 repository 裡，見 [Oscilloscope_read/STATUS.md](../Oscilloscope_read/STATUS.md)。順序：

1. CCS 腳本：`reset` → `loadProgram` → `halt`。
2. 確認 PC 在應用程式裡（例如 `_main`），不是 Boot ROM 的 0x3FBxxx。`loadProgram` 之後再 `reset`，PC 會留在 Boot ROM。
3. 示波器：`:TRIG:SWE NORM`、`:SING`，輪詢 `:TRIG:STAT?` 直到 `WAIT`。
4. 寫出 go 檔。
5. CCS 腳本看到 go 檔才 `run(false)`。
6. 示波器輪詢 `:TRIG:STAT?`，等到 `STOP` 或 `TD`。

## Track 量測線

- 設定：`:CURS:MODE TRACk`、`:CURS:TRACk:SOUR1 CHAN1`、`:CURS:TRACk:SOUR2 CHAN1`。
- 位置用 `:CURS:TRACk:CAX <px>`、`:CURS:TRACk:CBX <px>`。px 是 0 到 999，橫跨整個 10 格：`px = 500 + t / (10 * tdiv) * 1000`，t 以觸發點為 0。
- 讀值 `:CURS:TRACk:AXV?` 是非同步更新，最多會慢約 1 秒。拿讀值做二分搜尋會失敗。直接算 px，等約 1 秒，再讀回來確認。
- 讀值指令：`AXV?`、`AYV?`、`BXV?`、`BYV?`、`XDEL?`、`YDEL?`（都在 `:CURS:TRACk:` 底下）。
- `:CURS:TRACk:AX <時間>` 這類指令會回 -100 Command error，不能用時間直接設位置。

## 10% 與 90% 準位

- 用示波器自己的 `:MEAS:ITEM? VBASe,CHAN1` 與 `:MEAS:ITEM? VTOP,CHAN1`。這跟 RiseTime 用的定義相同。
- 用波形尾段中位數當高準位，90% 點會算錯，因為過衝後還在往下回落。
- 準位正確時，量測線 ΔX = 11.75 ns，與 RiseTime 11.8 ns 一致。
- 查詢某個量測項目，也會把它加進畫面下方的量測列。

## 兩種量測線畫法

同一次凍結的擷取可以截兩張圖。示波器保持 STOP，兩張之間只移動量測線，不要重新擷取。

| 畫法 | A 線 | B 線 | 看什麼 |
| --- | --- | --- | --- |
| 上升時間 | 10% 交越 | 90% 交越 | ΔX |
| 擺幅 | 低準位平台 | 高準位平坦段 | ΔY |

擺幅那張的 B 線不要放在過衝後還在回落的地方。

## 截圖

- `:DISP:DATA? ON,OFF,PNG` 回傳 IEEE 區塊（`#N<長度><資料>`）。這版韌體可能回 BMP，要轉成 PNG（`scope_lan.bmp_to_png`）。
- 讀完區塊後，socket 裡還剩一個 `\n`。用短逾時 `recv` 把它讀掉（`scope_lan.drain`），否則之後每個查詢的回應都錯一格。

## 側邊選單

`:SYST:KEY:PRES MOFF` 是切換，不是關閉。選單已經隱藏時再按，選單會跑出來。只在選單看得到時才按，按完看截圖確認。

## 存檔前檢查

任何一項不合格，就調整後重截：

- 50% 交越點離中線在 ±0.3 格以內。
- 低準位與高準位都完整在畫面內，沒有被切掉。
- 左上的量測線讀值框、左下的量測列沒有蓋到波形。
- 量測線沒有放在過衝上。
- 側邊選單已隱藏。

## 已接受的 GPIO0 上升緣設定

| 項目 | 值 |
| --- | --- |
| CH1 | 10X、600 mV/div、offset -1.65 V |
| 時基 | 5 ns/div、延遲 0 |
| 觸發 | 邊緣、上升、CHAN1、1.95 V、NORM、單次 |
| 結果 | RiseTime 11.8 ns、Vtop 3.66 V、Vbase 0.17 V |

## 內建信號產生器

- `:SOUR1:OUTP?` 有回應，這台有 GI（信號產生器）。
- `:SOUR1:OUTP:IMP?` 回 `OMEG`（高阻抗）。
- 這版韌體（00.01.03.03.00）下 `*OPT?` 會逾時。
- 產生器的用法之後再補。

## 腳本

[MCP/rigol-mso/tools](../MCP/rigol-mso/tools) 有三個檔。Python 只用標準函式庫，不需要 venv。

| 檔 | 用途 |
| --- | --- |
| `scope_lan.py` | socket 輔助：`connect`（預設綁 192.168.137.1）、`write`、`query`、`read_block`、`drain`、`bmp_to_png`、`waveform` |
| `capture_edge.py` | 設定示波器、單次擷取、算 px 放 Track 量測線、截兩張圖 |
| `edge_run.js` | CCS 21 腳本：連 XDS110、reset、載入、halt、等 go 檔、執行一次 |

兩個指令都在 `tools` 資料夾執行。另一個工作階段占用 XDS110 或示波器時不要跑。順序：

1. 先在背景啟動 CCS 腳本：

```bat
C:\ti\ccs2101\ccs\scripting\run.bat edge_run.js --ccxml <專案>\targetConfigs\TMS320F280049C.ccxml --program <專案>\Debug\GPIO_EX1.out
```

2. 等它印出 `READY`（或出現 `%TEMP%\gpio_edge_ready.txt`）。印出的 PC 要在應用程式範圍內。
3. 再執行擷取腳本：

```bat
python capture_edge.py
```

`edge_run.js` 的參數：

- `--ccxml`、`--program`：必填。也可以用環境變數 `EDGE_CCXML`、`EDGE_PROGRAM`。
- `--core`：預設 `C28xx_CPU1`。
- `--signal-dir`：ready／go／ran 檔的資料夾。預設 `EDGE_SIGNAL_DIR`，再來是 `%TEMP%`。
- `--wait-ms`：等 go 檔的上限，預設 90000。
- `--hold-ms`：執行後保持連線的時間，預設 40000。

`capture_edge.py` 的參數：

- `--addr`、`--port`：預設 `SCOPE_ADDR`，再來是 `config.json`；連接埠 5555。
- `--bind`：連線前綁的本機位址。預設 `SCOPE_BIND`，再來是 `192.168.137.1`。給 `""` 就不綁。
- `--vscale`、`--offset`、`--level`、`--tdiv`：預設 0.6 V/div、-1.65 V、1.95 V、5e-9 s/div。
- `--go-file`：預設 `%TEMP%\gpio_edge_go.txt`。改了 `--signal-dir` 時要一起改。
- `--out-dir`、`--prefix`：預設 `MCP/rigol-mso/captures`（不進 git）與 `GPIO0_rise`。輸出 `<prefix>_10_90.png` 與 `<prefix>_swing.png`。
- `--config-only`：只設定示波器就結束。
- `--reuse`：不設定、不擷取，直接用目前凍結的波形重放量測線、重截圖。CCS 腳本不用再跑。
- `--menu-off`：第一張截圖前按一次 MOFF。只在側邊選單看得到時才加。

擺幅那張的量測線位置寫死在 `capture_edge.py`：A 在 50% 交越點前 12 ns，B 在觸發點後 14 ns。這是照 5 ns/div 調的，換時基要跟著改。

截圖不要放進這個 repository。
