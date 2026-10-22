# Timer 中斷作業：100 Hz／500 Hz 方波與 ISR 執行時間

本文件記錄 `4_TIMER_Interrupt_HW.pdf` 的作業規格（*Homework - Timer and Interrupt module*）。下一個 coding agent 依這裡的程式、腳位、計算與量測步驟操作。進度記在 `STATUS.md`（開始實作時建立）。

專案是 `TIMER_HW`（2026-10-22 已建立），由 [Timer_lab/TIMER0_EX](../Timer_lab/TIMER0_EX) 複製改名，沿用老師版的 device support 檔與 RAM 連結設定。不要修改 Timer_lab 或其他既有 CCS 專案。

## 範圍

- 來源：`4_TIMER_Interrupt_HW.pdf` 第 1–3 頁，雲端課程資料夾 `數位控制設計-楊`。講義標了 CONFIDENTIAL，不放進倉庫。
- 第 1 頁是作業本身。第 2–3 頁是 Timer_lab 已做過的 `Init_PIE`、`TIMER0_ISR`、`main` 與 2.5 Hz 例圖，作為起點，並在第 2 頁 ISR 旁用紅字標出 GPIO 拉高、拉低的位置。
- 裝置：TMS320F280049C，LAUNCHXL-F280049C。SYSCLK = 100 MHz（`InitSysCtrl()`）。
- 只用 CPU Timer0，中斷走 PIE INT1.7。不要用 ePWM、第二個 Timer 或輪詢 `TIF`。講義沒寫的實驗條件不要自己加。

## 作業內容（第 1 頁）

一題，三個工作：

1. 用 Timer 與 GPIO 產生 **100 Hz** 方波。
2. 只用**一個** Timer 模組，同時產生 **100 Hz** 與 **500 Hz** 方波。講義手寫「gpio1, gpio2」，可能是指 GPIO1、GPIO2 兩支腳，也可能只是「第一、第二個 GPIO 輸出」；本專案選用 GPIO1、GPIO2。
3. 量測 **ISR 執行時間**，確認達成例圖所需的 **PRD 設定值**，並說明為什麼是這個值：
   - 進入 ISR 後把 GPIO 設為 High（ISR 第一行）。
   - 離開 ISR 前把 GPIO 設為 Low（ISR 最後一行）。
   - 量 High 脈波寬度，估計 ISR 執行時間（手寫：量中斷副程式第一行到最後一行的時間）。
   - 手寫提示：量下方脈波的頻率即可得知 PRD 設定值。

講義例圖只畫一組：一條每次 ISR 翻轉一次的方波，加一條 ISR 脈波，結構和工作 1 相同。講義沒有寫要量哪個工作。**本專案的決定（使用者 2026-10-22）：工作 1、工作 2 的 ISR 都量**，以涵蓋兩種解讀。

第 1 頁例圖：上方方波每次 ISR 翻轉一次，高低準位「等長」，代表每個半週期都剛好是一個 Timer 週期；下方每次 ISR 一個窄脈波。方波的翻轉邊緣落在脈波的高準位**之內**（比脈波上升緣晚一點），因為翻轉那行程式在 ISR 中間執行，不是和脈波上升緣對齊。

## 腳位

| 信號 | 工作 1 | 工作 2 | 封裝腳（100-pin PZ） | 開發板接頭（講義 pin map） |
| --- | --- | --- | --- | --- |
| GPIO1 | 100 Hz 方波 | 100 Hz 方波 | 78 | BoosterPack J8，編號 79 |
| GPIO2 | ISR 脈波 | 500 Hz 方波 | 77 | BoosterPack J8，編號 76 |
| GPIO0 | 不用 | ISR 脈波 | 79 | BoosterPack J8，編號 80 |

GPIO0、GPIO1 的接頭位置 2026-10-12 查證過，見 `docs/wiki/board-pins.md` 的「GPIO0／GPIO1／GPIO6 的接頭位置」。講義 pin map 的 J8 80／79 與 TI 使用說明 SPRUII7B Rev B 的 60／59 是**同一個實體位置**（J6／J8 標示勘誤）。照講義標的位置接，不要照 Rev B 的數字。

GPIO2（2026-10-22 查電路圖）：雲端 `TMS320F280049C_開發板電路圖.pdf` 第 2 頁 J8 的圖上腳號要加 40（圖上註明）。換算後 80 GPIO0、79 GPIO1、78 GPIO6、77 GPIO7、**76 GPIO2**、75 GPIO3。GPIO2 封裝腳 77，經 R71（0 Ω）接到接頭。照 Rev B 的編號推算是 56，Rev B 原圖沒有查。

J8 與 J6 組成 2×10 排針，同一列另一欄的腳：80 對 GND、79 對 GPIO27、76 對 **XRSn（RST）**。接 GPIO2 時勾針不要碰到旁邊的 RST，會重設晶片。

接線：CH1 接 GPIO1、CH2 接 GPIO2、CH3 接 GPIO0，地夾接 GPIO0 同一列的 GND（J6 60）。GPIO2 的位置用工作 1 的波形確認：CH1 是 100 Hz 方波、CH2 是 200 Hz 窄脈波、CH3 沒有訊號，三者各不相同就代表接對。確認結果寫回 `docs/wiki/board-pins.md`。

## 計算

講義（3_TIMER 第 7 頁）公式：`Time = 1/SYSCLKOUT × PRD × TDDR`，「TDDR = 1」是指除 1，暫存器值是 0。TRM 的精確式：

```
T = (PRD + 1) × (TDDR + 1) / SYSCLK
```

**PRD 照講義寫法**：`PRD = SYSCLK × T`，不減 1，與 Timer_lab 的 20000000 一致。多出的 1 個 SYSCLK（10 ns）誤差在報告中說明，不改程式。TPR、TPRH 都是 0（不分頻）。

每次 ISR 翻轉一次，方波週期是 ISR 週期的 2 倍。

| 工作 | ISR 週期（設計） | PRD | 實際 ISR 週期 | 輸出 |
| --- | --- | --- | --- | --- |
| 1 | 5 ms | 500000 | 500001 × 10 ns = 5.00001 ms | GPIO1 每次 ISR 翻轉：100 Hz（99.9998 Hz）；GPIO2 脈波 200 Hz（199.9996 Hz） |
| 2 | 1 ms | 100000 | 100001 × 10 ns = 1.00001 ms | GPIO2 每次 ISR 翻轉：500 Hz（499.995 Hz）；GPIO1 每 5 次 ISR 翻轉：100 Hz（99.999 Hz）；GPIO0 脈波 1 kHz（999.99 Hz） |

工作 2 只有一個 Timer，所以 ISR 週期取兩個半週期（5 ms、1 ms）的公約數 1 ms。500 Hz 每次 ISR 翻轉，100 Hz 在 ISR 裡用計數器數到 5 才翻轉一次。

離線驗算：在專案裡新增 `TIMER_HW/tools/timer_math.py`，改自 `Timer_lab/TIMER0_EX/tools/timer_math.py`。它從 `Init.c`／`Init.h` 讀 `HW_PART`、PRD、TPR、TPRH，算出上表數值，印 PASS／FAIL。改了計時設定就再跑一次。用 `python -I` 執行。

## 程式

### 結構

- 一個 CCS 專案 `TIMER_HW`，`Init.h` 用 `#define HW_PART 1`（或 `2`）切換工作 1、工作 2。改完重新建置、下載。
- ISR 脈波程式在工作 1、工作 2 都有，所以工作 3 不另外建置：量工作 1 的 ISR 時間就用 `HW_PART 1`，量工作 2 就用 `HW_PART 2`。
- 照講義忠實度原則：沿用 Timer_lab 的程式，只改作業需要的地方，並用 `// [作業]` 註解標出。建置或審查證明必須修正講義原碼時，另用 `// [修正]` 標出。

### main、Init_PIE

照 Timer_lab（3_TIMER 第 15–16 頁、本講義第 2–3 頁），不改：

```c
void main(void)
{
    InitSysCtrl();
    Init_GPIO();
    Init_CpuTimer();
    Init_PIE();
    while(1)
    {
    }
}
```

`Init_PIE`：`DINT`、`InitPieCtrl`、`IER = IFR = 0`、`ENPIE = 1`、`InitPieVectTable`、`PIEIER1.bit.INTx7 = 1`、`IER |= M_INT1`、`EINT`、`ERTM`。

### Init_GPIO

沿用 Timer_lab 對 GPIO0 的設定方式（`GPAPUD.all = 0xFFFFFFFF`、`GPADIR = 1`、`GPAMUX1 = 0`、`GPAGMUX1 = 0`、`GPAPUD = 1`、`GPACSEL1 = 0`），對**實際用到的腳**都做一次：

- 工作 1：GPIO1、GPIO2。
- 工作 2：GPIO0、GPIO1、GPIO2。

方波腳的初始準位依 Timer_lab 先 `GPASET`。脈波腳初始一定要 `GPACLEAR`（Low），否則第一次 ISR 前會是 High。

### Init_CpuTimer

與 Timer_lab 相同，只有 PRD 依 `HW_PART` 不同：

```c
CpuTimer0Regs.PRD.all  = 500000;   // 工作 1：10 ns × 500000 = 5 ms
// CpuTimer0Regs.PRD.all = 100000; // 工作 2：10 ns × 100000 = 1 ms
CpuTimer0Regs.TPR.all  = 0;
CpuTimer0Regs.TPRH.all = 0;
```

其餘（`RegsAddr`、`TSS = 0`、`TIE = 1`、`TIF = 1`、`InterruptCount = 0`）不變。

### TIMER0_ISR

ISR 繼續放在老師版 `f28004x_defaultisr.c`（Timer_lab 是第 106–119 行），PIE 向量表 1.7 已指向它。不要在別的檔再定義一個 `TIMER0_ISR`，會重複定義而連結失敗。`f28004x_defaultisr.c` 需要 `#include "Init.h"` 才看得到 `HW_PART`。

脈波拉高、拉低的位置照本講義第 2 頁紅字：`{` 後第一行拉高，`}` 前最後一行拉低。工作 1 的樣子：

```c
interrupt void TIMER0_ISR(void)
{
    GpioDataRegs.GPASET.bit.GPIO2 = 1;      // [作業] 進入 ISR：脈波 High
    CpuTimer0.InterruptCount++;
    EALLOW;
    GpioDataRegs.GPATOGGLE.bit.GPIO1 = 1;   // [作業] 100 Hz 方波
    PieCtrlRegs.PIEACK.all = PIEACK_GROUP1;
    EDIS;
    GpioDataRegs.GPACLEAR.bit.GPIO2 = 1;    // [作業] 離開 ISR 前：脈波 Low
}
```

工作 2：脈波腳換成 GPIO0；每次 ISR 翻 GPIO2（500 Hz）；用計數器每 5 次 ISR 翻一次 GPIO1（100 Hz）。本專案的計數器是 ISR 裡的 `static` 區域變數，數到 5 歸零。

注意：

- `PIEACK_GROUP1` 必寫，否則只進一次中斷。
- ISR 時間與編譯條件有關。專案目前沒有設定 `--opt_level`，程式在 RAM 執行（`280049C_RAM_lnk.cmd`）。建置後從 build log 確認實際的最佳化等級，記進 STATUS 與報告；不要為了讓 ISR 變短而改最佳化或連結設定。

## 工作 3：量測方法與要回答的問題

1. **ISR 執行時間**：量脈波 PWID。這段時間是 ISR 內第一行到最後一行，不含中斷延遲（從 Timer 歸零到進 ISR）和編譯器加的 context save／restore。報告要寫出量到的是哪一段。
2. **PRD 設定值**：量脈波頻率 `f_pulse`（= ISR 頻率），回推 `PRD = SYSCLK / f_pulse − 1`，與程式值（500000／100000）對照。示波器的頻率解析度看不出 ±1 時，如實寫出解析度限制。
3. **為什麼 PRD 是這個值**（講義的 *explain why*）：
   - 每次 ISR 只翻轉一次，所以方波的高、低準位各是一個 Timer 週期（例圖的「等長」），Timer 週期要設成方波的**半週期**。100 Hz 的半週期 5 ms，對應 PRD = 100 MHz × 5 ms = 500000。
   - 下方脈波每次 ISR 出現一次，脈波頻率 = ISR 頻率 = 方波頻率 × 2，所以量脈波頻率就能回推 PRD。
   - Timer 從 PRD 數到 0 再重載，共 PRD + 1 個 SYSCLK，所以實際週期是 `(PRD + 1) / SYSCLK`，照講義寫 PRD = N 會多 10 ns。
   - 補充：重載由硬體完成，不等 ISR 做完，所以 ISR 時間不影響週期；前提是 ISR 執行時間遠小於 ISR 週期，用量到的 ISR 時間佐證。
4. （選做）工作 2 的 ISR 在翻 GPIO1 的那次多做一件事。若示波器看得出兩種脈寬，分別記錄。

ISR 脈寬沒有預先的合格值，只記錄實測值（多次量測的平均、最小、最大）與條件。

## 建置與下載

流程與 Timer_lab 相同（RAM 連結，斷電後程式消失）：

1. 建立專案：複製 `projects/Timer_lab/TIMER0_EX` 為 `projects/Timer_HW/TIMER_HW`，不要複製 `Debug/`；改 `.project` 的專案名稱、`.launches` 檔名與 `tools/flash_and_run.js` 的輸出檔名。
2. 第一次（產生 `Debug/makefile`）：headless CCS 就地匯入並建置，workspace 用暫存目錄。指令見 [Timer_lab TASK](../Timer_lab/TASK.md) 的「建置與下載」。
3. 在 `tools/JEV_accel/config.json` 的 `projects` 用 `path` 登記 `TIMER_HW`（`mode: "ram"`，`path: "../../projects/Timer_HW/TIMER_HW"`），之後用 `ccs_build(project="TIMER_HW")`，回傳的 `map` 應是 `ok: true`、`mode: "ram"`。
4. 下載執行：先 `ccs_env` 確認 XDS110 沒被佔用，再 `ccs_load(project="TIMER_HW", run=true)`。交給 IDE 或其他工具前先 `ccs_release`。
5. 切換工作：改 `HW_PART` → 重建 → 重新下載。

操作 CCS 與示波器前先讀 `tools/JEV_accel/AGENTS.md` 與 `docs/wiki/jev.md`。

選用檢查：`CpuTimer0.InterruptCount` 工作 1 每秒約加 200，工作 2 每秒約加 1000。halt／run 要在同一次下載連線內做，理由見 Timer_lab TASK。

## 量測（RIGOL MSO5104）

示波器操作見 `docs/wiki/rigol-scope.md`，PDUT 單位、單次擷取與選單關閉的注意事項見 `docs/wiki/timer-flow-performance.md`。截圖前先 `jev_check_frame`；畫面是平的先 `jev_diagnose_capture`。

共同設定：探棒 10X、DC、1 V/div；RIGOL offset 與 Keysight 符號相反（Timer_lab 單通道用 −1.65 V，多通道時改用各通道位置錯開，以畫面不重疊為準）；觸發 Edge、上升緣、1.65 V、NORM。

| 畫面 | 通道 | 時基 | 觸發 | 讀值 |
| --- | --- | --- | --- | --- |
| 工作 1 概觀（對照例圖） | CH1 GPIO1、CH2 GPIO2 | 2 ms/div（2 個 100 Hz 週期、4 個脈波） | CH1 | CH1 FREQ／PER／PWID／NWID／PDUT／VTOP／VBASE；CH2 FREQ |
| 工作 2 概觀 | CH1 GPIO1、CH2 GPIO2、CH3 GPIO0 | 2 ms/div | CH1 | CH1、CH2 同上；CH3 FREQ |
| ISR 脈波放大（工作 1、2 各一張） | 脈波通道（＋方波通道，確認翻轉邊緣落在脈波內） | 從 200 ns/div 起，調到脈波佔數格 | 脈波通道上升緣 | 脈波 PWID（多次）、FREQ |

合格標準：

| 項目 | 標準 |
| --- | --- |
| 100 Hz 方波（工作 1、2 的 GPIO1） | FREQ 100 Hz ± 1 %，PWID／NWID 5 ms ± 1 % |
| 500 Hz 方波（工作 2 的 GPIO2） | FREQ 500 Hz ± 1 %，PWID／NWID 1 ms ± 1 % |
| PDUT | 49–51 %（RIGOL 回傳比例，0.5 = 50 %，換算後比對） |
| ISR 脈波頻率 | 工作 1 200 Hz ± 1 %，工作 2 1 kHz ± 1 % |
| ISR 脈寬 | 只記錄，無合格值 |
| VTOP／VBASE | 約 3.3 V／約 0 V（Timer_lab 曾量到 VTOP 偏低且原因未明，照實記錄） |

量測當下必做：存一份 `scope_status` 輸出（取樣率、記憶深度、頻寬限制、探棒倍率），記下探棒型號與接地方式（長地夾或短接地彈簧）。截圖用白底 PNG。截圖與原始資料放 `tools/JEV_accel/results/` 或私人目錄，不進 Git。

## 報告

- 檔名：`YYYYMMDD_TIMER中斷作業_第七組_<姓名>.pptx`。第一版用製作日 20261022，交件日確定後再改。
- 位置：倉庫旁的 `../CCS_private_archive/reports/Timer_HW/`，不進倉庫。
- 範本：`projects/Timer_lab/20261007_GPIO_第七組_<姓名>_template.pptx`；字型、頁尾等版型規則見 `docs/wiki/board-pins.md` 的報告版型。
- 必要內容：三個工作的程式說明（標出 `[作業]` 修改處）、PRD 計算、各工作波形截圖與量測值、工作 3 的答案（PRD 設定值與回推值、PRD 為什麼是這個值、ISR 執行時間、量測範圍不含 context save 的說明），以及「量測設備與設定」頁（欄位與「未記錄」寫法見 `docs/wiki/board-pins.md` 的「量測簡報必備：設備與設定頁」）。
- 區分理論預期、建置通過與硬體實測；沒量到的不要寫成已量到。

## 操作界線

- 不修改其他專案（Timer_lab、LED_test、Feedback_test、Serial_Plotter、Oscilloscope_read）。
- 講義 PDF、截圖、報告不進倉庫。
- `Debug/` 是編譯結果，依 `.gitignore` 不進版控。
