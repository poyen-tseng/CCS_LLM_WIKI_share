# 課程資料裡的操作摘要

來源資料夾：`G:\我的雲端硬碟\@研究所\數位控制設計-楊`。這裡只留操作時用得到的句子，不是講義全文。投影片裡很多數字畫在圖上，轉文字時會掉字；腳位與開機模式以開發板使用說明為準，並在各節標出來源檔名。

已讀範圍見 [cloud-read-log.md](cloud-read-log.md)。晶片數量、記憶體與 TRM 章節在 [device-f280049c.md](device-f280049c.md)，電路網路在 [board-pins.md](board-pins.md)。回到 [README.md](README.md)。

## 這門課要準備什麼

來源：`0_Introduction to design of digital control_lecture.pdf`。

- 板子型號 **LAUNCHXL-F280049C**。軟體是 Code Composer Studio，從 TI 官網下載。
- 參考文件：C2000 Piccolo F28004x LaunchPad Development Kit user guide、TMS320F28004x Technical Reference Manual、TMS320F28004x Microcontrollers data manual。雲端資料夾裡對應的是 `TMS320F280049C_開發板使用說明.pdf`（SPRUII7B，已摘要）、`TMS320F280049C_精簡版.pdf`（datasheet SPRS945E）與 `TMS320F280049C_詳細版.pdf`（TRM SPRUI33D，不是 datasheet）。後兩份的開發規格在 [device-f280049c.md](device-f280049c.md)，沒有把全文貼進來。
- 之後實驗還會用到示波器、DIP 開關、可變電阻、SPI 的 MCP4161-503E/P、I2C 的 MCP4561-502E/MS、SCI 的 PL2303GC（TTL 轉 USB）。目前 `GPIO_EX1` 還沒用到這些零件。
- 課表上 9/22 是 CCS 介面與 GPIO。TI 網站路徑：Design & Development → C2000 real-time microcontrollers → 硬體開發工具。

## CCS 安裝與這個專案怎麼編譯

來源：`1_CCS software installation and sample project_lecture.pdf`。

講義寫的是 **CCS 12.4**。這台電腦已經是 **CCS 21.0.1**（`C:\ti\ccs2101`），介面是 Theia。沿用這版，不要為了講義降回 12.4。C2000Ware 路徑是 `C:\ti\C2000Ware_5_00_00_00`（使用說明舊版預設寫 `C:\ti\c2000\C2000Ware_<version>`，這台不在那個路徑）。目錄名稱是 5.0，裡面的 manifest 檔名是 26.01，說明見 [references.md](references.md)。

講義要匯入的範例就是 **GPIO_EX1**。Include 要有這兩個目錄（路徑依實際安裝，本機就是下面兩行）：

- `C:\ti\C2000Ware_5_00_00_00\device_support\f28004x\common\include`
- `C:\ti\C2000Ware_5_00_00_00\device_support\f28004x\headers\include`

GUI 操作，CCS 12 與 21 選單名稱可能不同，步驟仍是：

1. Import CCS project，選 GPIO_EX1。
2. 專案右鍵 Properties → Build → Include Options，加入上面兩個目錄。
3. Clean Project，再 Build。講義的成功標準是編譯完成且沒有 error。
4. 除錯：Target Configuration → Launch → Connect Target → Load，選專案的 `.out`。
5. 中斷點用雙擊行號，或 View → Breakpoints。執行用 Resume、step into、step over、step return、terminate。Ctrl 加在符號上可跳到函式。
6. 暫存器寫法是 `.bit`（單欄）與 `.all`（整筆）。Watch 視窗可連續更新，數值格式在運算式上按右鍵改。

CCS 已開著時，同等動作用 [mcp.md](mcp.md)，不必重走 GUI。

## LaunchPad 硬體（除錯與腳位）

來源：`1_LAUNCHXL-F280049C_lecture.pdf` 與 `TMS320F280049C_開發板使用說明.pdf`（SPRUII7B）。講義圖上的腳號多半沒被抽出來，下面腳號來自使用說明。

- 晶片封裝 **F280049CPZS**（100 pin）。板上除錯器是 **XDS110**，只接 2-pin cJTAG（TMS、TCK）。Target Configuration 要用 2-pin cJTAG。TDI/TDO 預設不進除錯器，對應 GPIO35、GPIO37。
- USB Micro-B 接 **USB101**。LED0 是 USB 側 3.3 V，LED1 是裝置側 3.3 V（目標與 XDS110 都有電）。LED2、LED3 是藍色，只表示除錯器活動，程式控不了。
- 使用者 LED：LED4 紅 = **GPIO23**，LED5 綠 = **GPIO34**，經 SN74LVC2G07，**active-low**（輸出低才亮）。
- 開機開關 **S2 上下顛倒**：OFF（開路）= 1，ON（閉合）= 0。GPIO32 是 Position 1，GPIO24 是 Position 2。

| 模式 | GPIO32 (S2 位置 1) | GPIO24 (S2 位置 2) |
| --- | --- | --- |
| Boot from Parallel GPIO | ON (0) | ON (0) |
| Boot from SCI / Wait | OFF (1) | ON (0) |
| Boot from CAN | ON (0) | OFF (1) |
| Boot from Flash（預設） | OFF (1) | OFF (1) |

- 虛擬序列埠：XDS110 同時是除錯器與 Virtual COM。預設 **SCIA = GPIO28 / GPIO29** 接到這個 COM，不在 BoosterPack 上。改走 GPIO35 / GPIO37 要動 S3、S4、S8。使用說明 FAQ 寫：CPU 在 100 MHz 時，多數範例鮑率是 **115200**。改了 PLL 或自寫 SCI 時要重算。
- CAN 在 J14，GPIO32 / GPIO33 經 SN65HVD234。S9 決定這兩腳去 CAN 收發器還是 BoosterPack。GPIO33 還經 R46 接到 FSI；要用 CAN 時 R46 要在。
- 用板上 XDS110 去除錯別的板：接 J102，並拿掉 J101 上所有跳線，避免 JTAG 仍打到這顆 F280049C。
- 隔離跳線 JP1、JP2、JP3 出廠是不隔離（USB 與 MCU 共地）。要隔離再依使用說明拔跳線。

下載步驟（使用說明）：USB 接上 → LED0 與 LED1 亮 → 必要時裝 XDS110 與 VCP 驅動 → 開 CCS → Launch 專案裡的 Target Configuration（2-pin cJTAG）→ Load Program。

## 時脈

來源：`1_OSC_lecture.pdf`。專案實際呼叫來自 `f28004x_sysctrl.c`。

- 內部 INTOSC1、INTOSC2 講義標 10 MHz。板上晶振 **ECS-200-18-30B-AGN-TR，20 MHz**，接在 X1/X2。量測點是 X1（C39 下側對 GND）。
- 改時脈暫存器前要 `EALLOW`，設完 `EDIS`。
- `main()` 呼叫 `InitSysCtrl()`（`f28004x_sysctrl.c`）。該函式目前是：

```c
InitSysPll(XTAL_OSC, IMULT_10, FMULT_0, PLLCLK_BY_2);
```

- 講義的公式：`NF = IMULT + FMULT/4`，`PLLRAWCLK = OSCCLK * NF / ODIV`，再由 `PLLSYSCLKDIV` 得到 SYSCLK。`clock_source` 三選一：`INT_OSC2`、`XTAL_OSC`、`INT_OSC1`。除頻可從 /1 到 /126。Ctrl 加在 `InitSysPll` 上可跳進選項。
- 週邊時脈閘在 `PCLKCRx`，寫 0 是關掉。低速週邊（SCI、SPI）走 `LOSPCP` / `LSPCLK`。

## GPIO

來源：`2_GPIO_lecture.pdf`。暫存器細節以 TRM 為準；下面是講義有寫清楚的部分。

- `GPyDIR`：0 輸入，1 輸出。`GPADIR` 管 GPIO0–31，`GPBDIR` 管 GPIO32–63。
- 周邊功能由 `GPyGMUX`（高 2 bit）與 `GPyMUX`（低 2 bit）合成。講義以 GPIO6 為例：`00:00` GPIO、`00:01` EPWM4A、`00:10` OUTPUTXBAR4、`00:11` EXTSYNCOUT。`GPAGMUX1`/`GPAMUX1` 管 GPIO0–15，`GPAGMUX2`/`GPAMUX2` 管 GPIO16–31；B 組從 GPIO32 起。
- `GPyCSEL`：0 是 CPU，1 是 CLA。`GPACSEL1` 管 GPIO0–7，之後每 8 支腳一顆，到 `GPBCSEL4` 的 GPIO56–63。
- 輸出用 `GPySET` / `GPyCLEAR` / `GPyTOGGLE`。不要靠寫 `GPyDAT` 當一般輸出。`GPyDAT` 讀的是取樣後的腳位準位。
- `GPyPUD`：0 啟用內部上拉，1 關閉。`GPyINV`：1 表示輸入反相。
- 輸入濾波：`GPyQSEL` 的 0 同步、1 三次取樣、2 六次取樣、3 非同步。取樣間隔在 `GPyCTRL` 的 `QUALPRD`。
- `GPyODR`：0 push-pull，1 open-drain。
- 講義實驗：GPIO0 當輸出量高電位與上升時間；GPIO0 當輸入，經 qualification 改變 GPIO6。輸入高時輸出低，見 `2_GPIO_lecture.pdf` 第 35 頁。程式位置是 `main.c` 的 `main` 與 `Init.c` 的 `Init_GPIO`。
- 封裝腳號以精簡版 Table 4-1 的 100-pin PZ 欄為準：**GPIO0 是 pin 79，GPIO1 是 pin 78，GPIO6 是 pin 97**。講義第 30 頁圖上有 Pin 78 與 Pin 80，文字層沒把這兩個號碼對到 GPIO，不要拿 80／78 去量 GPIO0／GPIO6。

## 寫在別頁、沒有重抄進這裡的檔

精簡版與詳細版的數量、記憶體、TRM 章節在 [device-f280049c.md](device-f280049c.md)。電路圖網路、接腳卡（3 頁、接腳是圖、沒有文字層）與簡報版型在 [board-pins.md](board-pins.md)。`20250915上課教材.rar` 與工作區重複，沒有解壓。CCS 安裝 zip 只登記、本機已安裝。`分組名單.pdf` 沒有打開。`GPIO_EX1\` 與工作區是同一專案，改 [D:\code\_TI_CCS_no_chinese\GPIO_EX1](D:\code\_TI_CCS_no_chinese\GPIO_EX1) 那一份。
