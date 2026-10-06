# CCS LLM Wiki

給之後的 LLM 用的操作手冊。寫 C2000 程式、編譯、除錯時先看這裡，不要反組譯 CCS。

本機環境（2026-09-22 以官方 MCP 讀到）：

- CCS 21.0.1，安裝在 `C:\ti\ccs2101`
- 工作區專案 [`GPIO_EX1`](D:\code\_TI_CCS_no_chinese\GPIO_EX1)
- 裝置 TMS320F280049C（C28xx_CPU1）
- 除錯器 Texas Instruments XDS110 USB Debug Probe
- 編譯器 TI v25.11.1.LTS，作用中組態 Debug
- 這個專案沒有 `.syscfg`

## 頁面

| 頁 | 何時讀 |
| --- | --- |
| [entry-points.md](entry-points.md) | 要找執行檔、CLI、腳本、編譯器路徑 |
| [mcp.md](mcp.md) | 人在 Cursor 裡、CCS 已開著，要用 MCP 建置或除錯 |
| [cli-and-scripting.md](cli-and-scripting.md) | 不開 GUI、或要寫重複的下載／燒錄腳本 |
| [course-notes.md](course-notes.md) | 課程講義裡跟安裝、板子、GPIO、時脈有關的操作 |
| [device-f280049c.md](device-f280049c.md) | 記憶體位址、周邊數量、時脈、TRM 章節 |
| [references.md](references.md) | 官網文件、本機 C2000Ware 路徑、DCL、勘誤、有沒有現成 skill |
| [board-pins.md](board-pins.md) | LaunchPad 電路網路、LED、開機、UART、CAN |
| [boundaries.md](boundaries.md) | 想拆 CCS 執行檔或 DLL 之前 |
| [cloud-read-log.md](cloud-read-log.md) | 要讀雲端課程資料夾之前 |

## 雲端課程資料夾

路徑：`G:\我的雲端硬碟\@研究所\數位控制設計-楊`

這個資料夾會繼續新增檔案。下次要讀它時：

1. 先讀 [cloud-read-log.md](cloud-read-log.md)，不要把已登記的檔再送進上下文。
2. 列出資料夾（含子目錄）。相對路徑不在紀錄裡，或檔案 sha256 與紀錄不同，才處理。
3. 講義、簡報、短篇說明：摘要進 [course-notes.md](course-notes.md)，紀錄改為 `summarized`。
4. 大型手冊（datasheet、TRM、電路圖、接腳卡）：不要把全文貼進 wiki。只抽開發用得到的章節、數量與腳位，寫進對應頁，status 用 `summarized`，備註寫明沒貼全文。與已讀檔重複的壓縮檔標 `skipped-duplicate`，不要解壓。安裝檔標 `catalogued`。
5. 名單、成績、個資：`skipped-privacy`，不抄內容。
6. 與工作區 `GPIO_EX1` 相同的專案樹：`skipped-duplicate`，改工作區那份即可。
7. 處理完立刻更新紀錄的位元組數、mtime、sha256、status、寫進哪一頁、日期。

比對用 sha256，不要只看檔名。Google 雲端硬碟的 mtime 可能因同步改變，mtime 只作參考。
