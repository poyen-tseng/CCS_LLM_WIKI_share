# 不要逆向工程 CCS

回到 [README.md](README.md)。

寫這個專案、修中文註解、編譯、下載、看變數，都不需要拆 CCS。官方入口在 [entry-points.md](entry-points.md)、[mcp.md](mcp.md)、[cli-and-scripting.md](cli-and-scripting.md)。

## 授權

`C:\ti\ccs2101\ccs\theia\resources\app\plugins\ccs-ai\extension\LICENSE.txt`（`ccs-project` 外掛同一段）寫明：對以二進位提供的軟體，不允許 reverse engineering、decompilation 或 disassembly。TI 也沒有義務提供那些元件的原始碼。

因此不要對這些做反組譯或反編譯：

- `C:\ti\ccs2101\ccs\theia\ccstudio.exe`
- `C:\ti\ccs2101\ccs\ccs_base` 裡的 DebugServer、emulation DLL
- 打包後的 `ccs-ai`、`ccs-project` 外掛

## 可以做的事

- 介面行為：CCS 20 起是 Eclipse Theia。查 [eclipse-theia/theia](https://github.com/eclipse-theia/theia) 與 `C:\ti\ccs2101\ccs\doc\Code Composer Studio_21.0.1_manifest.html`，不要從 `ccstudio.exe` 挖。
- 看自己程式的組合語言：除錯時的 Disassembly 看的是專案的 `.out`，不是在拆 CCS。
- 中文變成 `�`：多半是檔案為 Big5、編輯器當 UTF-8。改原始檔編碼與 `.settings\org.eclipse.core.resources.prefs`，不要改 IDE 二進位。

## 舊腳本

`ccs_base\scripting` 的 DSS 仍附在安裝裡，文件也在。新的自動化用 `C:\ti\ccs2101\ccs\scripting`。選舊 API 不是逆向，只是之後 TI 不再建議新用。
