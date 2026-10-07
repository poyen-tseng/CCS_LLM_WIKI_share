# 先用 JEV，再自己看圖或重開除錯器

操作示波器、建置、燒錄、halt、讀 PC 時，先呼叫 JEV。一次呼叫回傳判斷和可以照做的下一步，不必先拍照、搜尋路徑或重讀整份 log。工具在 [JEV_accel](../JEV_accel/README.md)，實測數字在 [JEV_PERFORMANCE.md](../JEV_accel/JEV_PERFORMANCE.md)。

回到 [README.md](README.md)。示波器畫面細節見 [rigol-scope.md](rigol-scope.md)。CCS IDE 的中斷點與變數見 [mcp.md](mcp.md)。daemon 不可用時的腳本見 [cli-and-scripting.md](cli-and-scripting.md)。

Cursor 與 Claude Code 的工具名稱是 `jev-scope`（示波器）和 `jev-ccs`（CCS）。規則先跑。Jev 只在規則沒有明確結論時才問。回傳的 `source`：

| source | 意思 |
| --- | --- |
| `l0` | 規則已有結論，採用規則 |
| `jev` | 規則判斷不了，Jev 的信心夠，採用 Jev |
| `l0_fallback` | 沒有 API key、API 失敗，或信心低於 0.8，退回規則 |

## 示波器

1. 拍報告截圖之前呼叫 `jev_check_frame`。看兩個事件的延遲時加 `view="delay"`。
   - `ready=true`：才截圖，而且只截一次。
   - 否則：照 `next_fix` 送出 `scpi`，或再呼叫一次並設 `apply=true`。不要靠讀 PNG 判斷置中或截斷。
2. 單次觸發沒觸發，或波形是平線：呼叫 `jev_diagnose_capture`，帶上你設的觸發準位和燒錄輸出裡的 PC。只有 `root_cause=wiring` 才請使用者檢查接線。
3. `edge_run.js`、gmake、ccs-debug 的輸出交給 `jev_flash_state`。有量測值時帶上預期範圍（例如 QSEL=2 的延遲約 2e-5～5e-5 s），用來抓沒有重編的舊 build。
4. MOFF 是切換鍵。用 `jev_menu_visible(hide=true)`，它只在選單開著時才按。
5. 新訊號或起點完全不對：`jev_autoframe`。看邊緣用 `mode="edge"`，看延遲用 `mode="delay"` 並給 `delay_s`。

這台 MSO5104 上，`:DISP:DATA?` 的 invert 參數沒有作用，回傳的圖永遠是黑底。報告要白底就在截圖後把影像反相。畫面被截斷時，VTOP／VBASE 是螢幕邊緣，不要拿來自己算 offset；用 `apply=true` 或 `jev_autoframe`。對隱藏通道送量測會把該通道打開。只量已經顯示的通道。

## CCS

1. 先 `ccs_env`。路徑、XDS110、COM、誰佔著探針、daemon 是否已連線都在這一次裡面。不要自己搜尋 gmake、dss.bat、ccstudio。
2. 建置用 `ccs_build`。成功時回傳已含 `.map` 檢查。gmake 說 up to date 但原始碼比上次建置新時，它會標成 `stale_build` 並自動 touch 後再編一次。
3. 燒錄與執行用 `ccs_load`、`ccs_run_control`。session 保持連線時，halt 與讀 PC 低於 0.1 秒。不要為了 halt 或讀 PC 再寫一支 `dss.bat` 或 `run.bat`。
4. 把探針交給 CCS IDE 或其他腳本之前，先 `ccs_release`。daemon 佔著 XDS110 時，`dss.bat` 會印 Error -260；探針還在，那是 `probe_busy`。
5. 子代理中斷，或不確定燒了沒有：讀 `JEV_accel/results/ccs_runs.jsonl` 的最後幾行（時間、程式、PC、成敗、耗時）。
6. 外部 `dss.bat` 的文字交給 `ccs_dss_state`。`edge_run.js` 與量測是否符合預期仍用 `jev_flash_state`。

需要中斷點、呼叫堆疊或變數時，先 `ccs_release`，再照 [mcp.md](mcp.md) 用 `ccs-debug`。

## API key 失效時

由上往下，做到能繼續實驗為止。不要因為沒問到 Jev 就停。

1. 回傳已是 `l0` 或 `l0_fallback`：照 `next_fix` 或 `next_step` 做。燒錄、halt、讀 PC 本來就不呼叫 Jev。
2. 要確定這次不打 API：MCP 設 `jev_mode=off`，CLI 加 `--jev off`。規則仍會跑。
3. 這個工作階段的工具列表沒有 `jev-scope` 或 `jev-ccs`：在 `D:\code\_TI_CCS_no_chinese\JEV_accel` 用該目錄的 `.venv` 執行 `python -m jev_accel <子命令> --jev off`。
4. daemon 起不來，或 `ccs_release` 之後探針仍被佔住：改走 [cli-and-scripting.md](cli-and-scripting.md) 的 `C:\ti\ccs2101\ccs\scripting\run.bat`。不要為了一次 halt 新寫一支 `dss.bat`。

`l0_fallback` 若和實際畫面不符，再看圖，並把該案例補進 `JEV_accel/tests/fixtures/`。不要把 API key 寫進手冊或倉庫。
