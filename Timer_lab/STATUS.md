# Timer 實驗進度

來源是 `3_TIMER_lecture.pdf` 第 12–16 頁，實驗名稱是 *LAB experiment - Timer0 Module*。操作規格在 [TASK.md](TASK.md)。裝置是 LAUNCHXL-F280049C（TMS320F280049C）。示波器預定用 Keysight DSO-X 4034A，操作方式見 wiki 的 `keysight-scope.md`。

2026-10-12：沒有開發板與示波器，先完成不需硬體的部分。

## 已完成（無硬體）

- [TIMER0_EX](TIMER0_EX)：由 `Oscilloscope_read/GPIO_EX2` 複製改名，拿掉 `Comm.c/.h`。`main.c`、`Init.c`、`Init.h` 照講義第 13–16 頁重寫。`TIMER0_ISR` 沿用老師版 `f28004x_defaultisr.c`，沒有任何 `[修正]`。
- Headless CCS 匯入與建置：0 errors、0 warnings（CCS 21.0.1、cgt 25.11.1.LTS、RAM 連結）。
- `ccs_map_check(mode="ram")` ok：entry `_c_int00` 0x343、codestart 0x0、`_main` 0x3f6、`_TIMER0_ISR` 0x8034、`_Init_GPIO` 0x399、`_Init_PIE` 0x3b1、`_Init_CpuTimer` 0x3c9。專案裡只有一個 `TIMER0_ISR` 定義。
- `tools/timer_math.py` PASS：PRD = 20000000、TDDR = 0 → T = 0.20000001 s，方波 2.4999999 Hz、duty 50 %。
- `tools/flash_and_run.js` 已備好（由 LED_test 的腳本改輸出檔名），尚未在板上跑過。
- `JEV_accel/config.json` 已登記 `TIMER0_EX` 為 RAM 模式。

## 還沒完成（要硬體）

- [ ] 用 `ccs_load` 下載執行（或 `tools/flash_and_run.js`）。
- [ ] 除錯器確認 `CpuTimer0.InterruptCount` 每秒約加 5。
- [ ] 示波器 CH1 接 J8 pin 80，100 ms/div 截圖。
- [ ] `ks_measure` FREQ／PER／PWID／NWID／PDUT／VTOP／VBASE，對照 TASK.md 合格標準。
- [ ] （選做）GPIO0 外接 LED 看閃爍。

## 已知工具問題

- `ccs_build` 給絕對路徑時，gmake 在正確資料夾執行，但它內建的 map 檢查用專案名到 `D:/code/_TI_CCS_no_chinese/TIMER0_EX` 找 `.map`，報「not found」。單獨呼叫 `ccs_map_check` 給絕對路徑則正常。
- `ccs_env` 只掃 `D:/code/_TI_CCS_no_chinese` 的直接子資料夾，不會列出 `Timer_lab/TIMER0_EX`。

## 倉庫裡沒有的檔

- 講義 PDF 頁面標了 CONFIDENTIAL，沒有放進這個公開倉庫。
- `TIMER0_EX/Debug/` 是編譯結果，依倉庫的 `.gitignore` 不進版控。
