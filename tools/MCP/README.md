# MCP

這個資料夾只放本機用的 MCP 伺服器。一台伺服器一個子夾，不要把程式直接攤在這裡。

| 子夾                                                 | 做什麼                                              |
| -------------------------------------------------- | ------------------------------------------------ |
| [scope-rigol-mso5000](scope-rigol-mso5000)         | 經區域網路控制 RIGOL MSO5000 示波器（MCP `scope`）           |
| [scope-keysight-dsox4000](scope-keysight-dsox4000) | 經區域網路控制 Keysight DSO-X 4034A 示波器（MCP `keysight`） |
| [scope-tek-tds2000b](scope-tek-tds2000b) | 經 USB 控制 Tektronix TDS2014B 示波器（MCP `tek`；WinUSB 驅動見子夾 README） |
| [scope-tek-mso2000](scope-tek-mso2000) | 經 USB 控制 Tektronix MSO2014 示波器的類比通道（MCP `mso`；WinUSB 驅動見子夾 README） |

接上示波器後的速度實驗在 [scope-speed-experiments.md](scope-speed-experiments.md)。

## 示波器網路設定（給人閱讀）

第一次接線或要設定 IP、DNS、DHCP，請讀 [示波器網路設定](../../docs/wiki/scope-network-setup.md)：包含 Windows 網卡、兩台儀器面板、工具設定與連線驗證。

| 直連預設 | IP | 遮罩 | 閘道 | SCPI TCP 埠 |
| --- | --- | --- | --- | --- |
| 電腦專用有線網卡 | `192.168.137.1` | `255.255.255.0` | 留空 | — |
| RIGOL MSO5104 | `192.168.137.50` | `255.255.255.0` | `192.168.137.1` | `5555` |
| Keysight DSO-X 4034A | `192.168.137.60` | `255.255.255.0` | `192.168.137.1` | `5025` |

直接用 IP 控制不需要 DNS；電腦專用網卡 DNS 留空，示波器欄位處理見主文件。這些是設定檔預設，不代表目前已連線；接入既有區域網路時須使用該網路的參數。

Haiku 5.5 Max 與 Opus 5.5 Medium 操作 Keysight 示波器的速度與正確率比較在 [scope-model-race.md](scope-model-race.md)：兩邊都答對，Opus 快 4.9 倍。
