# scope-keysight-dsox4000

經區域網路控制 Keysight InfiniiVision DSO-X 4034A（`*IDN?` 顯示 AGILENT）。SCPI 在 TCP 連接埠 5025。預設位址在 `config.json`，目前是 `192.168.137.60`，bind `192.168.137.1`。環境變數 `KS_ADDR`、`KS_BIND` 可以覆寫。

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

與 RIGOL 不同的 SCPI、觸發狀態怎麼判斷、為什麼等觸發時不能讀資料、Demo 訊號的實測值，都寫在 [keysight-scope.md](../../LLM_WIKI/keysight-scope.md)。用 JEV 閘門置中與診斷見 [jev.md](../../LLM_WIKI/jev.md)。

## 不用 MCP 時

- `keysight.py` 的 CLI：`idn`、`status`、`shot [out.png] [black]`、`wave <ch> [norm|raw|max] [points]`、`meas <item> <ch> [ch2]`、`demo <function> [on|off]`、`mark <rise_10_90|fall_90_10|swing|off> [ch]`、`recover`、`q`、`w`。
- `tools/ks_lan.py`：只用標準函式庫的 socket 函式，`JEV_accel` 也用它。
- `tools/capture_edge.py`：一次完成邊緣置中、single、10–90 % 游標與兩張白底截圖。預設用 Demo CLK；接 F280049C 時加 `--go-file` 與 `--center 1.65`。

示波器卡住（查詢都逾時）時執行 `keysight.py recover`。

## 安裝

需要 Python 3.11。`requirements.txt` 與 RIGOL 那份相同。

`deploy.ps1` 會把 `keysight.py`、`ks_mcp.py`、`config.json`、`requirements.txt` 同步到 `%USERPROFILE%\.claude\mcp\keysight`，並在需要時建立那裡的 venv。第一次註冊：

```powershell
.\deploy.ps1
claude mcp add keysight --scope user -e KS_ADDR=192.168.137.60 -- "$HOME\.claude\mcp\keysight\.venv\Scripts\python.exe" "$HOME\.claude\mcp\keysight\ks_mcp.py"
```

之後改了程式只要再跑 `deploy.ps1`，然後在 Claude Code 重新連上 `keysight`（`/mcp`）。

`.venv/`、`captures/` 與 `__pycache__/` 不進 git。
