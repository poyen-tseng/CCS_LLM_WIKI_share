# 示波器網路設定：IP、DNS 與電腦直連

給實際接線與設定面板的人閱讀。本頁是 RIGOL MSO5104 與 Keysight DSO-X 4034A 的共用網路操作說明；MCP 安裝見各工具 README，波形操作見 [RIGOL](rigol-scope.md)、[Keysight](keysight-scope.md) 與 [JEV](jev.md)。回到 [Wiki 索引](README.md)。

2026-10-13 依倉庫程式、設定檔、既有實測紀錄與官方手冊整理。本次只做文件與靜態查核，沒有讀取目前網卡或示波器狀態。2026-10-07／12 的連線結果保留在 [歷史紀錄](../../tools/JEV_accel/SCOPE_IP_SETUP.md)，不代表現在已連線。

## 1. 接線與設定表

本倉庫的預設是電腦有線網卡與一台示波器背面的 **LAN 孔**用網路線直連；不是 USB Device 孔。第一次設定請使用這種接法。Wi-Fi 可繼續上網，但要確認它沒有使用相同的 `192.168.137.0/24` 網段；同網段、VPN 或網路共享造成的路由衝突見疑難排解。

| 欄位 | 電腦的專用有線網卡 | RIGOL MSO5104 | Keysight DSO-X 4034A |
| --- | --- | --- | --- |
| IPv4 位址 | `192.168.137.1` | `192.168.137.50` | `192.168.137.60` |
| 子網路遮罩 | `255.255.255.0`（首碼長度 `24`） | `255.255.255.0` | `255.255.255.0` |
| 預設閘道 | 留空 | `192.168.137.1` | `192.168.137.1` |
| DNS | 留空；此專用網卡不需名稱解析 | 不使用名稱解析，填法見下一節 | 不使用名稱解析，填法見下一節 |
| DHCP／AutoIP | 使用手動 IPv4 | DHCP OFF、AutoIP OFF、Static IP ON | 關閉 Automatic，手動指定參數 |
| SCPI TCP 埠 | — | `5555` | `5025` |

這是倉庫的直連配置，不是所有區域網路的通用值。兩端位址不同、位於同一子網即可通訊；同網段通訊不需要閘道。示波器閘道沿用既有配置，但電腦不因此自動成為路由器或 DNS 伺服器。

若要經交換器同時連接兩台，可以在專用網段保留上述三個不同位址；本次未驗證此拓樸。若接入學校、公司或家用路由器網路，請使用管理員分配的位址、遮罩、閘道與 DNS，或 DHCP 保留位址，並同步調整工具設定，避免 IP 衝突。不要直接將這組位址套到既有共用網路。

## 2. DNS、主機名稱與 AutoIP 要怎麼設

本倉庫直接連線到數字 IP，不依賴 DNS 或主機名稱。DNS 是把主機名稱轉為 IP 的服務；將 DNS 設為 `192.168.137.1` 並不會使電腦提供這項服務。直連沒有可用的上游 DNS，也不需要填 `8.8.8.8` 等公共 DNS。

- **電腦專用有線網卡**：DNS 留空。不更動用來上網的 Wi-Fi DNS。
- **示波器 DNS 欄位**：若允許留空，留空即可；若必須填數字，保留現有合法值即可完成本頁的 IP 連線，不必為此改成電腦 IP。這不代表該 DNS 在直連環境可用。
- **待驗證**：本機兩台示波器韌體是否接受空白或 `0.0.0.0` 作為停用 DNS 的填法。本頁不把這些值當成已驗證設定。若面板必須重填且拒絕套用，先記錄畫面與韌體版本，再核對該版本手冊；不要猜一個 DNS 伺服器。
- **Keysight Dynamic DNS／Multicast DNS**：數字 IP 連線不需要啟用；本頁不以主機名稱連線。使用名稱解析時才依實際網路服務設定。
- **DHCP／AutoIP**：直連通常沒有 DHCP 伺服器；AutoIP 可能產生 `169.254.x.x` 位址，與本頁的 `192.168.137.x` 不在同一子網。依下列面板步驟切到手動配置。

官方依據：[RIGOL MSO5000 User Guide，第 20 章 LAN Configuration](https://www.rigol.com/dam/global/downloads/brochures/en/user-manual/oscillosopes/MSO5000_UserGuide_EN.pdf) 說明手動網路參數；[Programming Guide，`:LAN:DNS`](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/MSO5000/MSO5000_ProgrammingGuide_EN.pdf) 定義 DNS 位址欄位。[Keysight 4000 X-Series User's Guide，第 21 章、印刷頁 361–362](https://www.keysight.com/us/en/assets/9018-03807/user-manuals/9018-03807.pdf) 說明 Automatic／Manual、DNS IP、Dynamic DNS 與 Multicast DNS。以上未確認本機面板接受停用 DNS 的填法。

## 3. Windows 電腦設定

1. 插上網路線，先以 PowerShell 執行 `Get-NetAdapter`，辨認插線的實體有線網卡。名稱不一定叫「乙太網路」，不要改到 Wi-Fi、VPN 或虛擬網卡。
2. 開啟「設定 → 網路和網際網路 → 乙太網路」，選擇該網卡。編輯「IP 指派」為手動，啟用 IPv4。
3. 填入 IP `192.168.137.1`、遮罩 `255.255.255.0`；若畫面要求「子網路首碼長度」，填 `24`。預設閘道與 DNS 留空，再儲存。不同 Windows 版本的欄位位置可能不同，也可在網卡 IPv4 內容設定。
4. 確認設定：

```powershell
Get-NetAdapter
Get-NetIPAddress -AddressFamily IPv4
Get-DnsClientServerAddress -AddressFamily IPv4
```

預期專用網卡有 `192.168.137.1/24`，接線及示波器開機後狀態為 `Up`。額外 IP 不一定有問題，請先辨認用途；不要任意移除既有設定。若此網卡由網路共享管理，先確認其設定來源再修改。

## 4. 示波器面板設定

### RIGOL MSO5104

1. 按 **Utility → IO → LAN**。
2. 關閉 DHCP 與 Auto IP，開啟 Static IP（部分版本稱 Manual IP）。
3. 填入 IP `192.168.137.50`、遮罩 `255.255.255.0`、閘道 `192.168.137.1`；DNS 依第 2 節處理。
4. 按 **Apply**，確認顯示的有效 IP 與網路狀態。選單名稱可能因韌體略有不同。

RIGOL 也提供 `:LAN:*` SCPI，但改 IP 會中斷原有連線；初次連線以面板操作為主。MCP 預設會擋下改網路指令，設定工具端 IP 不會替你更改儀器 IP。

### Keysight DSO-X 4034A

1. 按 **Utility → I/O → LAN Settings → Config**。
2. 依官方手冊，用 Entry 旋鈕選 **Automatic**，按軟鍵將它關閉，再以 **Modify** 設定手動參數。若本機韌體分列 DHCP／AutoIP／手動，則關閉前兩者並啟用手動。
3. 填入 IP `192.168.137.60`、遮罩 `255.255.255.0`、閘道 `192.168.137.1`；DNS 依第 2 節處理。主機名稱可保留。
4. 套用並確認有效 IP。套用方式以實際面板為準，不要為了套用手動設定而執行 LAN Reset。

本倉庫的 Keysight 操作紀錄未提供可用的 `:LAN` 設定指令，請使用面板。`*IDN?` 顯示舊品牌 **AGILENT TECHNOLOGIES** 是正常現象。

## 5. 工具設定與換機

工具設定只決定要連到哪裡；電腦網卡及示波器面板必須另行設定。`addr` 是示波器位址，`bind` 是電腦上已存在的本機位址，兩者不能互換。

| 入口 | 示波器位址來源（環境變數優先於設定檔） | 本機綁定位址 |
| --- | --- | --- |
| RIGOL MCP `scope`／`rigol.py` | `SCOPE_ADDR` → 該工具 `config.json` 的 `addr` | PyVISA 連線未實作明確 bind，依 Windows 路由 |
| RIGOL `tools/scope_lan.py`／`capture_edge.py` | `SCOPE_ADDR` → 該工具 `config.json` 的 `addr` | `SCOPE_BIND`，預設 `192.168.137.1` |
| Keysight MCP `keysight`／`keysight.py` | `KS_ADDR` → 該工具 `config.json` 的 `addr` | PyVISA 連線未使用讀入的 `bind`，依 Windows 路由 |
| Keysight `tools/ks_lan.py`／`capture_edge.py` | `KS_ADDR` → 該工具 `config.json` 的 `addr` | `KS_BIND` → 該工具 `config.json` 的 `bind`，預設 `192.168.137.1` |
| JEV `jev-scope`／CLI | `SCOPE_MODEL` 選機型；`SCOPE_ADDR` 覆寫所選機型位址 | `SCOPE_BIND` → JEV 設定的 `scope.bind` |

兩個 `capture_edge.py` 還可用 `--addr`、`--bind`、`--port` 明確覆寫。socket 腳本的空字串 bind 代表不綁定，會改由系統選擇來源位址。

JEV 建立連線時若收到 `OSError`，目前程式會再嘗試不綁定的連線；因此配置 bind 不保證每次都由指定網卡送出。網段或路由有衝突時應先處理衝突，再以識別碼核對設備。

**只有 JEV** 會合併其目錄下不進 Git 的 `config.local.json`，再套用環境變數。以下是完整的 JEV 本機覆寫範例；若已有此檔，合併需要的欄位，保留私人專案等既有設定：

```json
{
  "scope": {
    "model": "keysight",
    "bind": "192.168.137.1",
    "rigol": { "addr": "192.168.137.50", "port": 5555 },
    "keysight": { "addr": "192.168.137.60", "port": 5025 }
  }
}
```

換回 RIGOL 就將 `model` 改成 `rigol`。若曾設定共用的 `scope.addr`／`scope.port`，它們會優先於機型區塊；換機時要一併核對。`SCOPE_ADDR` 也會覆寫兩種機型，不會隨機型自動換成正確 IP。

在目前 PowerShell 執行 CLI 時可暫時設定：

```powershell
$env:SCOPE_MODEL = 'keysight'
$env:SCOPE_ADDR = '192.168.137.60'  # JEV
$env:SCOPE_BIND = '192.168.137.1'  # JEV／RIGOL socket 腳本
$env:KS_ADDR = '192.168.137.60'     # Keysight MCP／CLI／socket 腳本
$env:KS_BIND = '192.168.137.1'     # Keysight socket 腳本
```

這些變數只影響本程序及之後啟動的子程序。已運行的 Cursor／Claude Code MCP 不會自動取得它們；請在 MCP 啟動設定中指定所需變數，或修改對應設定檔後重新連線／重啟。單獨 MCP 不讀 JEV 的 `config.local.json`。

## 6. 依序驗證連線

以下指令供人手動執行，只查連線與識別碼，不更改波形設定。`python` 需指向可用的 Python 3；也可改成已安裝工具的 `.venv\Scripts\python.exe`。

1. 確認網卡 `Up`，且有正確 IP。
2. 對要使用的示波器測試 ping；不需要兩台都接著：

```powershell
ping -S 192.168.137.1 192.168.137.50  # RIGOL
ping -S 192.168.137.1 192.168.137.60  # Keysight
Get-NetNeighbor -IPAddress 192.168.137.50
Get-NetNeighbor -IPAddress 192.168.137.60
```

ARP／鄰居表應在正確網卡上出現實際 MAC；`Stale` 可只是快取，不能直接當作斷線。ping 無回覆也不能單獨證明 SCPI 不通，接著查識別碼。

3. 從已設定的本機位址連線，只送 `*IDN?`，讀到換行或逾時為止：

```powershell
# 選一台：RIGOL 用 .50 / 5555，Keysight 用 .60 / 5025。
$scopeAddress = '192.168.137.60'
$scopePort = 5025
@'
import socket
import sys
with socket.socket() as s:
    s.settimeout(3)
    s.bind(('192.168.137.1', 0))
    s.connect((sys.argv[1], int(sys.argv[2])))
    s.sendall(b'*IDN?\n')
    reply = b''
    while not reply.endswith(b'\n'):
        chunk = s.recv(1024)
        if not chunk:
            raise RuntimeError('連線關閉，尚未收到完整識別碼')
        reply += chunk
    print(reply.decode('ascii', errors='replace').strip())
'@ | python - $scopeAddress $scopePort
```

RIGOL 預期回覆包含 `RIGOL TECHNOLOGIES,MSO5104`；Keysight 包含 `AGILENT TECHNOLOGIES,DSO-X 4034A`。若回覆是別台儀器，先確認 IP 與接線。

4. 確認 MCP 在**目前會話**可用並重新連線，再以 `scope_idn` 或 `ks_idn` 核對；本機曾註冊不代表已連線。JEV 的後續操作依 [jev.md](jev.md)。識別碼成功只證明通訊成功，不代表已完成擷取、上板或硬體測試；不需為單純網路設定執行故障注入。

## 7. 疑難排解

| 症狀 | 優先檢查 |
| --- | --- |
| 網卡 Disconnected | 示波器是否開機、網路線兩端與 LAN 孔；連線速度不是接對設備的證據 |
| 儀器顯示 `169.254.x.x` | Automatic／DHCP／AutoIP 尚未關閉，手動 IP 尚未套用 |
| ARP 沒有有效 MAC、SCPI 逾時 | 面板上的有效 IP、電腦遮罩及正確網卡；先查指定 IP，不掃描網段 |
| bind 失敗或 Windows 錯誤 10049 | `192.168.137.1` 尚未配置在本機；bind 應填電腦 IP |
| socket 驗證成功，MCP 仍連不上 | 核對 MCP 啟動環境、舊 IP、重連與系統路由；PyVISA 驅動未明確 bind |
| Wi-Fi／VPN／共享也使用相同網段 | 執行 `Get-NetRoute -AddressFamily IPv4` 檢查；必要時改用不衝突的專用子網，同步更新電腦、儀器與工具 |
| ping 通但 SCPI 不通 | 核對 RIGOL 5555／Keysight 5025、遠端控制狀態、套用是否完成；Keysight 也可能是解析器卡住，見其 Wiki 的 recover 說明 |
| DNS 改了仍連不上 | 數字 IP 不使用 DNS；回到 IP、遮罩、接線、路由與 TCP 埠檢查 |

不要以固定 ping 延遲或 100 Mbps／1 Gbps 判定成功。以本次正確機型的 `*IDN?` 回覆為通訊驗證，另行記錄日期、IP、接線及版本。
