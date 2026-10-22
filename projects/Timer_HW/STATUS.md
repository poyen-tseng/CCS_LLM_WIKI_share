# Timer 中斷作業進度

來源是 `4_TIMER_Interrupt_HW.pdf`（*Homework - Timer and Interrupt module*）。操作規格在 [TASK.md](TASK.md)。裝置是 LAUNCHXL-F280049C（TMS320F280049C），示波器 RIGOL MSO5104。

## 2026-10-22：建置、上板、量測、簡報

### 程式（建置通過）

- [TIMER_HW](TIMER_HW)：由 `projects/Timer_lab/TIMER0_EX` 複製改名（不含 `Debug/`），`Init.h` 用 `#define HW_PART 1/2` 切換工作 1／2。改動在 `Init.h`、`Init.c`、`f28004x_defaultisr.c` 的 `TIMER0_ISR`，都標 `// [作業]`；沒有 `[修正]`。
- 工作 1：PRD = 500000（ISR 每 5 ms），ISR 第一行 `GPASET` GPIO2、翻轉 GPIO1、最後一行 `GPACLEAR` GPIO2。
- 工作 2：PRD = 100000（ISR 每 1 ms），脈波腳換成 GPIO0；每次翻 GPIO2，`static` 計數器每 5 次翻 GPIO1。
- `tools/timer_math.py`：兩個 HW_PART 都 PASS（工作 1：ISR 5.00001 ms、GPIO1 99.9998 Hz；工作 2：ISR 1.00001 ms、GPIO2 499.995 Hz、GPIO1 99.999 Hz）。
- 第一次用 `ccs-server-cli.bat` 就地匯入並建置。注意：在 PowerShell 呼叫時，`-ccs.location` 會在點號處被拆開，只印出 usage；改用 Bash 呼叫才成功。CCS 21.0.1、cgt 25.11.1.LTS、RAM 連結，0 errors、0 warnings。編譯指令沒有 `-O`，`cl2000 --help` 寫明預設 `--opt_level=off`。
- `tools/JEV_accel/config.json` 已登記 `TIMER_HW`（ram）。本次 jev-ccs 沒有重新讀 config，`ccs_build`／`ccs_load` 改給絕對路徑，map 檢查 ok。
- 原始碼目前停在 `HW_PART 1`，`.out` 也是工作 1 的建置。板上最後跑的是工作 2（RAM，斷電即消失）。

### 接線（硬體實測確認）

CH1 → GPIO1（J8 79）、CH2 → GPIO2（J8 76）、CH3 → GPIO0（J8 80）。三支探棒都用長地夾，接 GPIO0 同一列的 GND（J6 60）。探棒：CH1 Tektronix P2220（200 MHz、10 MΩ／16 pF、10X），CH2、CH3 HP9100（100 MHz、10X，型號照使用者回報）。

GPIO2 的接頭位置是從電路圖換算出來的（J8 圖上第 36 腳 + 40 = 76）。工作 1 中 CH2 量到 200 Hz、約 210 ns 的脈波，而 CH1 是 100 Hz 方波，兩個訊號不同，確認接到的是 GPIO2。工作 2 中 CH3 量到 1 kHz 脈波，確認 GPIO0。

### 量測（硬體實測，RIGOL MSO5104 韌體 00.01.03.03.00）

所有讀值都來自單次擷取、STOP 後的同一筆資料。通道 10X、DC、1 MΩ、頻寬限制 OFF。量測時擷取模式是 Normal。

| 工作 | 信號 | 讀值 | 標準 | 結果 |
| --- | --- | --- | --- | --- |
| 1 | GPIO1 | FREQ 100.01 Hz、PER 9.9993 ms、PWID 4.9996 ms、NWID 4.9997 ms、PDUT 0.5（50 %）、VTOP 3.337 V、VBASE 0.042 V | 100 Hz ±1 %、49–51 % | 通過 |
| 1 | GPIO2 脈波 | FREQ 200.01 Hz、PER 4.9996 ms | 200 Hz ±1 % | 通過 |
| 2 | GPIO1 | FREQ 100.01 Hz、PWID／NWID 4.9997 ms、PDUT 0.5 | 100 Hz ±1 % | 通過 |
| 2 | GPIO2 | FREQ 500.03 Hz、PWID 0.99996 ms、NWID 0.99992 ms、PDUT 0.50001 | 500 Hz ±1 % | 通過 |
| 2 | GPIO0 脈波 | FREQ 1000.1 Hz、PER 0.99994 ms | 1 kHz ±1 % | 通過 |

ISR 執行時間（脈波在 1.65 V 處的寬度；從 CSV 線性內插算出，脈寬沒有預設合格值）：

| 工作 | 情況 | 次數 | 脈寬 | 約合 SYSCLK |
| --- | --- | --- | --- | --- |
| 1 | 每次 ISR | 4 | 209.79–210.05 ns（約 209.9 ns） | 21 |
| 2 | 沒有翻轉 GPIO1 | 4 | 359.53–359.91 ns（約 359.7 ns） | 36 |
| 2 | 翻轉 GPIO1（每 5 次一次） | 3 | 369.71–369.79 ns（約 369.7 ns） | 37 |

- 放大畫面（工作 1 50 ns/div；工作 2 100 ns/div）可以看到，方波邊緣落在脈波高準位之內：工作 1 GPIO1 在脈波上升後 112 ns 翻轉；工作 2 GPIO2 在 110 ns、GPIO1 在 272 ns 翻轉。
- 從脈波頻率回推 PRD：200.01 Hz → 100 MHz / 200.01 − 1 ≈ 499 974；1000.1 Hz → ≈ 99 989。示波器頻率讀值只到 0.01 Hz／0.1 Hz（50／100 ppm），PER 也比設計值短約 0.008 %，這在示波器時基與板上晶振的容差內。所以只能說量測和 PRD = 500000／100000 一致，分辨不出 ±1 或 ±10 的差異。
- 中斷計數（同一次下載連線內）：工作 1 從 536 到 2600，工作 2 從 6370 到 11770。兩次讀取的時間間隔沒有精確計時（約 4 秒睡眠加上工具往返），只用來確認中斷在持續發生，頻率以示波器量測為準。

### 量測當下遇到的問題

- 示波器一開始是出廠狀態（探棒 1X、AUTO）。已改為 10X、NORM。
- 2 ms/div 時，200 ns 的脈波被畫面抽點，幾乎看不見。概觀截圖改用 `:ACQ:TYPE PEAK`，加上 `:DISP:WBR 100`（波形亮度）。這兩個設定在 STOP 狀態下送出都會回 ok，但沒有生效；要在 RUN 狀態下送才會生效。量測值仍取自 Normal 模式。亮度最後已改回 50。
- `jev_check_frame` 的 period 檢查會要求 CH1 置中。多通道上下錯開的畫面一定違反這條，這次是刻意保留，其餘檢查都通過。畫面剛好是 2 個週期（1.998），門檻用 1.9。
- `scope_capture` 的 CSV 檔名只精確到秒，同一秒內的兩次擷取，後一次會覆蓋前一次。工作 1 本來擷取 5 次，只剩 4 筆。
- CH1 在邊緣後有明顯的振鈴，原因可能是長地夾，沒有再驗證。

### 資料位置（不進 Git）

截圖、CSV 與 `part1.json`／`part2.json` 放在 `../CCS_private_archive/reports/Timer_HW/data/part1|part2/`。量測當時 `tools/JEV_accel/results/` 的忽略規則只涵蓋最上層的 json／jsonl，子資料夾不會被忽略，所以沒有放在那裡（同日稍後已加 `results/*/`，見下方「Git 忽略規則」）。示波器 MCP 的原始檔留在 `tools/MCP/scope-rigol-mso5000/captures/`（已忽略）。

### 簡報

- [x] `../CCS_private_archive/reports/Timer_HW/20261022_TIMER中斷作業_第七組_<姓名>.pptx`，共 13 頁，用 python-pptx 在課程範本 `20261007_GPIO_第七組_<姓名>_template.pptx` 上製作（版面 `2_標題及物件`，保留範本的頁碼與製作者框）。內文中文用標楷體、英文用 Times New Roman，程式用 Courier New，全部 ≥ 16 pt。
- 內容：題目、解讀（工作 3 兩個工作都量）、J8 接線圖、PRD 計算、程式 2 頁（文字可編輯）、量測設備與設定 2 頁、工作 1／2 結果、ISR 時間、PRD 原因示意圖、結論與限制。每頁備忘稿都附資料來源。
- 截圖是 RIGOL 黑底原圖反相後的白底圖，沒有合成。反相後的顏色是 CH1 藍、CH2 紅、CH3 綠，簡報全篇用同一組通道配色。
- 檢查：pptx 技能的 `validate.py --original template.pptx` 通過；markitdown 檢查沒有殘留的占位文字；用本機 PowerPoint COM 逐頁匯出 PNG 檢查，修正了第 1、2、3、5、6、8、11、13 頁的排版。數值與 `part1.json`／`part2.json` 一致。
- 這個 Windows 環境沒有 AF_UNIX，pptx 技能附的 `thumbnail.py` 與 soffice 渲染無法執行；改用 `build_deck/export_png.ps1`（PowerPoint COM 唯讀開啟後匯出）。建置腳本與渲染圖放在同目錄的 `build_deck/`。
- 「量測設備與設定」頁的供電方式寫「USB（推定，未另行記錄）」，因為當天沒有記錄。
- 每頁演講者備忘稿：前面是 2–4 句口語說明（約 100–150 字，30–40 秒），分隔線之後保留原本的技術備註與 [Sources]。口語稿寫在 `build_deck.py` 的 `SPOKEN` 清單；重建後 `validate.py` 通過，投影片版面沒有改。

## 2026-10-22：Git 忽略規則

- 倉庫根 `.gitignore` 加入 `*.pdf`、`*.ppt`、`*.pptx`、`*.potx`、`*.doc`、`*.docx`，講義、範本、報告不會進入公開倉庫。`projects/Timer_lab/` 的講義 PDF 與 GPIO 範本已確認被忽略；它們之前也沒有被追蹤。
- `tools/JEV_accel/.gitignore` 加入 `results/*/`，結果子資料夾（截圖、CSV）不進 Git；`results/.gitkeep` 仍保留。

## 待辦

- [ ] 交件日確定後，修改簡報檔名的日期。
- [ ] （選做）改用短接地彈簧重量，確認 CH1 的振鈴是不是來自長地夾。
