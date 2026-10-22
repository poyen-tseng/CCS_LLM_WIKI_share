# Codex 簡報技能與工具可用性

2026-10-13 在 Windows x64 本機排查 Presentations 技能要求的 `load_workspace_dependencies`。本頁記錄安裝與會話工具的差異；不能由此推論所有 Windows 或其他 Codex 會話都缺少工具。

## 本次已確認的事實

| 檢查 | 本機結果與證據 |
| --- | --- |
| Presentations 外掛 | 本機設定已啟用 `presentations@openai-primary-runtime`；版本 `26.813.12317` 的技能檔存在。 |
| 外掛 manifest | `%USERPROFILE%/.codex/plugins/cache/openai-primary-runtime/presentations/26.813.12317/.codex-plugin/plugin.json` 宣告 `skills`，沒有宣告 MCP 工具服務。此檔不提供 loader 的實作。 |
| 技能要求 | `skills/presentations/SKILL.md` 要求先呼叫 `load_workspace_dependencies`，取得 `RUNTIME_NODE`、`RUNTIME_NODE_MODULES`、`RUNTIME_BIN_DIR`。 |
| 目前會話工具 | 檢查本次 agent 可呼叫工具清單，沒有 `load_workspace_dependencies`。技能出現在清單中不代表其要求的工具也已連線。 |
| 本機 runtime | `%USERPROFILE%/.cache/codex-runtimes/codex-primary-runtime/runtime.json`：bundle `26.813.12317`，Artifact Tool `2.8.43`，Node `v24.19.0`，平台 `win32/x64`。 |
| 實際套件與執行檔 | runtime 下 `dependencies/node/node_modules/@oai/artifact-tool/package.json` 存在且版本 `2.8.43`；`dependencies/node/bin/node.exe` 也存在。不能將本次問題描述為「SDK／Node 未安裝」。 |

目前可確認的直接原因是：**技能要求與此會話提供的工具未對齊**。外掛技能屬於指令與資源，MCP 工具是另一項能力；官方說明也區分這兩者。[Skills 概念](https://developers.openai.com/plugins/concepts/skills)、[Plugin 結構](https://developers.openai.com/plugins/build/plugins)。

manifest 沒有 MCP 宣告，表示此技能套件本身不註冊該工具；不能因此斷言 loader 必須由它註冊。公開文件與本機證據未能確認上游為何未提供 loader，可能的內部註冊或版本問題仍待查，不能寫成已確認的產品缺陷。

## 歷史訊息與推論界線

本機日誌在 2026-10-11 10:56:42（Asia/Taipei）曾警告快取刷新時找不到已設定的 Presentations marketplace 項目；2026-10-13 讀取的 marketplace 清單已有 Presentations。這是歷史快取不一致的證據，尚不能證明它造成目前工具缺失。

目前 shell 未設定上述三個 runtime 環境變數也不是獨立故障證據：技能原本預期由 loader 回傳執行環境。沒有證據支持以切換 `js_repl`、重裝套件或修改產生的外掛快取作為修復；本次未進行這些修改，也未讀取或輸出驗證金鑰。

## 後續接手方式

1. 先查本次 agent 的實際工具清單，再讀技能要求。不要將本機設定、已安裝技能或另一會話的工具當作目前連線證據。
2. 缺工具時分別核對技能、manifest、runtime 描述與實際套件，明確區分「未安裝」與「未暴露工具」。保留版本及日期，不輸出機密設定。
3. 若需回報上游，提供會話工具缺失、技能要求、外掛／runtime 版本與平台等最小證據；將確定事實與待查原因分開。
4. 本次使用者明確指定改用本機 PowerPoint 並平行製作，因此以 PowerPoint COM 完成兩份報告。這是已授權的替代製作方式，不代表 loader 已修好。其他任務仍應先遵守其技能與使用者要求。

## 本機 PowerPoint 替代流程的已驗證限制

本次以 `Presentation.Open(..., WithWindow=false)` 複製原範本投影片並編輯，逐頁輸出 PNG 檢查，保留來源備註。多個 agent 的 COM 操作以同一命名 mutex 序列化，內容準備可平行；只關閉自己開啟的簡報，避免影響使用者檔案。

此環境在隱藏視窗下 `AddChart`／`AddChart2` 回傳 `0x80004005`，先啟動隱藏 Excel 仍失敗。改由隱藏 Excel 建立圖表，再將 `Excel.Sheet.12` 物件嵌入 PowerPoint 成功；圖表與資料可編輯，沒有外部活頁簿連結。這是本次環境結果，不是所有 Office 版本的通則。
