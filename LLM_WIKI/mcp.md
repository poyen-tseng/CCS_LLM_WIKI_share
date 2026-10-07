# Cursor 裡的 CCS MCP

CCS 21 要開著，這四個伺服器才有作用。它們是官方代理，不是從執行檔反組譯來的。工具名稱以 2026-09-22 這台 Cursor 連上的 schema 為準。

回到 [README.md](README.md)。路徑見 [entry-points.md](entry-points.md)。

燒錄、halt、讀 PC 先用 [jev.md](jev.md) 的 `jev-ccs`（`ccs_load`、`ccs_run_control`）。需要中斷點、呼叫堆疊或變數時，先 `ccs_release`，再使用下面的 `ccs-debug`。

## 先選哪一組

| 要做的事 | 命名空間 |
| --- | --- |
| 看專案、編譯、改編譯旗標、匯入專案 | `ccs-project` |
| 下載、執行、中斷點、記憶體、變數 | `ccs-debug` |
| 改 `.syscfg` 並重產生程式 | `ccs-sysconfig` |
| 看 LaunchPad 的 UART 輸出 | `ccs-serial` |

`GPIO_EX1` 沒有 `.syscfg`。沒有設定檔就不要呼叫 `ccs-sysconfig` 的 `openFile`。

長時間操作（建置、啟動除錯）若回傳 `taskId`，用同一個命名空間的 `waitForResult` 再等。`waitForResult` 約等 2 分鐘，還沒好就再叫一次。

## ccs-project

讀專案時把 `properties` 縮到需要的欄位，例如 `name`、`location`、`device`、`connection`、`activeBuildConfiguration`、`toolVersion`。

常用工具：

- `getActiveProjectName`、`getProjectDescriptors`
- `getProjectProductReferences`：讀寫專案相關路徑之前先叫，拿 SDK 實際位置
- `buildProject`：若這個專案已有除錯工作階段，先用 `ccs-debug` 的 `terminate`
- `getToolFlags` / `setToolFlags`：compiler、linker、hex、objcopy、sysconfig。改旗標前先讀，避免重複加上已有的 `-I`、`-D`、`-O`
- `getToolOptions`：只在需要「這個選項有哪些合法值」時用，結果寫在檔案裡
- `importProject`、`copyProject`、`renameProject`
- `getCompilers`、`getProducts`：產品清單不要用裝置型號當 `nameFilter`
- `getActiveSysConfigMCPVersion`、`changeSysConfigVersion`：SysConfig 打不開檔時才用來對齊版本

2026-09-22 讀到的作用中專案是 `GPIO_EX1`，編譯器 `TI v25.11.1.LTS`，連線 `TIXDS110_Connection`。

## ccs-debug

當時沒有進行中的除錯工作階段。要下程式時：

1. `getLaunchConfigurations` 或 `getTargetConfigurations` 確認名字。
2. 有專案用 `debugProject`（預設會自動連上在跑程式的核心）。只有 `.ccxml`、沒有專案時用 `launchTargetConfiguration`。
3. 核心被藏起來時先 `showAllCores`，再 `listCores`、`connectTarget`。
4. `loadProgram` 載入 `.out`。只要符號、不重寫記憶體時用 `loadSymbols`。
5. `setSourceBreakpoint` 用原始檔與行號。除錯工作階段進行中，中斷點才會被驗證。
6. `pause`、`continue`、`stepIn`、`stepOver`、`stepOut`、`restart`、`reset`（可用的 reset 先問 `getResets`）。
7. 停下來之後 `getStackFrames`、`getVariables`、`evaluate`、`readMemory`、`writeMemory`。
8. 主控台：`readFromCio` / `writeToCio`、`readFromDebugOutput`、`readFromGelOutput`。要等某段文字用對應的 `waitForPattern*`。已印出的舊訊息要先 `set*LogDirectoryPath`，再搜複製出來的檔。
9. 結束用 `terminate`。

`writeToCio` 預設會等回應（約 2000 ms）。有問答就設 `timeout`，不要拆成先寫再讀。

## ccs-sysconfig

只有工作區裡真的有 `.syscfg` 才用。

1. 不知道路徑時先 `listFiles`，已知路徑就直接 `openFile`。
2. `openFile` 回傳的 `additionalInstructions` 要照做。之後的工具都作用在目前打開的那一個檔。
3. `listModules` → `addModuleInstances` → `getInstanceConfiguration` → `changeConfiguration`。
4. 接線用 `manageConnections`，不要用 `changeConfiguration` 假裝在接腳。
5. `getErrorsAndWarnings` 確認沒有錯誤後 `save`。`save` 會寫回 `.syscfg` 並重產生程式。
6. 換晶片前先 `listMigrationTargets`，再 `migrate`。
7. 結束 `closeFile`。

SDK 範例怎麼設定，用 `inspectExample`，不要猜。

## ccs-serial

- 連 TI 板子用 `connectToTIDevices`，不要先叫 `connectSerialPort`，除非使用者指定了 COM。
- `listSerialPorts` 預設只列 TI 裝置。
- 多數 C2000 範例的 UART 是 115200。若專案有 SysConfig，先看設定裡的鮑率再連。
- 送指令用 `writeToSerial` 並帶 `timeout`。很多指令要結尾 `\r\n`。
- 等開機訊息用 `waitForPatternInSerial`。
- 查已經印過的內容：先 `setSerialLogDirectoryPath`，再搜那個目錄。
