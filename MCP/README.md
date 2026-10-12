# MCP

這個資料夾只放本機用的 MCP 伺服器。一台伺服器一個子夾，不要把程式直接攤在這裡。

| 子夾 | 做什麼 |
| --- | --- |
| [scope-rigol-mso5000](scope-rigol-mso5000) | 經區域網路控制 RIGOL MSO5000 示波器（MCP `scope`） |
| [scope-keysight-dsox4000](scope-keysight-dsox4000) | 經區域網路控制 Keysight DSO-X 4034A 示波器（MCP `keysight`） |

接上示波器後的速度實驗在 [scope-speed-experiments.md](scope-speed-experiments.md)。

Haiku 5.5 Max 與 Opus 5.5 Medium 操作 Keysight 示波器的速度與正確率比較在 [scope-model-race.md](scope-model-race.md)：兩邊都答對，Opus 快 4.9 倍。
