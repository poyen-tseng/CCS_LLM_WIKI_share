# F280049C 外部文件與 skill

2026-09-22 上網查過，並對過本機 `C:\ti\C2000Ware_5_00_00_00`。只記網址與本機路徑，沒有下載或另裝套件。回到 [README.md](README.md)。晶片數量與 TRM 章節見 [device-f280049c.md](device-f280049c.md)，板子見 [board-pins.md](board-pins.md)。

## 先用哪一份

目前實驗是振盪器與 GPIO，專案 `GPIO_EX1` 走 **bitfield**（`device_support\f28004x`）。新寫的周邊先繼續用這套標頭，與講義一致。

TI 新範例改走 **driverlib**（`driverlib\f28004x`）。同一個專案不要同時加兩套標頭：bitfield 的 `f28004x_lin.h` 與 driverlib 的 `cpu.h` 都定義了 `IDLE`，會編譯失敗。

| 要做的事 | 先看 |
| --- | --- |
| 這顆的腳位、電氣、記憶體 | 雲端精簡版 SPRS945E。官網較新版見下表 |
| 暫存器位元 | 雲端詳細版 SPRUI33D 的章名。頁碼以該版為準 |
| LaunchPad 開關、LED、UART、CAN | 雲端使用說明 SPRUII7B，摘要在 [board-pins.md](board-pins.md) |
| 編譯、下載、看變數 | [mcp.md](mcp.md)、[cli-and-scripting.md](cli-and-scripting.md) |
| 矽片與手冊不符的行為 | 勘誤 SPRZ439。雲端沒有這份 |
| 閉迴路 PID／補償器 | 本機 DCL，見下方路徑 |
| PWM 細節 | ePWM Developer’s Guide。GPIO 階段先不要展開 |

## 本機已經有的

安裝目錄名稱是 `C:\ti\C2000Ware_5_00_00_00`。講義寫的版次是 5.0，路徑用這個。目錄裡另有 `C2000Ware_26.01.00.00_manifest.html`，檔內日期寫 2026-12-05（晚於查閱日）。先沿用這個目錄，不要再裝第二份 C2000Ware。

| 內容 | 路徑 |
| --- | --- |
| Bitfield 標頭與 GPIO 一類範例 | `device_support\f28004x`。說明 HTML 在 `device_support\f28004x\docs\html` |
| Driverlib 範例 | `driverlib\f28004x\examples` |
| C2000 Academy 實驗解答 | `training\device\f28004x` |
| Digital Control Library（DCL） | `libraries\control\DCL\c28`。手冊在 `docs\DCL User's Guide.pdf`，另有 PID 調整指南 |
| 這塊 LaunchPad 的硬體檔 | `boards\LaunchPads\LAUNCHXL-F280049C`（連字號）。官網有時寫成底線 `LAUNCHXL_F280049C`，本機資料夾是連字號 |
| 套件總說明 | `docs\c2000Ware_documentation.html` |

`device.h` 的時脈註解與 SCI 預設腳仍以這個目錄為準，見 [device-f280049c.md](device-f280049c.md)。

## 官網文件

產品頁：[TMS320F280049C](https://www.ti.com/product/TMS320F280049C)。板子頁：[LAUNCHXL-F280049C](https://www.ti.com/tool/LAUNCHXL-F280049C)。

雲端已有、官網較新的：

| 文件 | 雲端 | 2026-09-22 官網所列 |
| --- | --- | --- |
| Datasheet SPRS945 | Rev. E，2017-01 至 2020-04 | Rev. H，2026-03-10。[PDF](https://www.ti.com/lit/ds/symlink/tms320f280049c.pdf) |
| TRM SPRUI33 | Rev. D，2015-11 至 2020-09，2745 頁 | Rev. H，2024-06-12。[PDF](https://www.ti.com/lit/ug/sprui33h/sprui33h.pdf) |
| LaunchPad 使用說明 SPRUII7 | Rev. B | 仍是 Rev. B。[PDF](https://www.ti.com/lit/ug/spruii7b/spruii7b.pdf) |

雲端沒有、開發時會用到的：

| 文件 | 備註 |
| --- | --- |
| 矽勘誤 SPRZ439 | 產品頁列 Rev. I（2026-08-19）。另有 [Rev. H](https://www.ti.com/lit/er/sprz439h/sprz439h.pdf)（修訂至 2024-02），涵蓋 revision 0／A／B。含巢狀中斷、Flash、SDFM 等已知行為。寫中斷或燒 Flash 前先查這份 |
| Getting Started With C2000 Real-Time Control Microcontrollers（Rev. C，2022-06-29） | 從板子、文件到軟體的總入口，連結在產品頁 |
| The Essential Guide for Developing With C2000（Rev. F，2022-03-03） | 產品頁上的應用筆記 |
| [C2000 Software Guide](https://software-dl.ti.com/C2000/docs/software_guide/index.html) | Driverlib、bitfield、函式庫怎麼選 |
| C2000 ePWM Developer’s Guide（Rev. A，2023-02-24） | PWM 實驗再用 |
| [DCL 獨立手冊 SPRUID3](https://www.ti.com/lit/ug/spruid3/spruid3.pdf) | 較舊的單行本。函式與範例以本機 `libraries\control\DCL` 為準。F28004x 用 FPU32 與 CLA 那組，固定小數點那組不是這顆的主路徑 |
| C28x 編譯器 SPRU514、組譯器 SPRU513、CPU 指令集 SPRU430 | 網路上容易搜到 2018 年的 SPRU514P。這台編譯器是 `ti-cgt-c2000_25.11.1.LTS`，以 CCS 安裝目錄裡那一版的文件為準 |

[C2000 Academy](https://dev.ti.com/tirex/explore/node?node=A__AIKo.r4gG7gT20B.wy-wFw__C28X-ACADEMY__1sbHxUB__LATEST) 有 F28004x 的 CCS、SysConfig、GPIO／ePWM／ADC 實驗。原始碼倉庫是 [c2000ware-c2000-academy](https://github.com/TexasInstruments/c2000ware-c2000-academy)，本機 `training\device\f28004x` 已有對應內容，不必再 clone。[c2000ware-core-sdk](https://github.com/TexasInstruments/c2000ware-core-sdk) 是上游倉庫，本機樹已在，不必再抓。

論壇：[TI E2E C2000](https://e2e.ti.com/support/microcontrollers/c2000-microcontrollers-group/c2000)。

## 不要和這塊板混用

- SPRUIC4 是 controlCARD `TMDSCNCD280049C`，開機腳同樣是 GPIO24 與 GPIO32，接頭不是 LaunchPad。
- [MotorControl SDK](https://www.ti.com/tool/C2000WARE-MOTORCONTROL-SDK) 與 InstaSPIN-FOC 給馬達用。C 字尾才有 InstaSPIN。目前 `GPIO_EX1` 用不到，先不要裝。
- 產品頁上的電源、LLC、PFC、CLB 應用筆記留給對應實驗。GPIO 階段不要把那些流程寫進專案。

## Skill

沒有現成、對得上 CCS 21 與 F280049C 的 agent skill。

公開最接近的是 [ccs1280-ti-embedded-workflow](https://github.com/logicalmove/ccs1280-ti-embedded-workflow)。它寫給 Codex、CCS 12.8，裝置是 F28034／F28335。不要安裝，也不要把它的路徑套到 `C:\ti\ccs2101`。

本機 Cursor skill 沒有 C2000 專用的。寫這顆時用本 wiki，加上已接上的 MCP：`ccs-project`、`ccs-debug`、`ccs-sysconfig`、`ccs-serial`（見 [mcp.md](mcp.md)）。`GPIO_EX1` 沒有 `.syscfg`，不要為了 Academy 的 SysConfig 實驗去開這個專案的 sysconfig。

若以後要做專用 skill，材料就是本 wiki：bitfield 與 driverlib 分開、LaunchPad 的 S2／S6／S8／S9、時脈 100 MHz、100 MHz 時多數範例鮑率 115200、不要反組譯 CCS。
