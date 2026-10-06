# 命令列、腳本、編譯器

CCS 沒開，或要在腳本裡重複下載時用這頁。CCS 已經開著、人在 Cursor 裡，優先用 [mcp.md](mcp.md)。

回到 [README.md](README.md)。執行檔路徑見 [entry-points.md](entry-points.md)。

## ccs-server-cli

```bat
C:\ti\ccs2101\ccs\eclipse\ccs-server-cli.bat -noSplash -workspace "<workspace_dir>" -application <app> [選項]
```

常用 application：

| application | 作用 |
| --- | --- |
| `com.ti.ccs.apps.importProject` | 匯入既有專案，`-ccs.location <路徑>` |
| `com.ti.ccs.apps.createProject` | 從 `.projectspec` 或裝置 id 建立 |
| `com.ti.ccs.apps.buildProject` | 建置，`-ccs.projects` 或 `-ccs.workspace` |
| `com.ti.ccs.apps.modifyProject` | 改編譯選項，`-ccs.project <名字>` |
| `com.ti.ccs.apps.inspect` | 檢查專案 |
| `com.ti.ccs.apps.createTargetConfiguration` | 建立 `.ccxml` |
| `com.ti.ccs.apps.initialize` | 指定 compiler 或 product 的搜尋路徑 |

某一個 application 的選項以這台 CCS 的說明為準：

```bat
ccs-server-cli.bat -noSplash -workspace "<workspace_dir>" -application com.ti.ccs.apps.buildProject -ccs.help
```

文件：[Full API Guide](https://software-dl.ti.com/ccs/esd/documents/users_guide_ccs_20.5.0/ccs_project-command-line-full-api-guide.html)。

建置 `GPIO_EX1` 時，workspace 指的是 CCS 的 workspace 目錄，不是專案資料夾本身。專案若已在 CCS 裡打開，直接用 MCP 的 `buildProject` 比較不容易指錯 workspace。

## CCS Scripting

新的除錯腳本。文件在 `C:\ti\ccs2101\ccs\scripting\docs`，範例在 `C:\ti\ccs2101\ccs\scripting\examples`。

JavaScript 用：

```bat
C:\ti\ccs2101\ccs\scripting\run.bat your_script.js
```

最小流程：

```javascript
const ds = initScripting();
ds.configure("D:/code/_TI_CCS_no_chinese/GPIO_EX1/targetConfigs/TMS320F280049C.ccxml");
const session = ds.openSession("C28xx_CPU1");
session.target.connect();
session.memory.loadProgram("D:/code/_TI_CCS_no_chinese/GPIO_EX1/Debug/GPIO_EX1.out");
session.target.run();
ds.shutdown();
```

CCS 有附 Python 3.14，執行檔在 `C:\ti\ccs2101\ccs\ccs_base\DebugServer\ca-modules\tools\python3.14\python.exe`。`ccs\scripting\python` 是 launcher、範例與 `site-packages`，裡面沒有 `python.exe`；該目錄的 `run.bat` 會呼叫上面這顆直譯器。`setup.bat` 會設定 `PYTHONPATH`，並用系統 PATH 上的 `python` 做 `pip install`。API 與 JavaScript 對應，語法不同。文件：[CCS Scripting](https://software-dl.ti.com/ccs/esd/documents/users_guide_ccs_20.5.0/ccs_debug-scripting.html)。

`C:\ti\ccs2101\ccs\ccs_base\scripting` 是舊的 DSS（Java）。不要為新工作再寫 DSS。

## SysConfig CLI

```bat
C:\ti\ccs2101\ccs\utils\sysconfig_1.28.1\sysconfig_cli.bat --script <file.syscfg> -o <輸出目錄> --compiler ccs
```

`GPIO_EX1` 沒有 `.syscfg`，這條用不到。有設定檔時，CCS 開著也可以用 MCP `ccs-sysconfig`，不必另開 CLI。

## 編譯器

`cl2000.exe` 在 `C:\ti\ccs2101\ccs\tools\compiler\ti-cgt-c2000_25.11.1.LTS\bin`。日常建置仍應走 CCS 專案（MCP 或 `ccs-server-cli`），這樣 include、`.cmd`、執行期庫才跟 `.cproject` 一致。只有在確認旗標時才直接叫 `cl2000`。目前專案使用的就是這版 `25.11.1.LTS`。

## UniFlash

本機 `C:\ti` 底下沒有 `dslite.bat`。不要編造 UniFlash 路徑，也不要假設已安裝。

若之後裝上 UniFlash，C2000 燒錄用它自己的 `dslite.bat`，模式預設是 flash。官方快速指南：[UniFlash CLI](https://software-dl.ti.com/ccs/esd/uniflash/docs/v9_6/uniflash_quick_start_guide.html)。呼叫時不要再多寫一次 `dslite.exe flash`，批次檔會自己帶執行檔。二進位檔加位址的寫法是 `file.bin,0x........`（逗號，不是空白）。

開發階段下載 `.out` 用 CCS 除錯或 CCS Scripting 即可，不必先裝 UniFlash。
