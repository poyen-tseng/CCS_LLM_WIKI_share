# 磁碟上的官方入口

安裝根目錄是 `C:\ti\ccs2101`。下面路徑都在 2026-09-22 於這台電腦確認存在。UniFlash 的 `dslite.bat` 不在 `C:\ti`，不要假設能呼叫它。

回到 [README.md](README.md)。

## 每天會用到的

| 用途            | 路徑                                                                                        |
| ------------- | ----------------------------------------------------------------------------------------- |
| 開啟 IDE        | `C:\ti\ccs2101\ccs\theia\ccstudio.exe`                                                    |
| 無介面建置         | `C:\ti\ccs2101\ccs\eclipse\ccs-server-cli.bat`                                            |
| 除錯腳本          | `C:\ti\ccs2101\ccs\scripting\run.bat`                                                     |
| 腳本文件          | `C:\ti\ccs2101\ccs\scripting\docs\index.html`                                             |
| Python 腳本環境   | `C:\ti\ccs2101\ccs\scripting\python`                                                      |
| MCP 代理        | `C:\ti\ccs2101\ccs\theia\resources\app\plugins\ccs-ai\extension\dist\mcp-server-proxy.js` |
| SysConfig 命令列 | `C:\ti\ccs2101\ccs\utils\sysconfig_1.28.1\sysconfig_cli.bat`                              |
| C28x 編譯器      | `C:\ti\ccs2101\ccs\tools\compiler\ti-cgt-c2000_25.11.1.LTS\bin\cl2000.exe`                |
| C2000Ware     | `C:\ti\C2000Ware_5_00_00_00`                                                              |

`ccs-server-cli.bat` 用 CCS 自帶的 Node 啟動 `com.ti.ccs.apps_*` 外掛裡的 `app-launcher.js`。除錯腳本的 `run.bat` 則呼叫 `ccs_base\cloudagent\node.exe` 與 `ccs\scripting\launcher.mjs`。

## MCP 代理引數

同一個 `mcp-server-proxy.js`，後面加一個引數決定伺服器：

- `project`：專案與建置（Cursor 命名空間 `ccs-project`）
- `debug`：除錯（`ccs-debug`）
- `sysconfig`：SysConfig（`ccs-sysconfig`）
- `serial`：序列埠（`ccs-serial`）

官方說明：[CCS MCP](https://software-dl.ti.com/ccs/esd/documents/users_guide_ccs_20.5.1/ccs_ai.html)。Cursor 已接上這四個時，直接呼叫工具，不必自己再啟動 proxy。

## 舊介面與授權

- 舊的 DSS 仍在 `C:\ti\ccs2101\ccs\ccs_base\scripting`。新腳本用 `ccs\scripting`，不要新寫 DSS。
- 二進位授權（禁止反組譯）在 `C:\ti\ccs2101\ccs\theia\resources\app\plugins\ccs-ai\extension\LICENSE.txt`，`ccs-project` 外掛有同一段。見 [boundaries.md](boundaries.md)。
- 第三方元件清單：`C:\ti\ccs2101\ccs\doc\Code Composer Studio_21.0.1_manifest.html`。介面本體是 Eclipse Theia，原始碼在 [eclipse-theia/theia](https://github.com/eclipse-theia/theia)。

## 這個專案的連線檔

- 目標設定：`D:\code\_TI_CCS_no_chinese\GPIO_EX1\targetConfigs\TMS320F280049C.ccxml`（XDS110）
- 除錯啟動：`D:\code\_TI_CCS_no_chinese\GPIO_EX1\.launches\GPIO_EX1.launch`

命令列與腳本的用法見 [cli-and-scripting.md](cli-and-scripting.md)。CCS 已開著時優先走 [mcp.md](mcp.md)。
