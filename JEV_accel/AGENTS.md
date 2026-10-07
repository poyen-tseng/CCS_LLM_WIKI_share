# 給 Agent 的規則：操作 MSO5104 與 F280049C 時先問 jev-scope，操作 CCS 時先問 jev-ccs

`jev-scope`／`jev-ccs` MCP（或 `python -m jev_accel ...`）會先用規則判斷，判斷不了時再問 Jev。一次呼叫就能拿到「判斷結果＋可直接送出的 SCPI、燒錄步驟或下一步」。照下面的順序使用，可以避免以前反覆拍照、看圖、搜尋路徑、重讀 log 的回合。

1. **拍報告截圖之前**，先呼叫 `jev_check_frame`（看兩個事件的延遲時加 `view="delay"`）。
   - `ready=true`：才呼叫 `scope_screenshot`，而且只拍一次。
   - 否則：照 `next_fix` 送出 `scpi`（或用 `apply=true`），再呼叫一次 `jev_check_frame`。不要靠讀 PNG 來判斷置中或截斷。
2. **單次觸發沒觸發、或波形是平線時**，先呼叫 `jev_diagnose_capture`，帶上你設定的觸發準位和燒錄輸出裡的 PC。
   - 只有回傳 `root_cause=wiring` 時，才請使用者檢查接線。
3. **燒錄、gmake、ccs-debug 之後**，把終端機輸出交給 `jev_flash_state`，不要反覆讀檔。
   - 有量測值時，帶上預期範圍（例如 QSEL=2 的延遲應在 2e-5～5e-5 s），可以抓到 gmake 沒重新編譯的舊 build。
   - `ccs-debug` 逾時兩次，就照 `fallback_dss` 改用 `run.bat edge_run.js`。
4. **MOFF 是切換鍵，不要盲按。** 用 `jev_menu_visible(hide=true)`，它只在選單開著時才按。
5. **新訊號、或還不知道該用什麼設定時**，先用 `jev_autoframe`：
   - 看邊緣：`mode="edge"`。
   - 看延遲：`mode="delay", delay_s=...`。
6. 回傳中有 `source`，代表答案來自哪一層：
   - `l0`：規則判斷。
   - `jev`：Jev 判斷。
   - `l0_fallback`：Jev 信心不足或無法使用，退回規則。

   如果是 `l0_fallback`，而且結果看起來和實際畫面不符，再自行看圖判斷，並把那個案例補進 `tests/fixtures/`。

修改規則或門檻之後，請執行 `.\.venv\Scripts\python.exe -m pytest -m "not jev and not hw"`，確認所有 fixture 仍然通過。

示波器連不上時（逾時、ARP 是 00-00-…），先請使用者照 [SCOPE_IP_SETUP.md](SCOPE_IP_SETUP.md) 檢查，不要自己掃描網段。

量測時注意：對**隱藏的通道**送 `:MEAS:ITEM? ...,CHANn`，RIGOL 會把那個通道打開。兩個通道同時開著時，每個通道的記憶體深度會減半（實測從 80k 變成 20k）。只量已經顯示的通道；量完後如果要還原，送 `:CHANn:DISP 0`。

硬體實測（2026-10-07）得到的規則：
- `jev_check_frame` 回傳 `hint`（畫面被截斷）時，不要自己算 offset，直接用 `apply=true` 或 `jev_autoframe` 重新取景。截斷時量到的 VTOP/VBASE 是螢幕邊緣，用它們算出來的數值會讓畫面更糟。
- 起點設定完全不對時（探棒倍率錯、時基錯），直接呼叫 `jev_autoframe`。它會依序：先改探棒倍率 → 粗調 → 細調。
- 白底截圖：這台示波器的 `:DISP:DATA?` invert 參數沒有作用，回傳的永遠是黑底。要白底就在截圖後把影像反相（例如 PIL `ImageOps.invert`）。
- 報告截圖前先 `:MEAS:CLE ALL`，再加回需要的量測項目。本工具的量測查詢會在畫面下方留下量測列。

## 操作 CCS／F280049C 時先問 jev-ccs

1. **先呼叫 `ccs_env`。** 路徑、XDS110、COM 埠、誰佔著探針、daemon 是否已連線，都在這一次裡面。不要自己 `Get-ChildItem` 找 gmake、dss.bat、ccstudio。
2. **建置用 `ccs_build`。** 不要手動 gmake 再對 `.map` 跑三次 `Select-String`。成功時回傳已含 `ccs_map_check`。gmake 說 up to date 但原始碼比上次建置新時，它會標成 `stale_build` 並自動 touch 後再編一次。
3. **燒錄與執行用 `ccs_load`、`ccs_run_control`。** 不要為了 halt 或讀 PC 再寫一支 `dss.bat`／`run.bat`。session 保持暖機時，halt 與讀 PC 低於 0.1 s。
4. **把探針交給別的工具或 CCS IDE 之前，先 `ccs_release`。** daemon 佔著 XDS110 時，`dss.bat` 會印 Error -260；那是 `probe_busy`，探針還在。
5. **子代理中斷或你不確定燒了沒有時，讀 `results/ccs_runs.jsonl` 的最後幾行**（時間、程式、PC、成敗、耗時）。不要翻整份 transcript 和 terminals。
6. **外部 `dss.bat` 的輸出交給 `ccs_dss_state`，** 和示波器流程裡的 `jev_flash_state` 分開：前者看 DSS／scripting 文字，後者看 `edge_run.js` 與量測是否符合預期。

