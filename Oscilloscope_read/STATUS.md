# GPIO 實驗進度

來源是 `2_GPIO_lecture.pdf` 第 30–36 頁，實驗名稱是 *LAB Experiment - GPIO input sample and output control*。操作規格在 [TASK.md](TASK.md)。裝置是 LAUNCHXL-F280049C（TMS320F280049C）。

示波器與開發板目前已從這台電腦抽離。下面是截至抽離前做完與還沒做的項目。

## 已完成

- [TASK.md](TASK.md) 已依第 30–36 頁寫好實驗規格。
- 本機 `D:\code\_TI_CCS_no_chinese\GPIO_EX1` 是 Example 1：GPIO0 輸出高準位後空轉。這份程式已下載到開發板並執行。該專案不在這個倉庫裡。
- GPIO0 停在高準位時，示波器讀到約 **3.37 V**。
- 上升緣截圖是 [GPIO0_rise.png](GPIO0_rise.png)。時基 **20.0 ns/div**、**1.00 V/div**、上升緣觸發 **1.50 V**。示波器算出的上升時間是 **11.775 ns**。講義第 33 頁手寫標的是 **8 ns**。
- [GPIO_EX2](GPIO_EX2) 已寫成 Example 2：GPIO0 輸入、GPIO6 反相輸出，`GPAQSEL1.GPIO0 = 2`、`QUALPRD0 = 255`。註解寫明第 35 頁要把這兩欄改成 0。Debug 組態編譯沒有 error。這份沒有下載到板上。

## 還沒完成

- Example 1 的另一張圖：第 33 頁左邊那種高準位直流波形（約 5 μs/div）。目前只有數字 3.37 V，沒有這張截圖。
- Example 2 整段量測都還沒做。板上最後跑的是本機 `GPIO_EX1`，不是 `GPIO_EX2`。
- 第 35 頁：`GPAQSEL1.GPIO0 = 0`、`QUALPRD0 = 0` 時，同時看 GPIO0 與 GPIO6，並確認切換時 GPIO6 是否抖動。
- 第 36 頁：`GPAQSEL1.GPIO0 = 2`、`QUALPRD0 = 255` 時，確認 GPIO6 是否只乾淨切換一次。
- 這兩頁的探棒位置是 GPIO0 = J8 pin 80、GPIO6 = J8 pin 78。講義沒有寫 GPIO0 的外部信號從哪來。

## 倉庫裡沒有的檔

- 講義 PDF 頁面標了 CONFIDENTIAL，沒有放進這個公開倉庫。
- `GPIO_EX2/Debug/` 是編譯結果，依倉庫的 `.gitignore` 不進版控。
