# CCS LLM Wiki

給之後的 LLM 用的 CCS / C2000 操作手冊。寫程式、編譯、除錯時先讀版本資料夾裡的說明，不要反組譯 CCS。

目前版本：[LLM_WIKI](docs/wiki/README.md)（2026-09-22 初建）

接手開發的 agent 請先讀 [AGENTS.md](AGENTS.md)：開始前閱讀相關 Wiki 與專案規格，完成後更新進度，將可重用的新知識寫回 Wiki。Claude Code 的入口是 [CLAUDE.md](CLAUDE.md)，引用同一份指引。

## 目前工作目標與專案狀態

2026-10-13：目前目標是加速既有 CCS／JEV／示波器操作流程，減少重複搜尋、工具往返與連線初始化，同時維持結果的正確性與可驗證性。JEV 用於適合的決策環節，確定性檢查與實測證據仍須保留。

| 專案                                             | 開發狀態                                                     |
| ---------------------------------------------- | -------------------------------------------------------- |
| GPIO qualification（Oscilloscope_read／GPIO_EX2） | [終止開發](projects/Oscilloscope_read/STATUS.md)，保留歷史程式與量測紀錄 |
| Serial_Plotter                                 | [終止開發](projects/Serial_Plotter/STATUS.md)，保留歷史程式與工具      |
| Feedback_test                                  | [終止開發](projects/Feedback_test/STATUS.md)，保留歷史程式與工具       |
| LED_test                                       | [終止開發](projects/LED_test/STATUS.md)，保留歷史程式與工具            |

除非使用者明確要求重啟，這四個專案不再新增功能、補做實驗或完成舊待辦，也不主動安排其上板、燒錄或量測。下方相關操作說明保留供歷史參考。Timer_lab 不在此次終止清單內；後續工作優先服務流程加速目標，不自動展開新的周邊實驗。

## 目錄與本機資料

`projects/` 放 CCS 實驗專案，`tools/` 放 JEV 與示波器 MCP，`docs/wiki/` 放操作手冊。直接在這個倉庫開發；Cursor 與 Claude Code 的工具也從 `tools/` 執行。

私人資料集中在倉庫旁的 `../CCS_private_archive/`：`projects/GPIO_EX1` 是未公開專案，`reports/` 放講義、報告及素材，`images/` 放私人圖片，`installers/` 保留 CCS 安裝 ZIP。這些資料不在 Git 保存範圍，需自行備份。

JEV 的公開專案路徑相對於 `tools/JEV_accel/` 解析，私人專案透過該工具的 `config.local.json` 登記。Python `.venv/`、本機設定、操作紀錄與編譯產物不加入 Git。專案搬移後，第一次使用須以 CCS 重新匯入新的專案位置並建置，產生 `Debug/`。MCP 設定更新後須重新連線或重啟 Cursor／Claude Code。

## LED_test

[LED_test](projects/LED_test) 是 LAUNCHXL-F280049C 的 LED 範例：紅燈 GPIO23 與綠燈 GPIO34 交替閃爍。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

`projects/LED_test/tools/flash_and_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/LED_test.out`，再從 `tools/` 執行這個腳本。

## Feedback_test

[Feedback_test](projects/Feedback_test) 是 LAUNCHXL-F280049C 的自回授測試：GPIO0 讀回、SCIB 內部 loopback，再由 SCIA（115200）送出結果並進入 echo。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

`projects/Feedback_test/tools/flash_and_run.js` 與 `restart_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/Feedback_test.out`，再從 `tools/` 執行。

## Serial_Plotter

[Serial_Plotter](projects/Serial_Plotter) 是 LAUNCHXL-F280049C 的串流繪圖範例：DAC A 在 DACOUTA 輸出 256 階正弦，ADC A 對同一腳（ADCINA0）取樣，SCIA 以 500 Hz、115200 送出 `dac,adc`。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

用 Chrome 或 Edge 打開 [web/scope.html](projects/Serial_Plotter/web/scope.html) 即可畫這兩條線。`tools/flash_and_run.js` 與 `restart_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/Serial_Plotter.out`，再從 `tools/` 執行。

## Oscilloscope_read

[Oscilloscope_read](projects/Oscilloscope_read) 是 LAUNCHXL-F280049C 的 GPIO Example 2：GPIO0 當輸入，經 qualification 反相驅動 GPIO6。用 CCS 匯入 [GPIO_EX2](projects/Oscilloscope_read/GPIO_EX2) 即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

歷史進度與量測紀錄見 [STATUS.md](projects/Oscilloscope_read/STATUS.md)。原實驗操作規格在 [TASK.md](projects/Oscilloscope_read/TASK.md)；專案已終止開發，舊待辦不再執行。

## Timer_lab

[Timer_lab](projects/Timer_lab) 是 LAUNCHXL-F280049C 的 Timer0 實驗：Timer0 每 0.2 秒中斷一次，ISR 切換 GPIO0（J8 pin 80），輸出 2.5 Hz 方波。用 CCS 匯入 [TIMER0_EX](projects/Timer_lab/TIMER0_EX) 即可建置（RAM 連結）。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

操作規格在 [TASK.md](projects/Timer_lab/TASK.md)，進度在 [STATUS.md](projects/Timer_lab/STATUS.md)。`TIMER0_EX/tools/timer_math.py` 不需硬體即可驗算計時設定；`tools/flash_and_run.js` 的路徑相對於 `tools/`。

## Timer_HW

[Timer_HW](projects/Timer_HW) 是 Timer 與中斷作業（`4_TIMER_Interrupt_HW.pdf`）。同一個 Timer0 產生 100 Hz 與 500 Hz 方波（GPIO1、GPIO2），並用 GPIO 脈波量 ISR 執行時間。用 CCS 匯入 [TIMER_HW](projects/Timer_HW/TIMER_HW) 即可建置（RAM 連結），`Init.h` 的 `HW_PART` 切換工作 1／2。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。

操作規格在 [TASK.md](projects/Timer_HW/TASK.md)，進度與實測值在 [STATUS.md](projects/Timer_HW/STATUS.md)。`TIMER_HW/tools/timer_math.py` 不需硬體即可驗算 PRD 與輸出頻率。

## MCP

給人閱讀的 [示波器網路設定](docs/wiki/scope-network-setup.md) 說明兩台示波器與 Windows 網卡的 IP、遮罩、閘道、DNS、面板操作與連線驗證。

[MCP](tools/MCP) 只放本機 MCP 伺服器，一台伺服器一個子夾。目前有 [scope-rigol-mso5000](tools/MCP/scope-rigol-mso5000)（RIGOL MSO5000）與 [scope-keysight-dsox4000](tools/MCP/scope-keysight-dsox4000)（Keysight DSO-X 4034A），都用區域網路控制。

## JEV_accel

[JEV_accel](tools/JEV_accel) 是示波器與 CCS 的規則優先工具：先用確定性規則判斷，判斷不了再問 Jev。示波器的用法在 [tools/JEV_accel/README.md](tools/JEV_accel/README.md)，實測的加速幅度與 Jev 正確率在 [tools/JEV_accel/JEV_PERFORMANCE.md](tools/JEV_accel/JEV_PERFORMANCE.md)。
