# CCS LLM Wiki

給之後的 LLM 用的 CCS / C2000 操作手冊。寫程式、編譯、除錯時先讀版本資料夾裡的說明，不要反組譯 CCS。

目前版本：[v20260922-初建](v20260922-初建/README.md)

## LED_test

[LED_test](LED_test) 是 LAUNCHXL-F280049C 的 LED 範例：紅燈 GPIO23 與綠燈 GPIO34 交替閃爍。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

`LED_test/tools/flash_and_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/LED_test.out`，再從 `tools/` 執行這個腳本。

## Feedback_test

[Feedback_test](Feedback_test) 是 LAUNCHXL-F280049C 的自回授測試：GPIO0 讀回、SCIB 內部 loopback，再由 SCIA（115200）送出結果並進入 echo。用 CCS 匯入這個資料夾即可建置。需要 CCS，以及安裝在 `C:\ti\C2000Ware_5_00_00_00` 的 C2000Ware。`Debug/` 是編譯結果，沒有放進這個 repository。

`Feedback_test/tools/flash_and_run.js` 與 `restart_run.js` 的輸出檔與目標設定是相對於 `tools/` 的路徑。先在 CCS 建置出 `Debug/Feedback_test.out`，再從 `tools/` 執行。
