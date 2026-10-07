# 示波器 IP 設定：讓 RIGOL MSO5104 回到 192.168.137.50

這份說明讓電腦能透過有線網路控制示波器，`scope` 和 `jev-scope` 兩個 MCP，以及 `pytest -m hw`，都靠這個連線。

## 1. 目標拓樸

```
電腦「乙太網路」網卡                     RIGOL MSO5104 背面 LAN 孔
192.168.137.1 / 24   ── 網路線直連 ──   192.168.137.50 / 255.255.255.0
                                         閘道 192.168.137.1
                                         SCPI：TCP 5555
```

- 網路線**直接**接在電腦和示波器之間，不要經過交換器、路由器或學校網路孔。
- 電腦的 Wi-Fi 可以保持開著。我們的工具會先 bind `192.168.137.1` 再連線，封包不會走 Wi-Fi。

## 2. 當時的狀態（2026-10-07 只讀檢查；之後已恢復連線）

| 項目 | 結果 | 意思 |
|---|---|---|
| 電腦「乙太網路」網卡 | Up，1 Gbps，IP 有 192.168.137.1，另有一個不相關的位址 | 電腦端已經設好 |
| bind 192.168.137.1 後送 `*IDN?` | 逾時 | 示波器沒有回應 |
| ARP 表（192.168.137.x，以及網卡上另一個不相關的網段） | **全部 Unreachable**，包含 .50 | 線的另一端沒有任何裝置回應 |

> 更正（同日稍晚實測）：示波器連上、`*IDN?` 正常回應時，網卡同樣顯示 **1 Gbps**。所以連線速度**不能**用來判斷線的另一端是不是示波器，請以 ARP 和 `*IDN?` 為準。

當時（連不上時）最可能的原因依序是：
1. 示波器沒開機。
2. 網路線沒接到示波器背面的 LAN 孔。
3. 示波器的 IP 設定被改掉了。

## 3. 示波器面板設定

先前已經用 `:LAN:APPLy` 寫入過固定 IP，重開機會保留，**正常情況下只要確認數值沒變就好**。

1. 開機後按前面板的 **Utility**，進入 **IO**（或「I/O 設定」）→ **LAN**。選單名稱可能因韌體版本而略有不同，以實際畫面為準。
2. 確認或設定以下數值：

   | 欄位 | 值 |
   |---|---|
   | DHCP | 關（OFF） |
   | Auto IP | 關（OFF） |
   | Manual IP／Static IP | 開（ON） |
   | IP Address | `192.168.137.50` |
   | Subnet Mask | `255.255.255.0` |
   | Gateway | `192.168.137.1` |

3. 按 **Apply**（套用）。畫面上的 LAN 狀態應該變成「已連線」或「Configured」。

如果示波器已經能用其他方式連線，例如它暫時拿到別的 IP，也可以直接送出下面這串 SCPI，效果和面板設定相同：

```
:LAN:DHCP OFF
:LAN:AUToip OFF
:LAN:MANual ON
:LAN:IPADdress 192.168.137.50
:LAN:SMASk 255.255.255.0
:LAN:GATeway 192.168.137.1
:LAN:APPLy
```

`scope` MCP 會把 `:LAN:` 指令當成危險指令擋下來，必須明確加上 `allow_dangerous=true` 才會送出。這是刻意的設計，避免 Agent 誤改網路設定。

## 4. 電腦端檢查

電腦端目前已經正確設定，只有在數值不同時才需要修改。

- 設定 → 網路和網際網路 → 乙太網路 → IP 指派：手動，IPv4 `192.168.137.1`，子網路首碼長度 `24`（遮罩 255.255.255.0），閘道留空。
- 網卡上另外那個不相關的位址不影響連線，可以保留。

## 5. 驗證（依序執行，在 PowerShell）

| 步驟 | 指令 | 成功時應該看到 |
|---|---|---|
| 1 網卡狀態 | `Get-NetAdapter -Name 乙太網路` | Status `Up`（這台實測連上時是 1 Gbps；速度本身不代表接對） |
| 2 ping | `ping -S 192.168.137.1 192.168.137.50` | 有回覆，時間 < 1 ms |
| 3 ARP | `Get-NetNeighbor -IPAddress 192.168.137.50` | LinkLayerAddress 是真的 MAC（不是 `00-00-00-00-00-00`），State `Reachable` |
| 4 SCPI | 見下方 | 印出 `RIGOL TECHNOLOGIES,MSO5104,...` |
| 5 工具 | `cd D:\code\_TI_CCS_no_chinese\JEV_accel; .\.venv\Scripts\python.exe -m jev_accel menu --jev off` | 回傳 JSON，含 `"visible": true/false` |

步驟 4 的指令：

```powershell
python -c "import socket; s=socket.socket(); s.settimeout(3); s.bind(('192.168.137.1',0)); s.connect(('192.168.137.50',5555)); s.sendall(b'*IDN?\n'); print(s.recv(200)); s.close()"
```

五步都通過後，告訴 Agent「示波器已連上」，它就會開始硬體測試：先跑 `pytest -m hw`，再做 README「硬體驗證」裡的故障注入。故障注入結束後，Agent 會還原原本的設定。

## 6. 疑難排解

| 症狀 | 可能原因 | 處理 |
|---|---|---|
| 網卡 `Disconnected`，或 `Up` 但 ARP 查不到 .50 | 線沒接到示波器，或接到別的裝置 | 檢查線的兩端；示波器端要插在背面的 **LAN** 孔，不是 USB Device 孔 |
| 步驟 2、3 不通（ARP 是 00-00-…） | 示波器沒開機、線鬆了、示波器 IP 不是 .50 | 重插線；照第 3 節檢查面板上的 IP |
| ping 通，但步驟 4 逾時或被拒 | 示波器 LAN 的遠端控制沒開，或剛改完 IP 還在套用 | 等幾秒再試；確認面板 LAN 狀態；必要時重開示波器 |
| 步驟 4 有回應但不是 RIGOL | 封包走了 Wi-Fi（沒有 bind），或 .50 是別的裝置 | 一定要 bind `192.168.137.1`；確認線是直連 |
| 示波器只能用別的 IP | DHCP 打開了，或設定被重設 | 照第 3 節改回 .50。臨時不想改的話，用環境變數 `SCOPE_ADDR=<新IP>`，或在 `config.local.json` 寫 `{"scope": {"addr": "<新IP>"}}`，不需要改程式 |

資料來源：`@CCS_LLM_WIKI\oscilloscope-mso5104.md`、`CCS_LLM_WIKI_share\LLM_WIKI\rigol-scope.md`，以及 2026-10-07 在本機做的只讀網路檢查。

## 7. 實測紀錄

2026-10-07 恢復連線後：`*IDN?` 回 `RIGOL TECHNOLOGIES,MSO5104` 與韌體版號，ARP 狀態 Reachable，網卡 1 Gbps，`pytest -m hw` 3/3 通過。
