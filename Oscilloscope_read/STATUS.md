# GPIO 實驗進度

來源是 `2_GPIO_lecture.pdf` 第 30–36 頁，實驗名稱是 *LAB Experiment - GPIO input sample and output control*。操作規格在 [TASK.md](TASK.md)。裝置是 LAUNCHXL-F280049C（TMS320F280049C）。示波器是 RIGOL MSO5104，操作方式見 wiki 的 `rigol-scope.md`。

2026-10-07 量測全部完成。報告 pptx 在本機，不進倉庫。

## Example 1：GPIO0 輸出高準位

- 本機 `D:\code\_TI_CCS_no_chinese\GPIO_EX1` 的程式：GPIO0 輸出高準位後空轉。該專案不在這個倉庫裡。
- 高準位直流：Vavg 3.27 V、Vmax 3.34 V、Vmin 3.21 V（5 µs/div、1 V/div）。截圖 `GPIO0_high_dc.png`。
- 上升時間：11.8 ns（10%–90%，Vbase 0.17 V、Vtop 3.66 V），講義手寫 8 ns，p29 規格 ≤ 8 ns。量測含示波器 100 MHz 頻寬與 10X 探棒影響。設定 5 ns/div、600 mV/div、offset -1.65 V、觸發 1.95 V。截圖 `GPIO0_rise_10_90.png`（量測線在 10%／90%）與 `GPIO0_rise_swing.png`（量測線在高低準位）。
- 舊的 `GPIO0_rise.png`（20 ns/div）沒有置中，已不使用。

## Example 2：GPIO0 輸入、GPIO6 反相輸出

- [GPIO_EX2](GPIO_EX2) 已下載執行。最後留在板上與原始碼裡的是第 34／36 頁那組：`GPAQSEL1.GPIO0 = 2`、`QUALPRD0 = 255`。第 35 頁那組（兩欄都是 0）是暫時改 `Init.c` 編譯量完，再改回來。
- 探棒：CH1 = GPIO0（J8 pin 80），CH2 = GPIO6（J8 pin 78），都是 10X。GI 關閉時 GPIO0 約 0 V、GPIO6 約 3.3 V，確認 J8 pin 78 就是 GPIO6、反相邏輯正確。
- GI 三角波（0–2.5 V、1 Hz 與 0.1 Hz）當輸入時，兩組設定的 GPIO6 都只乾淨切換一次。脈寬觸發 12 秒內抓不到小於 100 µs 的突波。乾淨的斜坡不會讓 GPIO 輸入抖動。
- 改用杜邦線把 J8 pin 80 碰觸 3.3 V 再放開（人為彈跳）：
  - QSEL = 0：碰觸後 GPIO0 彈跳，GPIO6 跟著出現窄突波。截圖 `ex2_q0_touch.png`、`ex2_q0_release.png`、`ex2_q0_zoom.png`。
  - QSEL = 2、CTRL = 255：試了三次碰觸都沒有彈跳，GPIO6 單次切換，比 GPIO0 晚 33.1 µs。截圖 `ex2_q2_touch.png`、`ex2_q2_release.png`、`ex2_q2_delay.png`。
- GI 脈衝濾除測試（0–2.5 V）：
  - QSEL = 0、10 µs 脈衝：GPIO6 跟著切換（低 9.84 µs）。`ex2_q0_pulse10us.png`
  - QSEL = 2、CTRL = 255、10 µs 脈衝：被濾除，GPIO6 保持高。`ex2_q2_pulse10us.png`
  - QSEL = 2、CTRL = 255、60 µs 脈衝：通過，約 31 µs 後切換，低 61.1 µs。`ex2_q2_pulse60us.png`
- 取樣週期 2 × 255 × 10 ns = 5.1 µs，6 次取樣約 25.5–30.6 µs，與量到的 33.1 µs 延遲和濾除結果一致。

## 還沒完成

- 報告第 5 頁的接線照片待補。

## 倉庫裡沒有的檔

- 講義 PDF 頁面標了 CONFIDENTIAL，沒有放進這個公開倉庫。報告與截圖也不放。
- `GPIO_EX2/Debug/` 是編譯結果，依倉庫的 `.gitignore` 不進版控。
