# scope-keysight-dsox4000

經區域網路控制 Keysight InfiniiVision DSO-X 4034A（`*IDN?` 顯示 AGILENT）。SCPI 在 TCP 連接埠 5025。`config.json` 的預設位址是 `192.168.137.60`，socket 腳本的 bind 是 `192.168.137.1`。`KS_ADDR` 可覆寫位址，`KS_BIND` 可覆寫 socket 腳本的 bind；MCP 的 PyVISA 連線未使用 bind，依 Windows 路由。

MCP 伺服器名稱是 `keysight`，工具都以 `ks_` 開頭：

| 工具 | 做什麼 |
| --- | --- |
| `ks_idn`、`ks_status` | 識別碼與選配；通道、時基、擷取、觸發、Demo、游標設定與 `run_state` |
| `ks_set_channel`、`ks_set_timebase`、`ks_set_trigger` | 調整設定；觸發有 EDGE 與 GLITCH（脈寬） |
| `ks_run_control`、`ks_autoscale` | run／stop／single／force；`run_state` 用 RIGOL 的字：TD、WAIT、AUTO、STOP |
| `ks_measure` | 自動量測。RIGOL 名稱（`RTIM`、`VBASE`、`PDUT`…）與 Keysight 原名都可；`DEL`、`PHAS` 量兩個通道 |
| `ks_markers` | 游標。`auto="rise_10_90"` 從波形算 10 %／90 % 點放游標 |
| `ks_capture`、`ks_screenshot` | 波形 CSV、白底 PNG，存在 captures |
| `ks_demo` | 前面板 Demo 1／Demo 2 的訓練訊號，當作自我測試訊號源（這台沒有 WaveGen） |
| `ks_scpi` | 原始 SCPI。會擋下重置、存取設定、儲存、`:LAN`、`:WGEN` 等指令；不支援的查詢 2 秒後回報錯誤佇列 |

與 RIGOL 不同的 SCPI、觸發狀態怎麼判斷、為什麼等觸發時不能讀資料、Demo 訊號的實測值，都寫在 [keysight-scope.md](../../../docs/wiki/keysight-scope.md)。用 JEV 閘門置中與診斷見 [jev.md](../../../docs/wiki/jev.md)。

## 網路設定（給人閱讀）

完整面板操作、Windows 網卡、DNS、工具覆寫與驗證見 [示波器網路設定](../../../docs/wiki/scope-network-setup.md)。

| 欄位 | 直連預設 |
| --- | --- |
| 電腦 IP／遮罩 | `192.168.137.1`／`255.255.255.0` |
| 示波器 IP／遮罩／閘道 | `192.168.137.60`／`255.255.255.0`／`192.168.137.1` |
| IP 配置 | 關閉 Automatic，手動指定參數 |
| SCPI TCP 埠 | `5025` |
| DNS | 數字 IP 連線不使用；欄位填法見主文件 |

此表是預設配置，不代表目前已連線。設定工具端 IP 不會更改示波器面板 IP。

## 不用 MCP 時

- `keysight.py` 的 CLI：`idn`、`status`、`shot [out.png] [black]`、`wave <ch> [norm|raw|max] [points]`、`meas <item> <ch> [ch2]`、`demo <function> [on|off]`、`mark <rise_10_90|fall_90_10|swing|off> [ch]`、`recover`、`q`、`w`。
- `tools/ks_lan.py`：只用標準函式庫的 socket 函式，`JEV_accel` 也用它。
- `tools/capture_edge.py`：一次完成邊緣置中、single、10–90 % 游標與兩張白底截圖。預設用 Demo CLK；接 F280049C 時加 `--go-file` 與 `--center 1.65`。

示波器卡住（查詢都逾時）時執行 `keysight.py recover`。

## 安裝

需要 Python 3.11。`requirements.txt` 與 RIGOL 那份相同。

`deploy.ps1` 在這個倉庫目錄建立 `.venv` 並安裝依賴，不再複製程式到使用者目錄。Cursor 與 Claude Code 的 `keysight` 直接執行這裡的 `ks_mcp.py`。在本目錄第一次註冊：

```powershell
.\deploy.ps1
claude mcp add keysight --scope user -e KS_ADDR=192.168.137.60 -- "$PWD\.venv\Scripts\python.exe" "$PWD\ks_mcp.py"
```

修改程式後重新連上 `keysight`（`/mcp`）；只有依賴改變時才需再跑 `deploy.ps1`。使用者目錄下的舊部署副本暫時保留，但不再註冊。

`.venv/`、`captures/` 與 `__pycache__/` 不進 git。
