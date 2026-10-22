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

### GPIO0／GPIO1／GPIO6 的接頭位置（2026-10-12 查證）

上表刻意不寫接頭編號，因為電路圖抽取時表格被打散。這三腳後來有兩張圖和一次實測可對照，編號卻互相衝突：

| 信號 | 封裝腳（PZ，精簡版 Table 4-1） | 講義 pin map（舊版 Figure 3） | SPRUII7B Rev B Figure 3 |
| --- | --- | --- | --- |
| GPIO0 | 79 | J8、80 | 60 |
| GPIO1 | 78 | J8、79 | 59 |
| GPIO6 | 97 | J8、78 | 58 |
| 同排另一腳 | | J6、60 = GND | 80 = GND |

- 兩版圖指的是 BoosterPack site 2（MCU 下方）右側接頭上的**同一個實體位置**，只有欄名與號碼不同。使用說明第 1.7.1 節（known issues）寫：PCB 絲印、電路圖與 Quick Start 卡把 J6／J8 與 51–60／71–80 標反。
- 2026-10-07 依講義標的 J8 80／78 接探棒，量到 GPIO0 與 GPIO6，GPIO6 反相行為正確（`projects/Oscilloscope_read/STATUS.md`）。
- 照位置接，不要只照數字：照 Rev B 的「80」去接會碰到 GND。拿不準時，GPIO0 那排的另一腳應是 GND。

### GPIO2 與 J8 整欄（2026-10-22 查電路圖並實測）

雲端 `TMS320F280049C_開發板電路圖.pdf` 第 2 頁 BoosterPack Site 2 的 J8 畫成 40–31 腳，圖上註明 J5–J8 的腳號要加 40。換算後，與講義 pin map 的 80／79／78 一致：

| J8（講義編號） | 信號 | 同一列 J6 的腳 |
| --- | --- | --- |
| 80 | GPIO0 | GND |
| 79 | GPIO1 | GPIO27 |
| 78 | GPIO6_BP | 未接 |
| 77 | GPIO7_BP | 未接 |
| 76 | **GPIO2_BP**（封裝腳 77，經 R71 0 Ω） | **XRSn（RST）** |
| 75 | GPIO3 | GPIO24 |

- GPIO2 的對面是 RST，勾針或地夾碰到它，晶片會重設。
- 2026-10-22 Timer_HW 實測：J8 79 是 100 Hz 方波（GPIO1），J8 76 是 200 Hz、約 210 ns 的 ISR 脈波（GPIO2），J8 80 是 1 kHz 脈波（GPIO0）。三個訊號不同，位置確認正確（`projects/Timer_HW/STATUS.md`）。
- 按同樣的位置對應，Rev B Figure 3 裡 GPIO2 應該編為 56；這是推算，沒有查 Rev B 原圖。

## 報告簡報範例

`附件_簡報範例.pptx` 不是技術手冊，是 2026-09-29 那次 OSC／GPIO 報告的版型。要點：

- 檔名：`日期_主題_組別_報告人姓名`，例如 `20250923_OSC及GPIO_第一組_XXX`。
- 中文標楷體，英文 Times New Roman，最小 16 pt，每頁右下角寫製作者。
- 目錄建議：程式碼說明、振盪器波形量測、通用型輸出輸入波形量測。
- 量測點仍是 C39 下方與 GND。GPIO 實驗是 GPIO0 輸入、GPIO6 輸出；簡報與 GPIO 講義第 35 頁都是輸入高時輸出低。`course-notes.md` 沒有「例 2」這個標題。封裝腳號見該頁。講義圖上的 Pin 80／78 是 BoosterPack 接頭編號，不是封裝腳號，見「GPIO0／GPIO1／GPIO6 的接頭位置」的對照表。
- 範例投影片把 `InitSysCtrl` 的路徑寫成 `GPIO_EX1/Init.c/Init_GPIO`。那是錯的。`InitSysCtrl` 在 `f28004x_sysctrl.c`，`Init_GPIO` 才在 `Init.c`。

## 量測簡報必備：設備與設定頁

有放波形或量測值的簡報，必須有一頁「量測設備與設定」。目的是讓沒參與實驗的人看得出用了什麼裝置、怎麼量，並能重做。2026-10-15 使用者要求加上這條規則。

規則：

- 表格集中放在一頁（或連續兩頁），放在第一張波形頁之前。設定散在各頁的圖說不能取代這一頁。
- 每一格都寫**這次實際量測時的值**，不寫 TASK 的預定值。數值的來源優先順序：量測當下的 `scope_status`／`ks_status` 回傳、`scope_scpi`／`ks_scpi` 查詢、同次截圖上的狀態列、STATUS 紀錄。
- JEV 結果 JSON 裡 `frame.*.suggestion` 的 `vdiv`／`offset`／`trigger_level` 是 Jev 的**建議值**，不是示波器的實際設定，不能抄進設定表。2026-10-13 `timer_optimized_v2_20261013/0.json` 的建議是 0.5 V/div、offset −1.439 V，同次截圖實際是 1.00 V/div、−1.65 V。
- 量測前先存一份 `scope_status`／`ks_status` 的輸出，和截圖放在同一個結果目錄，事後才查得到。
- 查不到的格子寫「未記錄」，不能留空，也不能用型錄值或推測值填。要估計時寫「約」並在備忘稿寫依據。
- 同一份簡報用了不同設定（例如兩種時基、兩組 qualification）時，每組各一欄，或在對應波形頁標明差異。
- 每張波形截圖的圖說至少寫：通道對應的信號、V/div、s/div、觸發條件。
- 這一頁也算進簡報 QA：輸出 PNG 檢查時要確認表格沒有空格、數值和結果 JSON 一致。

表格欄位：

| 類別 | 必寫項目 | 資料來源 |
| --- | --- | --- |
| 被測物 | 開發板與晶片型號、供電方式（USB／外部）、SYSCLK、程式在 RAM 或 Flash | TASK、STATUS |
| 軟體 | CCS 版本、編譯器版本、專案名稱 | `ccs_env`、建置紀錄 |
| 被測信號規格 | 信號名稱與接點（GPIO、接頭與腳位編號）、邏輯準位（3.3 V）、預期頻率／週期／脈寬／電壓、引用的規格（如 rise ≤ 8 ns） | TASK、講義、資料手冊 |
| 外部信號源（有用才寫） | 儀器型號、波形、振幅與偏移（如 0–2.5 V）、頻率或脈寬、輸出阻抗設定、接到哪一腳 | 量測紀錄 |
| 示波器 | 廠牌型號、類比頻寬、IDN 韌體版本 | `*IDN?`、wiki 儀器頁 |
| 通道 | 每個用到的通道對應的信號、探棒倍率、耦合（DC／AC）、輸入阻抗、頻寬限制開關、V/div、offset（RIGOL 與 Keysight 符號相反，寫實際數值並註明廠牌） | `scope_status`／`ks_status`；RIGOL 的阻抗用 `:CHANn:IMP?` |
| 探棒 | 型號、頻寬、接地方式（長地夾／短接地彈簧）、地夾接在哪個 GND | 現場紀錄；不知道就寫「未記錄」 |
| 水平與擷取 | s/div、水平位置、取樣率、記憶深度（點數）、擷取模式（Normal／Average／High-Res） | `scope_status`／`ks_status`；RIGOL 擷取模式用 `:ACQ:TYPE?` |
| 觸發 | 類型、來源、斜率、準位、sweep（AUTO／NORM／SINGLE）、單次擷取或連續 | `scope_status`／`ks_status` |
| 量測方法 | 量測項目、參考準位（脈寬／週期 50 %、上升時間 10–90 %）、取幾次或是否同一次凍結擷取、合格標準 | TASK、結果 JSON |
| 限制 | 儀器與探棒頻寬對快邊緣的影響、接地方式對準位的影響、本次未驗證的項目 | STATUS |

示波器頻寬對上升時間的影響要寫明：100 MHz 的 RIGOL MSO5104 本身上升時間約 0.35／100 MHz ≈ 3.5 ns，量 ns 級邊緣時會偏大（GPIO 實驗量到 11.8 ns 就有這個成分）。

RIGOL 截圖的狀態列可以事後讀出一部分設定：上方 H 欄是時基、取樣率與記憶深度，T 欄是觸發斜率、來源、準位與 sweep（N = NORM），下方通道框是 V/div 與 offset。擷取模式、頻寬限制、輸入阻抗與探棒接地方式從截圖看不出來，要在量測當下查詢或記錄。

本規則補在 2026-10-13 Timer 簡報之後。那份簡報第 6 頁已有通道、時基與觸發設定（與截圖 `timer_optimized_v2_20261013/0.png` 相符：100 ms/div、1.00 V/div、−1.65 V、上升緣 1.65 V、NORM），但沒有取樣率、記憶深度、探棒接地方式、擷取模式、頻寬限制、輸入阻抗與量測參考準位。重做該簡報時，取樣率 25 MSa/s 與記憶深度 25 Mpts 可從同一張截圖讀出；其餘項目當天沒有記錄，應寫「未記錄」，不可補填。
