# CCS LLM Wiki

給之後的 LLM 用的 CCS / C2000 操作手冊。寫程式、編譯、除錯時先讀版本資料夾裡的說明，不要反組譯 CCS。

目前版本：[LLM_WIKI](LLM_WIKI/README.md)（2026-09-22 初建）

## LED_test

[LED_test](LED_test) 是 LAUNCHXL-F280049C 的 LED 範例：紅燈 GPIO23 與綠燈 GPIO34 交替閃爍。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

`LED_test/tools/flash_and_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/LED_test.out`，再從 `tools/` 執行這個腳本。

## Feedback_test

[Feedback_test](Feedback_test) 是 LAUNCHXL-F280049C 的自回授測試：GPIO0 讀回、SCIB 內部 loopback，再由 SCIA（115200）送出結果並進入 echo。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

`Feedback_test/tools/flash_and_run.js` 與 `restart_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/Feedback_test.out`，再從 `tools/` 執行。

## Serial_Plotter

[Serial_Plotter](Serial_Plotter) 是 LAUNCHXL-F280049C 的串流繪圖範例：DAC A 在 DACOUTA 輸出 256 階正弦，ADC A 對同一腳（ADCINA0）取樣，SCIA 以 500 Hz、115200 送出 `dac,adc`。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

用 Chrome 或 Edge 打開 [web/scope.html](Serial_Plotter/web/scope.html) 即可畫這兩條線。`tools/flash_and_run.js` 與 `restart_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/Serial_Plotter.out`，再從 `tools/` 執行。

## Oscilloscope_read

[Oscilloscope_read](Oscilloscope_read) 是 LAUNCHXL-F280049C 的 GPIO Example 2：GPIO0 當輸入，經 qualification 反相驅動 GPIO6。用 CCS 匯入 [GPIO_EX2](Oscilloscope_read/GPIO_EX2) 即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

做到哪裡、上升緣截圖與還沒量的項目見 [STATUS.md](Oscilloscope_read/STATUS.md)。操作規格在 [TASK.md](Oscilloscope_read/TASK.md)。

## MCP

[MCP](MCP) 只放本機 MCP 伺服器，一台伺服器一個子夾。目前有 [rigol-mso](MCP/rigol-mso)，用區域網路控制 RIGOL MSO5000。
