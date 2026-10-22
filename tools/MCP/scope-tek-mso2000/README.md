# scope-tek-mso2000

經 USB 控制 Tektronix MSO2014（MSO／DPO2000 系列：4 類比通道、100 MHz、每筆 125 k 或 1 M 點；16 個數位通道尚未支援）。接後面板 USB 裝置埠，走 USBTMC，用 pyvisa-py + libusb（WinUSB 驅動），不需要 NI-VISA 或 TekVISA。`config.json` 的 `"resource": "auto"` 依 VID 0x0699／PID 0x0377 自動找示波器；要固定位址時寫在 `config.local.json`（git 忽略）或環境變數 `MSO_RESOURCE`。

MCP 伺服器名稱是 `mso`，工具都以 `mso_` 開頭：

| 工具 | 做什麼 |
| --- | --- |
| `mso_idn`、`mso_status` | 識別碼；通道（含探棒比、單位、頻寬）、時基（含紀錄長度、取樣率）、擷取、觸發設定與 `run_state` |
| `mso_set_channel`、`mso_set_timebase`、`mso_set_trigger` | 調整設定。`offset_v_center` 用真正的電壓偏移；觸發有 EDGE 與 PULSE（脈寬） |
| `mso_run_control`、`mso_autoscale` | run／stop／single／force；`run_state` 用 RIGOL 的字：TD、WAIT、AUTO、STOP |
| `mso_measure` | 自動量測。RIGOL 名稱（`VPP`、`VTOP`、`PDUT`、`DEL`、`PHAS`…）與 Tek 原名都可；每項約 60–100 ms |
| `mso_capture` | 波形 CSV。`SCREEN` 約 5000 點，`FULL` 整筆 125 k／1 M 點 |
| `mso_screenshot` | 白底（或黑底）PNG，只用 USB 線（`HARDC START`，約 1.7 s），存在 captures |
| `mso_scpi` | 原始 SCPI。會擋下重置、存取設定、校正、鎖面板、列印、檔案系統與 USB／網路設定指令，也擋 AUTOSET（請用 `mso_autoscale`） |

這台沒有函數產生器。自我測試時，四支探棒都接前面板 PROBE COMP（約 5 V、1 kHz 方波）。探棒沒有 ID 腳，示波器偵測不到衰減比；用 `mso_set_channel(probe_ratio=10)` 設定，並看 `mso_status`。

SCPI 差異、可用的量測項目、觸發狀態判斷、速度與 2026-10-22 的實測結果都寫在 [mso2000-scope.md](../../../docs/wiki/mso2000-scope.md)。

## USB 驅動（第一次接線）

Windows 沒有內建 USBTMC 驅動，沒裝之前裝置管理員會顯示「MSO2014」錯誤。

1. 以系統管理員執行 [Zadig](https://zadig.akeo.ie)。
2. Options → List All Devices，選「MSO2014」（USB ID `0699 0377`）。
3. 目標驅動選 **WinUSB**，按 Install Driver。
4. 執行 `.venv\Scripts\python.exe -I mso.py list`，應列出 `USB0::1689::887::<序號>::0::INSTR`。

還原：裝置管理員 → 解除安裝這個裝置，並勾選刪除驅動程式。

## USB 卡住時

AUTOSET 執行時示波器不回應 USB。若這時有短逾時的查詢逾時中斷，USB 連線會卡住：之後每個指令都逾時，USBTMC clear 和 USB reset 都救不回來，只能拔插 USB 線（2026-10-22 實測）。所以 AUTOSET 只用 `mso_autoscale`（一次長逾時的 `*OPC?`），不要經 `mso_scpi` 送。

## 不用 MCP 時

`mso.py` 的 CLI：`list`、`idn`、`status`、`shot [out.png] [black]`、`wave <ch> [screen|full] [點數]`、`meas <item> <ch> [ch2]`、`recover`、`q "<查詢>"`、`w "<指令>"`。

## 安裝

需要 Python 3.11。`requirements.txt` 和 `scope-tek-tds2000b` 相同（Keysight 那份再加 `pyusb`、`libusb-package`、`pillow`）。

`deploy.ps1` 在這個目錄建立 `.venv` 並安裝依賴。在本目錄第一次註冊：

```powershell
.\deploy.ps1
claude mcp add mso --scope user -- "$PWD\.venv\Scripts\python.exe" "$PWD\mso_mcp.py"
```

修改程式後重新連上 `mso`（`/mcp`）；只有依賴改變時才需再跑 `deploy.ps1`。

`.venv/`、`captures/`、`__pycache__/` 與 `config.local.json` 不進 git。`mso_status`／`mso_idn` 的輸出含示波器序號，不要貼進公開文件。
