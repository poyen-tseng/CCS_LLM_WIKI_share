# LaunchPad 接腳與電路

板上是 LAUNCHXL-F280049C，MCU 為 F280049CPZS。操作步驟與 LED 極性已在 [course-notes.md](course-notes.md)。這頁補電路圖上查得到的網路名稱。晶片規格見 [device-f280049c.md](device-f280049c.md)。

## 來源

- `TMS320F280049C_開發板電路圖.pdf`：有可搜尋文字，下面的網路名稱來自這份。
- `TMS320F280049C_開發板_LaunchPad接腳說明卡.pdf`：3 頁。前兩頁沒有文字層（海報圖），第 3 頁只有 TI 法律聲明。沒有從這份抽出接腳表。BoosterPack 第幾腳對哪個 GPIO，以使用說明 SPRUII7B 的接頭圖與這份電路圖為準，不要把接腳卡當文字資料再讀一次。
- 使用說明裡已經摘要過的事實（XDS110、LED、S2、SCIA）不在這裡重抄整段，只在電路圖能對上時標網路名。

## 除錯與電源

- USB Micro-B 是 **USB101**。隔離器是 U3。使用說明 known issues 寫明料號 **ADUM3160**：VBUS1 接到 USB 5 V 時，內部穩壓會把 VDD1 變成輸出，和外部 3.3 V 衝突。同一份說明另有一節把 U3 寫成 LMR2421 升壓器；電路圖上 U3 的腳位是 USB 隔離器。
- 除錯這顆 F280049C 時，**J101 的跳線要接上**。拿掉 J101 全部跳線、改接 **J102**，板上 XDS110 才改去除錯外部目標。
- J101 上的除錯信號包含 TMS、TCK，以及 `XDS_TXD` / `XDS_RXD`（虛擬 COM）。

## LED 與開機開關

電路圖網路：

- **LED4 紅**接 **GPIO23**（經 U6 開漏驅動，電阻 R38）。
- **LED5 綠**接 **GPIO34**。
- 使用說明寫這兩顆是 **active-low**（GPIO 拉低才亮）。電路圖標了 Red / Green，沒有再寫有效準位，極性沿用使用說明。
- **S2 上下顛倒**：UP = open = 1，DOWN = closed = 0。腳位是 **GPIO32** 與 **GPIO24**。
- 圖上寫的模式：Boot from SCI / Wait、Boot from Flash。完整四種組合見 [course-notes.md](course-notes.md)。

## 時脈與 UART、CAN

- 晶振 **Y2** 接在 **X1 與 X2** 之間。講義的料號是 ECS-200-18-30B-AGN-TR，20 MHz。量測點是 C39 下方對 GND。
- 預設虛擬 COM 的 SCIA 網路是 **GPIO28_SCIRX**、**GPIO29_SCITX**。S6 = 0 且 S8 = 0 走虛擬 COM；S6 = 1 才改到 BoosterPack（`GPIO28_BP`、`GPIO29_BP`）。另一組 GPIO35 / GPIO37 要 S3.1 = 1、S4 = 1、S8 = 1 才進虛擬 COM。
- CAN 網路是 **GPIO32_CANTX**、**GPIO33_CANRX**，接到 J14 的收發器。只有 **S9** 決定這兩腳去 CAN 還是 BoosterPack（`GPIO32_BP`、`GPIO33_BP`）：S9 = 0 去 J14，S9 = 1（預設）去 BoosterPack。S8 不管 CAN，它管的是 SCIA。要用 CAN 時電路圖註明 **R46 要是 0 Ω**，因為 GPIO33 也接到 FSI。

C2000Ware 預設 SCI 腳位與電路圖一致：`device.h` 的 `DEVICE_GPIO_CFG_SCIRXDA` 是 `GPIO_28_SCIA_RX`，`DEVICE_GPIO_CFG_SCITXDA` 是 `GPIO_29_SCIA_TX`。

## 電路圖上還能對上的 BoosterPack 網路

抽取時表格被打散，只記錄文字清楚的網路，不編造接頭編號：

| 網路 | 圖上旁邊的功能字 |
| --- | --- |
| GPIO0 | PWM/GPIO |
| GPIO3 | Timer_Cap/GPIO |
| GPIO6 | PWM/GPIO |
| GPIO12、GPIO14、GPIO18、GPIO23、GPIO24、GPIO26、GPIO32、GPIO34、GPIO37 | GPIO 或與 I2C、SPI、ADC 標在同一區 |

ADC 標籤有 ADCINA0、ADCINA3、ADCINA4、ADCINA6、ADCINA9、ADCINC1。完整接頭編號以 SPRUII7B Figure 3（BoosterPack pinout）與電路圖原圖為準。

## 報告簡報範例

`附件_簡報範例.pptx` 不是技術手冊，是 2026-09-29 那次 OSC／GPIO 報告的版型。要點：

- 檔名：`日期_主題_組別_報告人姓名`，例如 `20250923_OSC及GPIO_第一組_XXX`。
- 中文標楷體，英文 Times New Roman，最小 16 pt，每頁右下角寫製作者。
- 目錄建議：程式碼說明、振盪器波形量測、通用型輸出輸入波形量測。
- 量測點仍是 C39 下方與 GND。GPIO 實驗是 GPIO0 輸入、GPIO6 輸出；簡報與 GPIO 講義第 35 頁都是輸入高時輸出低。`course-notes.md` 沒有「例 2」這個標題。封裝腳號見該頁，不要用講義圖上的 Pin 80／78。
- 範例投影片把 `InitSysCtrl` 的路徑寫成 `GPIO_EX1/Init.c/Init_GPIO`。那是錯的。`InitSysCtrl` 在 `f28004x_sysctrl.c`，`Init_GPIO` 才在 `Init.c`。
