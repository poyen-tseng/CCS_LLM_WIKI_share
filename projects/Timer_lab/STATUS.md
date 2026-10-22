# Timer 實驗進度

來源是 `3_TIMER_lecture.pdf` 第 12–16 頁，實驗名稱是 *LAB experiment - Timer0 Module*。操作規格在 [TASK.md](TASK.md)。裝置是 LAUNCHXL-F280049C（TMS320F280049C）。原先預定用 Keysight DSO-X 4034A；2026-10-13 現場改用 RIGOL MSO5104，以下保留原建置紀錄。

2026-10-12：沒有開發板與示波器，先完成不需硬體的部分。

## 已完成（無硬體）

- [TIMER0_EX](TIMER0_EX)：由 `projects/Oscilloscope_read/GPIO_EX2` 複製改名，拿掉 `Comm.c/.h`。`main.c`、`Init.c`、`Init.h` 照講義第 13–16 頁重寫。`TIMER0_ISR` 沿用老師版 `f28004x_defaultisr.c`，沒有任何 `[修正]`。
- Headless CCS 匯入與建置：0 errors、0 warnings（CCS 21.0.1、cgt 25.11.1.LTS、RAM 連結）。
- `ccs_map_check(mode="ram")` ok：entry `_c_int00` 0x343、codestart 0x0、`_main` 0x3f6、`_TIMER0_ISR` 0x8034、`_Init_GPIO` 0x399、`_Init_PIE` 0x3b1、`_Init_CpuTimer` 0x3c9。專案裡只有一個 `TIMER0_ISR` 定義。
- `tools/timer_math.py` PASS：PRD = 20000000、TDDR = 0 → T = 0.20000001 s，方波 2.4999999 Hz、duty 50 %。
- `tools/flash_and_run.js` 已備好（由 LED_test 的腳本改輸出檔名），尚未在板上跑過。
- `tools/JEV_accel/config.json` 已登記 `TIMER0_EX` 為 RAM 模式。

## 2026-10-12 原硬體待辦（最新進度見下方）

- [ ] 用 `ccs_load` 下載執行（或 `tools/flash_and_run.js`）。
- [ ] 除錯器確認 `CpuTimer0.InterruptCount` 每秒約加 5。
- [ ] 示波器 CH1 接 J8 pin 80，100 ms/div 截圖。
- [ ] `ks_measure` FREQ／PER／PWID／NWID／PDUT／VTOP／VBASE，對照 TASK.md 合格標準。
- [ ] （選做）GPIO0 外接 LED 看閃爍。

## 工具問題（2026-10-12 已修正）

- 以前 `ccs_build`／`ccs_load` 給絕對路徑時，`.map` 檢查會到 `D:/code/_TI_CCS_no_chinese/TIMER0_EX` 找檔而報 not found，`ccs_load` 會因此拒絕下載。已修正。
- `tools/JEV_accel/config.json` 已用 `"path": "../../projects/Timer_lab/TIMER0_EX"` 登記，`ccs_build("TIMER0_EX")`、`ccs_load(project="TIMER0_EX")` 直接用名字即可，`ccs_env` 也會列出它。搬移前實測 `ccs_build` 以名字與絕對路徑都回 `map.ok = true`（ram）；新位置首次使用須重新匯入 CCS 並建置。
- jev-ccs MCP 伺服器要重新啟動才會載入修正後的程式。

## 倉庫裡沒有的檔

- 講義 PDF 頁面標了 CONFIDENTIAL，沒有放進這個公開倉庫。
- `TIMER0_EX/Debug/` 是編譯結果，依倉庫的 `.gitignore` 不進版控。


## 2026-10-13：RIGOL 上板、計時驗收與流程加速

- [x] 就地匯入新位置，CCS 21.0.1／TI cgt 25.11.1.LTS 建置 0 errors、0 warnings；JEV RAM map 檢查通過。原 Timer 程式與 PRD = 20000000 未修改。
- [x] XDS110 校驗下載至 RAM 並執行；不是 Flash 燒錄，也未測斷電保留。
- [x] 同一次下載連線中，`CpuTimer0.InterruptCount` 由 3 增至 23，觀察區間約 4.133 秒，增加 20 次。讀取後恢復執行。
- [x] CH1 10X 接 GPIO0、地夾接 GND，100 ms/div、1 V/div、RIGOL offset −1.65 V、上升緣 1.65 V、NORM；單次 STOP 後完成七項讀值、畫面閘門與白底 PNG。
- [x] FREQ 2.5002 Hz、PER 399.97 ms、PWID 199.98 ms、NWID 199.99 ms、PDUT 50%，符合 TASK 計時標準。RIGOL PDUT 原始值 0.5，腳本換算百分比並保留原值。
- [x] baseline／optimized 正式流程各 5 次通過自動計時及畫面檢查；中位數 11.628 → 9.376 秒（1.240 倍、耗時減少 19.37%），Scope 連線 5 → 1 次。校驗、map 與來源變更檢查保留。
- [x] 觸發超出範圍、垂直截斷兩種異常均被拒絕；還原後重新擷取通過。原始資料與還原截圖在 `timer_faults_v3_20261013/`；較早不成功的異常設定嘗試另外保留。
- [x] JEV 離線回歸 83 項通過；RIGOL 硬體檢查 3 項通過，未 skip。TCP_NODELAY 沒有實測改善，未採用。

**電壓量測限制**：正式比較 VTOP 2.8368–2.9202 V、VBASE 0 V；較早驗收 VTOP 3.1288 V、VBASE 0.20859 V。截圖可見平台低頻波動，原因尚未確認；不能宣稱乾淨的 3.3 V 平台已驗證。已向使用者詢問探棒接地方式，待補充接線條件及必要的後續量測。外接 LED 不在此次範圍。

完整研究方法、單位、重連影響及原始資料位置集中在 [Timer 流程加速 Wiki](../../docs/wiki/timer-flow-performance.md)。本機 JSON／CSV／PNG 在 `tools/JEV_accel/results/`，不進 Git。初次成功截圖是 `timer_acceptance_v3/0.png`，正式比較為 `timer_baseline_v2_20261013/` 與 `timer_optimized_v2_20261013/`。本機 `config.local.json` 已選擇 RIGOL，保留其他私人設定。

收尾已確認：關閉舊 daemon 後重新擷取仍通過，Timer RAM 程式保持執行；示波器回 RUN、探針 owner=free。最後 VTOP 2.9619 V、VBASE 0 V，計時值維持通過。最後白底截圖與 `final.json` 在 `timer_final_20261013/`；電壓平台波動限制仍保留。

## 2026-10-13：Timer 與流程加速研究簡報

- [x] 依使用者指定，以兩個 subagent 平行準備內容，使用本機 Microsoft PowerPoint COM 製作兩份私人報告；COM 存取以同一 mutex 序列化。
- [x] Timer 課程簡報共 9 頁，參考本機講義與指定 GPIO 範本，沿用 4:3 主版與作者資訊；涵蓋原理、接線、程式、中斷、實測及限制。
- [x] 流程加速研究共 8 頁，呈現十筆正式流程耗時、完整流程中位數、階段比較、採用與未採用方案、回歸／異常檢查及研究限制。
- [x] 兩份成品逐頁輸出 PNG 並檢查；來源備註齊全，沒有空占位符、舊 GPIO 實驗敘述或文字溢出。核對圖表及表格與配對 JSON；本次僅製作報告，未新增硬體實驗。

成品放在倉庫旁的私人目錄 `../CCS_private_archive/reports/Timer_lab/`：檔名前綴分別為 `20261013_TIMER_` 與 `20261013_流程加速研究_`，副檔名 `.pptx`。講義、範本、報告與私人 QA 圖片不加入公開 Git；可在該目錄的 `build_timer/` 與 `build_acceleration/` 查閱渲染及驗證紀錄。

研究圖表是嵌入的 Excel 物件，可在桌面 PowerPoint 配合 Excel 雙擊編輯，沒有外部 xlsx 連結。此環境隱藏視窗下的原生圖表建立失敗，因此採此替代方式。Timer 程式片段為可編輯文字。兩份報告皆保留「計時通過，電壓平台待查」及樣本／計時範圍限制，不將此次簡報檢查當作新硬體驗證。

技能要求的 loader 未出現在本次會話，但本機 Artifact Tool 與 Node 實際已安裝；診斷與已授權 PowerPoint 替代方式記錄於 [Codex 簡報工具可用性](../../docs/wiki/codex-artifact-runtime.md)。loader 的上游原因仍待查，尚未修復或變更外掛設定。

## 2026-10-15：報告須有設備與設定頁

- 依使用者要求，新增報告規則：量測簡報必須有一頁「量測設備與設定」，規則在 `docs/wiki/board-pins.md`「量測簡報必備：設備與設定頁」，`AGENTS.md` 已加入口。
- 已核對 2026-10-13 Timer 簡報：第 6 頁的設定與截圖 `timer_optimized_v2_20261013/0.png` 狀態列相符（100 ms/div、1.00 V/div、−1.65 V、上升緣 1.65 V、NORM）。同目錄 `0.json` 的 0.5 V/div、−1.439 V 是 JEV 建議值，不是實際設定。
- [ ] 簡報尚未補上設備與設定頁，本次只改了文件，沒有改簡報。補頁時：取樣率 25 MSa/s、記憶深度 25 Mpts 讀自同一張截圖；探棒型號與接地方式、擷取模式、頻寬限制、輸入阻抗當天沒有記錄，要寫「未記錄」。
