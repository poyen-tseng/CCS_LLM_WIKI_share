# Timer0 完整流程加速：RIGOL 實測

2026-10-13 使用 LAUNCHXL-F280049C 與 RIGOL MSO5104，完成 Timer0 計時驗收並比較相同工作的兩種工具流程。專案規格見 [Timer TASK](../../projects/Timer_lab/TASK.md)，進度見 [STATUS](../../projects/Timer_lab/STATUS.md)。回到 [Wiki 索引](README.md)。

## 條件與驗收

- CCS 21.0.1、TI C2000 編譯器 25.11.1.LTS、C2000Ware 5.00.00.00，使用 XDS110、C28xx_CPU1；既有 `TIMER0_EX` RAM 程式未修改。
- RIGOL MSO5104，韌體 `00.01.03.03.00`，`192.168.137.50:5555`，電腦有線位址 `192.168.137.1/24`。本次會話沒有 JEV／scope MCP，使用 JEV `.venv` 的 API／CLI。
- 接線：10X 探棒尖端接 GPIO0／PWM1A，地夾接板上 GND，USB 接 USB101。接頭編號有版本差異，見 [板子接腳](board-pins.md)，不可只依「80」接線。
- CH1：10X、DC、1 V/div、offset **−1.65 V**；100 ms/div、水平偏移 0；CH1 上升緣、1.65 V、NORM。先填滿一秒畫面，再單次擷取；STOP 後讀取同一次凍結的資料。
- 自動驗收：頻率 2.5 Hz、週期 0.4 s、高低脈寬各 0.2 s，誤差 ±1%；占空比 49–51%；各讀值須有效，畫面不截斷且至少顯示 2 個週期。

計時實測：FREQ **2.5002 Hz**、PER **399.97 ms**、PWID **199.98 ms**、NWID **199.99 ms**、PDUT **50%**。兩種正式流程各 5 次全部通過上述自動檢查。中斷計數在同一次下載連線內由 3 增至 23，觀察區間約 4.133 秒，增加 20 次，符合約每秒 5 次的預期。

電壓限制：正式比較的 VTOP 為 **2.8368–2.9202 V**、VBASE 為 **0 V**；較早驗收曾讀到 VTOP 3.1288 V、VBASE 0.20859 V。截圖可見高低平台有低頻波動，尚未確認接地、探棒或其他原因。原 TASK 只指定「約 3.3 V／約 0 V」，未訂電壓誤差；因此本頁將計時與畫面通過分開記錄，**不宣稱已驗證乾淨的 3.3 V 電壓平台**。

## 比較方式與結果

兩種流程均執行增量建置與 RAM map 檢查、來源變更檢查、校驗下載並運行、儀器設定回讀、新單次擷取、週期畫面閘門、七項量測與白底 PNG。JEV 使用 `auto`，本次正式畫面判斷均來自 L0，沒有把模型呼叫時間當成已測項目。

首次就地匯入約 5.84 秒、headless 建置約 11.69 秒；CCS scripting 冷初始化約 25.09 秒，首次 load 呼叫約 35.51 秒，均另列，不計入以下暖機比較。兩批第一筆都包含重新連接目標，其餘重用已連接的 daemon session。計時範圍從增量建置開始至 PNG／識別碼／SCPI 錯誤核對完成；環境檢查、批次前準備與最後還原／釋放不計入。

| 項目（5 次中位數） | baseline | optimized |
| --- | --- | --- |
| 完整流程 | 11.628 s | 9.376 s |
| 各次範圍 | 11.329–13.182 s | 9.095–11.212 s |
| 建置 | 0.234 s | 0.250 s |
| 校驗下載 | 2.214 s | 2.214 s |
| 設定與回讀 | 1.566 s | 1.167 s |
| 新單次擷取 | 1.640 s | 1.799 s |
| 畫面檢查 | 4.390 s | 2.582 s |
| 七項量測 | 1.165 s | 1.054 s |
| 最終截圖與核對 | 0.264 s | 0.301 s |
| 流程內 Scope 連線數 | 5 | 1 |
| Scope 指令數（包含輪詢） | 77 | 75 |
| CCS API 呼叫數 | 2 | 2 |
| 明確等待時間（不含舊 drain 等待） | 4.95 s | 3.00 s |
| 自動檢查通過 | 5/5 | 5/5 |

整段中位數加速 **1.240 倍**，耗時減少 **19.37%**。階段中位數不必相加等於整段中位數。改善主要在畫面檢查與等待；建置、校驗下載和硬體擷取沒有宣稱變快。這是依序跑兩批、每批 5 次的首輪研究，未做大量交錯重測，不報可靠 p95，也不是不同模型的比較。

## 實作與已採用的改善

- 新入口：在 `tools/JEV_accel` 用 `.venv` 執行 `bench/timer_flow.py --mode baseline|optimized --runs 5`；輸出 JSON、CSV、PNG 到忽略的 `results/`，失敗回傳非零並執行還原／釋放。本機 `config.local.json` 選擇 `scope.model=rigol`，其他私人設定保留。
- optimized 在一次流程中重用 Scope 連線；只在同一次 STOP 擷取中重用 PER／VTOP／VBASE。每次重新建置檢查、下載校驗及擷取，沒有重用上次波形。
- `view="period"`／`--view period --min-periods 2` 不要求第一個邊緣置中，也不查 ns 上升時間；觸發準位須在擺幅 10%–90% 內。這是完整週期的檢查，既有 edge／delay 規則不變。縮短時基導致不足兩個週期會被拒絕。
- RIGOL 的 period 閘門在 `apply=true` 關閉選單後，只重新讀選單影像，不重做會再次打開 Measure 的量測查詢。截圖前完成所有量測及清量測列，再檢查選單；MOFF 只在確認選單開著時送出。
- optimized 明確讀完 IEEE 區塊的 LF／CRLF，確認後不再用逾時 drain 等待；EOF、分段回覆與錯誤尾碼都會失敗，不將缺資料當成功。此路徑目前僅供 RIGOL 流程測試入口採用，舊 caller 的預設行為保留。
- 設定後仍等待一秒以填滿 100 ms/div 的畫面；STOP 已確認後取消多餘的 1.5 秒 frame settle。必需的畫面更新與選單更新等待仍保留。
- TCP_NODELAY 做兩輪 OFF／ON，每段 100 次 IDN。OFF 中位數約 0.971 ms、ON 約 1.078 ms，識別碼與波形點數一致；未達「至少 1 ms 且 20% 改善」，所以**不採用**。

## 可重用的操作修正

1. **RIGOL PDUT 單位**：本機韌體回傳 `0.5`，與 PWID／PER 約 0.5 一致。測試入口乘 100 成為 50%，另存 `PDUT_raw`；既有驅動的原始回傳契約不變。
2. **釋放後重連會改變 CPU 狀態**：本次重新 connect 後讀到 PC `0x3fc7a5`（Boot ROM）、Timer PRD 65535、PIEIER1 0、InterruptCount 0。不能因此認定先前程式沒有執行。中斷計數必須在同一次下載 session 檢查，或重連後重新下載再檢查。
3. **受限變數讀取**：`ccs-ctl read_var --name CpuTimer0.InterruptCount`／MCP `ccs_run_control(action="read_var", names=[...])` 要求先 halt，只接受變數與點分隔欄位，拒絕賦值、函式與任意 GEL。
4. **CCS CLI 引數**：本機 `ccs-server-cli.bat` 加 `-noSplash` 會印 usage 並結束；移除後成功。見 [CLI 操作](cli-and-scripting.md)。

## 證據與限制

離線回歸 **83 passed、6 deselected**（`-m "not jev and not hw"`）；RIGOL 硬體檢查 **3 passed、86 deselected**（`-m hw`），不是 skip。未執行 Jev API replay。變數讀取限制、週期／觸發判斷、分段區塊與 EOF／尾碼同步、失敗還原與釋放均有離線測試。

受控異常於 `timer_faults_v3_20261013/results.json` 實測完成：觸發準位 5 V 使儀器 WAIT，閘門拒絕，診斷為 `trig_level_out_of_range`；改為 0.2 V/div、offset −1.5 V 製造 BYTE 截斷，閘門回 `clipped=true` 並拒絕。兩者均還原已知 Timer 設定後重新擷取、通過計時與畫面驗收，留存 `restored.png`。

前兩個垂直異常嘗試另存：offset +2 V 時位置檢查已拒絕，但未達 BYTE 飽和；offset +6 V 時單次擷取逾時，因此未宣稱截斷檢查通過。最後改用仍可觸發的窄電壓範圍完成飽和測試。這些暫時設定均在 finally 還原，未更動 IP 或儀器韌體。

本機資料位於 `tools/JEV_accel/results/`：正式批次 `timer_baseline_v2_20261013/`、`timer_optimized_v2_20261013/`，比較摘要 `timer_comparison_20261013.json`，中斷計數 `timer_acceptance_v2/counter.json`，初次通過截圖 `timer_acceptance_v3/0.png`，TCP_NODELAY 資料 `timer_nodelay/results.json`。每筆正式結果含 build／map／load 校驗結果、畫面 metrics、七項讀值、耗時與指令數。

較早 `timer_smoke_baseline`／`timer_acceptance`／`timer_acceptance_v2`／`timer_baseline_20261013` 的失敗保留：分別暴露選單重新開啟、PDUT 單位與邊緣模式條件不適用等問題；未混入正式比較。原始資料與截圖不加入公開 Git。正式批次的 `.out` 修改時間相同，無程式修改；optimized 環境紀錄另有程式 SHA256。

本頁沒有高速邊緣、中斷抖動、Flash 開機或斷電保留測試。RAM 程式斷電即消失。電壓平台的波動原因仍待確認。

收尾驗證：關閉舊 daemon，確保下次啟動載入更新的讀取功能；之後以 RIGOL 新單次擷取再次通過週期閘門與計時量測，證明板上 RAM 程式仍在執行。最後 FREQ 2.5002 Hz、PER 399.97 ms、PDUT 50%、VTOP 2.9619 V、VBASE 0 V；白底截圖與 JSON 在 `timer_final_20261013/`。示波器已回 RUN，`ccs_env` 確認探針 owner=free、daemon 未運行。

最後報告 PNG 又以同一程式的較晚擷取更新：period 閘門通過後送 `:MEAS:CLE ALL`，等 0.8 秒讓畫面更新，再輸出無量測列的圖；它不是前述 `final.json` 的同一次凍結資料。此清畫面等待在正式 5＋5 次比較之外，未追溯加進比較耗時。量測列的用途與清除指令見 [RIGOL Programming Guide 的 `:MEASure:CLEar`](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/MSO5000/MSO5000_ProgrammingGuide_EN.pdf)；不能只因指令回傳成功就認定 UI 已重繪。
