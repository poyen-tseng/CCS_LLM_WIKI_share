# TMS320F280049C 開發規格

課堂用的兩份 PDF 都已讀過目錄與開發相關章節，沒有把全文貼進來。回到 [README.md](README.md)。板子接線見 [board-pins.md](board-pins.md)。

| 雲端檔                      | 實際文件                                       | 版次                |
| ------------------------ | ------------------------------------------ | ----------------- |
| `TMS320F280049C_精簡版.pdf` | Datasheet SPRS945E                         | 2017-01 至 2020-04 |
| `TMS320F280049C_詳細版.pdf` | Technical Reference Manual SPRUI33D，2745 頁 | 2015-11 至 2020-09 |

官網較新的是 [datasheet Rev. H](https://www.ti.com/lit/ds/symlink/tms320f280049c.pdf) 與 [SPRUI33H TRM](https://www.ti.com/lit/ug/sprui33h/sprui33h.pdf)（2024-06）。章名大致相同，頁碼可能不同。寫程式時以雲端這兩份的暫存器行為為課堂依據；若和本機 `C:\ti\C2000Ware_5_00_00_00` 的標頭衝突，以標頭與 TRM 章名為準，不要只靠舊頁碼。勘誤、DCL 與其他外部文件見 [references.md](references.md)。

板上晶片是 **F280049CPZS**：100-pin PZ LQFP，14.0 mm × 14.0 mm。C 字尾表示有 InstaSPIN-FOC。同系列還有 64-pin PM、56-pin RSH，腳數比較少，不要把那些腳位數套到這塊 LaunchPad。

## 這顆與之後實驗有關的數量

來源：精簡版 Table 3-1 與第 1 章。100-pin PZ 的 F280049C：

| 項目                      | 數量或上限                                                            |
| ----------------------- | ---------------------------------------------------------------- |
| C28x                    | 100 MHz，FPU32、TMU type 0、VCU-I                                   |
| CLA type 2              | 有，100 MHz                                                        |
| CPU timer               | 3                                                                |
| Watchdog / NMIWD        | 各 1                                                              |
| Flash                   | 256 KB（128 KW），兩個 128 KB bank                                    |
| RAM                     | 100 KB（50 KW）：Dedicated/Local shared 36 KB + Global shared 64 KB |
| GPIO                    | 40（另有 21 個 AIO）                                                  |
| 外部中斷                    | 5                                                                |
| ADC                     | 3 顆 12-bit，各 3.45 MSPS，轉換時間 290 ns；100-pin 共 21 個單端通道            |
| CMPSS                   | 7（每組兩個比較器與內部 DAC）                                                |
| PGA                     | 7，增益 3、6、12、24                                                   |
| 緩衝 DAC                  | 2                                                                |
| ePWM / HRPWM            | 16 通道，HRPWM 解析度 150 ps，含 dead-band 與 trip zone                   |
| eCAP                    | 7（其中 2 個有 HRCAP）                                                 |
| eQEP                    | 2                                                                |
| SDFM                    | 4 通道                                                             |
| CAN / SCI / SPI         | 各 2                                                              |
| I2C / LIN / PMBus / FSI | 各 1                                                              |
| DMA                     | 6 通道                                                             |
| CLB                     | F280049C 有 4 tiles                                               |

電源是 **1.2 V 核心、3.3 V I/O**。內部 VREG 或 DC-DC 可從單一 3.3 V 產生 1.2 V。兩顆零腳位內部振盪器 **INTOSC1、INTOSC2 都是 10 MHz**。重設後系統 PLL 的預設來源是 INTOSC2（datasheet Table 5-12 註）。外部時脈可以是 X1/X2 的晶振，或只打進 X1 的單端時脈。

## 這個專案的時脈

`f28004x_sysctrl.c` 的 `InitSysCtrl()` 呼叫：

```c
InitSysPll(XTAL_OSC, IMULT_10, FMULT_0, PLLCLK_BY_2);
```

C2000Ware `device.h` 對同一組設定的註解是：

`PLLSYSCLK = 20 MHz (XTAL_OSC) * 10 (IMULT) * 1 (FMULT) / 2 (PLLCLK_BY_2)`

也就是 **100 MHz**，等於這顆 CPU 的上限。板上晶振是 20 MHz，見 [board-pins.md](board-pins.md)。`DEVICE_OSCSRC_FREQ` 在 `C:\ti\C2000Ware_5_00_00_00\device_support\f28004x\common\include\device.h` 定義為 `20000000U`。

之後算 Timer、PWM、SCI 鮑率時，先確認 `InitSysPll` 沒被改掉。SCI 與 SPI 走 LSPCLK（`LOSPCP`），不是每一顆周邊都直接吃 100 MHz。周邊時脈閘在 `PCLKCRx`。

## 記憶體（寫 linker 時用）

來源：精簡版 Table 6-1。位址是 C28x 的 word address。

| 區塊               | 大小                 | 起始                         | 結束                 | 備註                                 |
| ---------------- | ------------------ | -------------------------- | ------------------ | ---------------------------------- |
| M0 RAM           | 1 KW               | `0x00000000`               | `0x000003FF`       |                                    |
| M1 RAM           | 1 KW               | `0x00000400`               | `0x000007FF`       |                                    |
| PIE vector table | 512 W              | `0x00000D00`               | `0x00000EFF`       |                                    |
| LS0–LS7          | 各 2 KW             | `0x00008000` 起，每塊 +`0x800` | LS7 到 `0x0000BFFF` | CLA 可設定，可保護                        |
| GS0–GS3          | 各 8 KW             | `0x0000C000` 起             | GS3 到 `0x00013FFF` | DMA 可存取                            |
| Flash Bank0      | 64 KW              | `0x00080000`               | `0x0008FFFF`       | ECC，可加密                            |
| Flash Bank1      | 64 KW              | `0x00090000`               | `0x0009FFFF`       | 同上                                 |
| Boot ROM         | datasheet 標 64K×16 | `0x003F0000`               | `0x003FFFBF`       | 這段跨距是 65472 words。最後 64 words 是下一列 |
| Reset vectors    | 64 W               | `0x003FFFC0`               | `0x003FFFFF`       | 與上一列合起來才是 64 KW                    |

F280049 有兩個 Flash bank。一次只能對其中一個做 erase/program，程式可以從另一個 bank 或從 RAM 執行。不要在正在擦寫的那個 bank 上讀取。

專案的 RAM/Flash 放置仍看 `280049C_RAM_lnk.cmd` 與 `280049C_FLASH_lnk.cmd`，不要憑這張表改 cmd，除非要換燒錄方式。

## 開機

重設後 Boot ROM 會取樣 boot mode 腳。取樣期間那些 GPIO 是輸入，內部上拉被關掉。除錯環境下 Boot ROM 花的時間跟當時的 SYSCLK 有關，PLL 可能還沒開。

LaunchPad 的 boot 腳是 GPIO32 與 GPIO24，開關 S2 上下顛倒。模式表在 [course-notes.md](course-notes.md) 與 [board-pins.md](board-pins.md)。TRM 第 4 章（約第 589 頁，SPRUI33D）有 SCI / I2C / parallel GPIO boot 的流程。

## 暫存器要翻 TRM 哪一章

頁碼是雲端 **SPRUI33D**。官網 SPRUI33H 請用章名搜尋。

| 以後要寫                          | TRM                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------- |
| 時脈、PLL、CPU Timer、Watchdog、PIE | 第 3 章。時脈 3.7（約第 98 頁），CPU Timer 3.8（約第 107 頁），PIE channel map 3.5.5（約第 87 頁） |
| 開機與 boot loader               | 第 4 章，約第 589 頁。GPIO boot 腳位 4.6.9，約第 620 頁                                   |
| GPIO、MUX、上拉、資料暫存器             | 第 8 章，約第 857 頁。Mux 8.5，`GPIO_CTRL_REGS` 約第 871 頁，`GPIO_DATA_REGS` 約第 942 頁   |
| X-BAR、GPIO Output X-BAR       | 第 9 章章首約第 965 頁；9.2 約第 968 頁                                                 |
| ADC                           | 第 13 章，約第 1439 頁。類比子系統總覽第 12 章，約第 1409 頁                                     |
| PGA                           | 第 14 章                                                                       |
| DAC                           | 第 15 章，約第 1633 頁                                                             |
| CMPSS                         | 第 16 章，約第 1647 頁                                                             |
| ePWM、HRPWM、Trip-Zone          | 第 18 章，約第 1767 頁。Trip-Zone 18.9，約第 1819 頁                                    |
| eCAP                          | 第 19 章，約第 2021 頁                                                             |
| eQEP                          | 第 21 章，約第 2080 頁                                                             |
| SPI                           | 第 22 章，約第 2143 頁                                                             |
| SCI（UART）                     | 第 23 章，約第 2185 頁。鮑率在 23.12                                                   |
| I2C                           | 第 24 章，約第 2223 頁                                                             |

Datasheet 第 4 章是腳位與 pinmux 表，第 5 章是電氣與時脈規格，第 6 章是記憶體。GPIO 每個腳的 MUX 編碼以 datasheet 4.4 與 TRM 8.5 為準，講義裡的 GPIO6 例子只是其中一列。
