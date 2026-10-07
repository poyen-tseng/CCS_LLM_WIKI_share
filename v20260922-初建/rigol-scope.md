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

## 內建信號產生器（GI）

2026-10-07 量 GPIO Example 2 時用過。

- `:SOUR1:OUTP?` 有回應，這台有 GI。這版韌體（00.01.03.03.00）下 `*OPT?` 會逾時。
- 高阻抗模式（`:SOUR1:OUTP:IMP OMEG`）下，|offset| + Vpp/2 上限是 2.5 V。設 3.3 Vpp、offset 1.65 V 時，offset 會被自動改成 0.85 V，不會報錯。所以 0–3.3 V 做不到，最多 0–2.5 V（`:SOUR1:VOLT 2.5`、`:SOUR1:VOLT:OFFS 1.25`）。2.5 V 仍高於 F28004x 的 VIH。
- 開輸出前先關輸出、設好參數、回讀 `FUNC?`、`VOLT?`、`VOLT:OFFS?`、`OUTP:IMP?`，確認上下限都在 0 到 3.3 V 之間才 `:SOUR1:OUTP ON`。回讀和設定值不同就保持關閉。
- 腳位還被程式當輸出時不要開 GI，例如板上還在跑 `GPIO_EX1`（GPIO0 輸出高）。先下載把該腳設成輸入的程式。
- 三角波：`:SOUR1:FUNC RAMP`、`:SOUR1:FUNC:RAMP:SYMM 50`、`:SOUR1:FREQ 1`。
- 脈衝：`:SOUR1:FUNC PULS`、`:SOUR1:FREQ`、`:SOUR1:PULS:DCYC <百分比>`。10 kHz、10% 就是 10 µs 寬的脈衝。
- 沒有 BNC 轉鱷魚夾時，可以把 1X／10X 可切換的探棒切到 1X，當信號線用：BNC 接 GI，鉤針接腳位，接地夾接 GND。固定 10X 的探棒鉤針裡串了 9 MΩ，不能當信號源。

## 雙通道與觸發

- 第二個通道一樣要 `:CHAN2:PROB 10`。兩個通道都用 1 V/div、offset -1.65 V，0 V 會落在中線下 1.65 格，兩條線疊在同一組格線上，和講義的圖一樣。
- 時基很慢（例如 100 ms/div）時，`:RUN` 幾秒後 `:STOP`，畫面可能停在掃描中途，只剩一個點，量測值也是舊的。看電位用 1 ms/div 左右。
- 脈寬觸發：`:TRIG:MODE PULS`、`:TRIG:PULS:SOUR CHAN2`、`:TRIG:PULS:LEV 1.65`、`:TRIG:PULS:WHEN LESS`、`:TRIG:PULS:UWID <秒>`。`WHEN` 只吃 `GRE`、`LESS` 這類值，`PLES`、`:TRIG:PULS:POL` 都會 -100。先用一個一定會觸發的寬度做對照（例如脈寬 0.5 s 時設 UWID 1），確認設定有效，再用來找窄突波。
- 用手碰觸製造彈跳時，觸發會被碰觸瞬間的彈跳搶先觸發。要拍「放開」時，請對方先碰穩，再上膛，再放開。
- 凍結的擷取記憶體夠深時（例如 10 ms/div、20 Mpts），停住後改 `:TIM:MAIN:SCAL` 和 `:TIM:MAIN:OFFS`，就能放大同一筆資料的任何一段，不必重抓。

## 側邊選單偵測

量測指令（`:MEAS:ITEM`）常會把 Measure 選單打開，不能假設它是關的。截圖後檢查 BMP：選單左緣在 x ≈ 850–862 有一條藍色邊線（b > 120、r < 100、b 比 g 大 30 以上），沿 y 200–540 掃，超過 40 列命中就是選單開著，這時按一次 MOFF 再重截。用畫面右側亮點總數判斷不可靠，選單按鈕底色是黑的。

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
