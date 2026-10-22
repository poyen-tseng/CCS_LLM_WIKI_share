# Timer 實驗：Timer0 中斷切換 GPIO0

本文件記錄 `3_TIMER_lecture.pdf` 第 12–16 頁的實驗操作。下一個 coding agent 依這裡的程式、腳位、計算與量測步驟操作。進度記在 [STATUS.md](STATUS.md)。

專案是 [TIMER0_EX](TIMER0_EX)，由 `projects/Oscilloscope_read/GPIO_EX2` 複製改名，沿用老師版的 device support 檔與 RAM 連結設定。不要開啟或修改其他既有 CCS 專案。

## 範圍

- 來源：`3_TIMER_lecture.pdf` 第 12–16 頁，標題 *LAB experiment - Timer0 Module*。講義標了 CONFIDENTIAL，不放進倉庫。
- 第 1–11 頁是背景：下數計數原理、CPU Timer 架構（TIM、PRD、TCR、TPR／TPRH 的 TDDR 與 PSC、TINT）、第 7 頁的時間計算、第 11 頁 TIMER0 經 PIE 送到 CPU INT1。這些只用來核對程式，不是另外的實驗步驟。
- 裝置：TMS320F280049C，LAUNCHXL-F280049C。SYSCLK = 100 MHz（`InitSysCtrl()`）。
- 講義只要求 Timer0。不要另做 Timer1／Timer2、ePWM 或改成輪詢 `TIF`。

## 實驗目標（第 12 頁）

用 Timer0 模組控制 GPIO0 做 toggle。

1. 設定 Timer0 計數 0.2 秒。
2. 在中斷服務函式中切換 GPIO0，並量測 GPIO0 狀態。（若 GPIO0 外接 LED，LED 會閃爍。）

## 腳位

| 信號    | 封裝腳（100-pin PZ） | 開發板接頭（講義 pin map）    |
| ----- | --------------- | -------------------- |
| GPIO0 | 79              | BoosterPack J8，編號 80 |

第 12 頁圖上把「Pin 80」畫在晶片框旁，但 80 不是封裝腳號（精簡版 Table 4-1：GPIO0 是 pin 79）。它是 GPIO 講義第 32 頁 pin map 的接頭編號（J8、80）。上一個 GPIO 實驗在 2026-10-07 照這個位置接探棒，量到的就是 GPIO0（`projects/Oscilloscope_read/STATUS.md`）。

注意：TI 使用說明 SPRUII7B Rev B 的 Figure 3 把同一個位置編成 **60**，它的「80」是同一排另一腳 **GND**（J6／J8 標示勘誤）。照講義標的位置接，不要照 Rev B 的數字。對照表見 `docs/wiki/board-pins.md` 的「GPIO0／GPIO1／GPIO6 的接頭位置」。

## 計算（第 7 頁）

講義公式：`Time = 1/SYSCLKOUT × PRD × TDDR`。講義寫「TDDR = 1」是指除 1，暫存器值是 0。TRM 的精確式：

```
T = (PRD + 1) × (TDDR + 1) / SYSCLK
```

- 0.2 s、SYSCLK 100 MHz、不分頻：PRD = 0.2 × 100M = 20,000,000（< 2^32）。講義程式就寫 20000000，實際 T = 0.20000001 s。精確值是 19999999，差 10 ns，可忽略。**照講義保留 20000000。**
- 最大時間（不分頻）：2^32 / 100 MHz = 42.95 s。
- 最大時間（PRD 與 TDDR 都最大）：2^32 × 2^16 / 100 MHz = 2,814,749.77 s ≈ 32.6 天（講義手寫「32 天」）。

GPIO0 每次中斷切換一次，所以預期波形：

| 項目    | 預期值                        |
| ----- | -------------------------- |
| 高準位寬度 | 0.2 s                      |
| 低準位寬度 | 0.2 s                      |
| 週期    | 0.4 s                      |
| 頻率    | 2.5 Hz（第 16 頁例圖讀數 2.50 Hz） |
| Duty  | 50 %                       |
| 高準位   | 約 3.3 V                    |

離線驗算：`python -I TIMER0_EX/tools/timer_math.py`。它從 `Init.c` 讀 PRD、TPR、TPRH 算出上面數值，印 PASS／FAIL。改了 `Init.c` 的計時設定就再跑一次。

## 程式

順序是第 16 頁 Step 4 的 `main`。每個函式在 `TIMER0_EX/Init.c`，註解保留講義原文。

### main（第 16 頁 Step 4）

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

### Init_GPIO（第 13 頁 Step 1）

- `InitGpio()`，`EALLOW`
- `GPAPUD.all = 0xFFFFFFFF`：關閉 GPIOA 內部上拉
- `GPADIR.bit.GPIO0 = 1`：輸出
- `GPAMUX1.bit.GPIO0 = 0`，`GPAGMUX1.bit.GPIO0 = 0`：GPIO 功能
- `GPAPUD.bit.GPIO0 = 1`：關閉該腳上拉
- `GPACSEL1.bit.GPIO0 = 0`：CPU 控制
- `GPASET.bit.GPIO0 = 1`：先輸出高準位
- `EDIS`

### Init_CpuTimer（第 14 頁 Step 2）

```c
EALLOW;
CpuTimer0.RegsAddr = &CpuTimer0Regs;
CpuTimer0Regs.PRD.all  = 20000000; // 10 ns × 20000000 = 0.2 s
CpuTimer0Regs.TPR.all  = 0;        // 不分頻
CpuTimer0Regs.TPRH.all = 0;
CpuTimer0Regs.TCR.bit.TSS = 0;     // 開始計數
CpuTimer0Regs.TCR.bit.TIE = 1;     // 啟用 Timer0 中斷
CpuTimer0Regs.TCR.bit.TIF = 1;     // 寫 1 清除旗標
CpuTimer0.InterruptCount = 0;
EDIS;
```

### Init_PIE（第 15 頁 Step 3）

```c
DINT;
InitPieCtrl();
IER = 0x0000;
IFR = 0x0000;
PieCtrlRegs.PIECTRL.bit.ENPIE = 1;
InitPieVectTable();
PieCtrlRegs.PIEIER1.bit.INTx7 = 1; // INT1.7 = TIMER0
IER |= M_INT1;
EINT;
ERTM;
```

### TIMER0_ISR（第 15 頁右側）

```c
interrupt void TIMER0_ISR(void)
{
    CpuTimer0.InterruptCount++;
    EALLOW;
    GpioDataRegs.GPATOGGLE.bit.GPIO0 = 1;
    PieCtrlRegs.PIEACK.all = PIEACK_GROUP1;
    EDIS;
}
```

這個 ISR **不在 `Init.c` 或 `main.c`**。它在老師修改過的 `TIMER0_EX/f28004x_defaultisr.c`（第 106–119 行），`f28004x_pievect.c` 的 PIE 向量表 1.7 指向它，所以 `InitPieVectTable()` 之後就接上了。講義程式不需要另寫 `PieVectTable.TIMER0_INT = &TIMER0_ISR;`。

注意：

- 不要在別的檔再定義一個 `TIMER0_ISR`，會重複定義連結失敗。若換成 C2000Ware 原版 `f28004x_defaultisr.c`，裡面的 `TIMER0_ISR` 是 `ESTOP0; for(;;);`，GPIO0 不會翻轉。
- ISR 一定要寫 `PIEACK_GROUP1`，否則 INT1 群組只會進一次中斷，GPIO0 只翻一次。
- `Init_CpuTimer` 先把 TSS 清 0 才 `Init_PIE`，計時器比中斷早幾微秒開始數。第一個 0.2 s 內就開好中斷，不影響波形。
- 照講義忠實度原則：沿用講義程式，只在建置或審查證明必要時才改，改的地方用 `// [修正]` 註解標出。目前沒有任何修正。

## 建置與下載

專案用 RAM 連結（`280049C_RAM_lnk.cmd`，沒有 `_FLASH`），與 GPIO_EX2 相同。下載後斷電程式就消失，重新上電要重新下載。

1. 第一次（產生 `Debug/makefile`）：用 headless CCS 就地匯入並建置，workspace 用暫存目錄，不動使用者的 IDE workspace。
   
   ```bat
   C:\ti\ccs2101\ccs\eclipse\ccs-server-cli.bat -workspace <暫存ws> -application com.ti.ccs.apps.importProject -ccs.location <repo>\projects\Timer_lab\TIMER0_EX
   C:\ti\ccs2101\ccs\eclipse\ccs-server-cli.bat -workspace <暫存ws> -application com.ti.ccs.apps.buildProject -ccs.projects TIMER0_EX
   ```
   
   或在 CCS IDE 匯入 `projects/Timer_lab/TIMER0_EX` 後 Build。

2. 之後：`ccs_build(project="TIMER0_EX")`。`tools/JEV_accel/config.json` 已用 `path` 登記這個巢狀專案，回傳裡的 `map` 應是 `ok: true`、`mode: "ram"`。

3. 下載執行：先 `ccs_env` 確認 XDS110 沒被佔用，再 `ccs_load(project="TIMER0_EX", run=true)`。備用：在 `TIMER0_EX/tools/` 執行 DSS 腳本 `flash_and_run.js`（輸出檔與 ccxml 是相對 `tools/` 的路徑）。

4. 要交給 IDE 或其他工具用探棒前，先 `ccs_release`。

選用檢查：在除錯器看 `CpuTimer0.InterruptCount`，每秒應增加約 5。

## 量測（第 16 頁 Step 5）

示波器：2026-10-13 現場使用 RIGOL MSO5104（IP `192.168.137.50`，TCP `5555`），取代原先預定的 Keysight。課程的 Timer0 與量測目標不變。操作見 [RIGOL Wiki](../../docs/wiki/rigol-scope.md)，流程研究見 [Timer 流程加速](../../docs/wiki/timer-flow-performance.md)。

接線：CH1 探棒 10X 接 J8 pin 80（GPIO0），地夾接 GND。

設定（照第 16 頁例圖 1.00 V/div、100 ms/div）：

| 項目     | 設定                                |
| ------ | --------------------------------- |
| CH1    | 1 V/div，DC，探棒 10X                 |
| Offset | **−1.65 V**（RIGOL 與 Keysight 的符號相反） |
| 時基     | 100 ms/div（全螢幕 1 s，約 2.5 個週期）     |
| 觸發     | Edge，CH1，上升緣，1.65 V，sweep NORM    |

步驟：

1. 先 `ccs_env`，再建置與校驗下載；設定 CH1 10X、DC、1 V/div、offset −1.65 V、100 ms/div、水平偏移 0、上升緣觸發 1.65 V、NORM。
2. 等待完整一秒畫面更新，再單次擷取，確認 STOP 後讀資料。`jev_check_frame(view="period", min_periods=2, apply=true)` 檢查週期畫面；不得使用 edge autoframe 把時基縮到 ns。
3. 讀取 FREQ／PER／PWID／NWID／PDUT／VTOP／VBASE。這版 RIGOL 的 PDUT 回傳比例（0.5 = 50%），不能直接拿 0.5 對照百分比標準；測試腳本保留原始值並換算。
4. RIGOL 量測查詢會重新打開 Measure 選單；完成所有查詢後依 JEV 偵測結果關閉，避免盲按 MOFF。使用同一次凍結的資料重新核對選單，不重跑量測查詢。
5. 通過畫面與數值驗收後，留存白底 PNG；此台需在本機反相。自動化入口：在 `tools/JEV_accel` 用 `.venv` 執行 `bench/timer_flow.py --mode optimized --runs 1`，結果在忽略的 `results/`。
6. `CpuTimer0.InterruptCount` 檢查要在同一次下載連線中進行：halt／read_var → run 約 4 秒 → halt／read_var，預期約增加 20 次，再恢復執行與重新擷取。釋放後重新連線本機會進 Boot ROM，不可將重連後的 0 當成原程式的計數結果。

合格標準：

| 項目        | 標準           |
| --------- | ------------ |
| FREQ      | 2.5 Hz ± 1 % |
| PER       | 0.4 s ± 1 %  |
| PWID／NWID | 0.2 s ± 1 %  |
| PDUT      | 49–51 %（以百分比表示） |
| VTOP      | 約 3.3 V      |
| VBASE     | 約 0 V        |

若畫面是平的：先 `jev_diagnose_capture`，再確認程式在跑（`InterruptCount` 有增加）、探棒在 J8 pin 80。

報告：上表是操作設定，不是報告內容的全部。量測當下先存一份 `scope_status` 輸出（取樣率、記憶深度、頻寬限制、探棒倍率），並記下探棒型號與接地方式（長地夾或短接地彈簧）；VTOP 偏低的原因待查，接地方式尤其要記。簡報要有「量測設備與設定」頁，欄位見 `docs/wiki/board-pins.md` 的「量測簡報必備：設備與設定頁」。

## 操作界線

- 不修改其他專案（LED_test、Feedback_test、Serial_Plotter、Oscilloscope_read）。
- 講義 PDF、截圖、報告不進倉庫。
- `Debug/` 是編譯結果，依 `.gitignore` 不進版控。
