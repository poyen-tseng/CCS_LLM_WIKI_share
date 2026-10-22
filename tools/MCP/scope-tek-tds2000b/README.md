# scope-tek-tds2000b

經 USB 控制 Tektronix TDS2014B（4 通道、100 MHz、每筆 2500 點；TDS2000B 系列）。接後面板 USB 裝置埠，走 USBTMC，用 pyvisa-py + libusb（WinUSB 驅動），不需要 NI-VISA 或 TekVISA。`config.json` 的 `"resource": "auto"` 依 VID 0x0699／PID 0x0368 自動找示波器；要固定位址時寫在 `config.local.json`（git 忽略）或環境變數 `TEK_RESOURCE`。

MCP 伺服器名稱是 `tek`，工具都以 `tek_` 開頭：

| 工具 | 做什麼 |
| --- | --- |
| `tek_idn`、`tek_status` | 識別碼；通道（含單位 V／A 與探棒比）、時基、擷取、觸發設定與 `run_state` |
| `tek_set_channel`、`tek_set_timebase`、`tek_set_trigger` | 調整設定。通道位置以格為單位，也可給 `offset_v_center`；觸發有 EDGE 與 PULSE（脈寬） |
| `tek_run_control`、`tek_autoscale` | run／stop／single／force；`run_state` 用 RIGOL 的字：TD、WAIT、AUTO、STOP |
| `tek_measure` | 自動量測。RIGOL 名稱（`VPP`、`RTIM`、`PDUT`…）與 Tek 原名都可；韌體沒有的工作週期由脈寬 ÷ 週期算出 |
| `tek_capture`、`tek_screenshot` | 2500 點波形 CSV、白底 PNG，存在 captures |
| `tek_scpi` | 原始 SCPI。會擋下重置、存取設定、校正、鎖面板、列印與檔案系統指令 |

這台沒有函數產生器。自我測試時，四支探棒都接前面板 PROBE COMP（約 5 V、1 kHz 方波）。

SCPI 差異、可用的量測項目、觸發狀態判斷、速度與 2026-10-22 的實測結果都寫在 [tek-scope.md](../../../docs/wiki/tek-scope.md)。

## USB 驅動（第一次接線）

Windows 沒有內建 USBTMC 驅動，沒裝之前裝置管理員會顯示「Tektronix TDS2014B」錯誤碼 28。

1. 以系統管理員執行 [Zadig](https://zadig.akeo.ie)。
2. Options → List All Devices，選「Tektronix TDS2014B」（USB ID `0699 0368`）。
3. 目標驅動選 **WinUSB**，按 Install Driver。
4. 執行 `.venv\Scripts\python.exe -I tek.py list`，應列出 `USB0::1689::872::<序號>::0::INSTR`。

還原：裝置管理員 → 解除安裝這個裝置，並勾選刪除驅動程式。

## 不用 MCP 時

`tek.py` 的 CLI：`list`、`idn`、`status`、`shot [out.png] [black]`、`wave <ch>`、`meas <item> <ch>`、`recover`、`q "<查詢>"`、`w "<指令>"`。

## 安裝

需要 Python 3.11。`requirements.txt` 是 Keysight 那份再加 `pyusb`、`libusb-package`（內含 libusb-1.0.dll）與 `pillow`（BMP 轉 PNG）。

`deploy.ps1` 在這個目錄建立 `.venv` 並安裝依賴。在本目錄第一次註冊：

```powershell
.\deploy.ps1
claude mcp add tek --scope user -- "$PWD\.venv\Scripts\python.exe" "$PWD\tek_mcp.py"
```

修改程式後重新連上 `tek`（`/mcp`）；只有依賴改變時才需再跑 `deploy.ps1`。

`.venv/`、`captures/`、`__pycache__/` 與 `config.local.json` 不進 git。截圖與 `tek_status` 的輸出含示波器序號，不要貼進公開文件。
