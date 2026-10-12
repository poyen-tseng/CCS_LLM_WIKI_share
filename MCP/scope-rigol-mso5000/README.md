# scope-rigol-mso5000

經區域網路控制 RIGOL MSO5000（這台是 MSO5104）。SCPI 在 TCP 連接埠 5555。預設位址在 `config.json`，目前是 `192.168.137.50`。環境變數 `SCOPE_ADDR` 可以覆寫。

工具包括讀識別碼、讀設定、調通道／時基／觸發、單次擷取、截圖、下載波形 CSV，以及一條會擋下重置與改網路指令的原始 SCPI。

要截置中、有量測線的波形圖，先讀 [rigol-scope.md](../../LLM_WIKI/rigol-scope.md)。配合的獨立腳本在 [tools](tools)。接上示波器後的速度實驗在 [scope-speed-experiments.md](../scope-speed-experiments.md)。

## 截圖

放進報告或投影片的圖要用白色背景。`screenshot()` 與 `tools/capture_edge.py` 送 `:DISP:DATA? ON,ON,PNG`。三個參數是彩色、反相、格式；第二個是反相，`ON` 才是白底，`OFF` 是黑底。反相只作用在回傳的圖。確認側邊選單時仍用黑底圖，門檻寫在 wiki 的「側邊選單偵測」。

## 安裝

需要 Python 3.11。在這個資料夾：

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`.venv/`、`captures/` 與 `__pycache__/` 不進 git。

Claude Code 用該 venv 的 python 執行 `scope_mcp.py`，例如：

```json
{
  "command": "<這個資料夾>\\.venv\\Scripts\\python.exe",
  "args": ["<這個資料夾>\\scope_mcp.py"]
}
```

`deploy.ps1` 會把 `rigol.py`、`scope_mcp.py`、`config.json`、`requirements.txt` 同步到 `%USERPROFILE%\.claude\mcp\scope`，並在需要時建立那裡的 venv。同步後要在 Claude Code 重新連上名為 `scope` 的伺服器。
