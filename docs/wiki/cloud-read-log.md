# 雲端資料夾已讀紀錄

來源根目錄：`G:\我的雲端硬碟\@研究所\數位控制設計-楊`

下次打開這個資料夾時，先讀本頁，再只處理「相對路徑不在下表」或「sha256 與下表不同」的檔。mtime 會因雲端同步變動，不用來判斷內容是否沒變。規則也寫在 [README.md](README.md)。

status 意義：

| status | 意義 |
| --- | --- |
| `summarized` | 已把開發用得到的內容寫進 wiki。sha256 不變就不要重讀。 |
| `catalogued` | 知道檔案在，沒有把全文送進上下文。使用者沒點名要查這份之前，不要打開。 |
| `skipped-duplicate` | 與已讀檔或工作區專案重複。不要再打開。`GPIO_EX1/` 的 sha256 是該樹每個檔的路徑、內容 sha256、大小組成的清單再雜湊。 |
| `skipped-privacy` | 名單。不要打開、不要抄姓名。 |

登記日期：2026-09-22。摘要所根據的文字抽取已刪除，wiki 裡不保留講義全文。

## summarized

| 相對路徑 | bytes | mtime (UTC) | sha256 | 寫進 |
| --- | --- | --- | --- | --- |
| `0_Introduction to design of digital control_lecture.pdf` | 2254060 | 2026-09-08T05:02:47Z | `01f895bbf09a1de91de3d8066224e6e8e21e3a0b56d95ea87b05074677fdc6f3` | course-notes.md |
| `1_CCS software installation and sample project_lecture.pdf` | 1366484 | 2026-09-15T05:41:17Z | `5135b476d2067c7a5f458488c18757b6591ab482aa18b3d8e6e5920f15b4b30d` | course-notes.md |
| `1_LAUNCHXL-F280049C_lecture.pdf` | 5455191 | 2026-09-15T07:32:44Z | `7012171ccf3e10b97a82deb3e3e33d98149e4a91f2b55152718693e252567c44` | course-notes.md |
| `1_OSC_lecture.pdf` | 3599645 | 2026-09-15T08:17:17Z | `36fa5fe9fc9834470abafab3be9b5f781d50ad96c2b31ab0707a820528b06544` | course-notes.md |
| `2_GPIO_lecture.pdf` | 2617689 | 2026-09-22T02:12:48Z | `a51c7bfd478c74c83d0f30ff1b3c24620ecdb8c444e15e28fa2139038db037ba` | course-notes.md |
| `TMS320F280049C_開發板使用說明.pdf` | 4350097 | 2020-11-03T13:22:18Z | `aa84918388ed32a15e0dcbf036d7e6c56bd6f9f7aa8e0be3fcee98697cab3193` | course-notes.md |
| `TMS320F280049C_精簡版.pdf` | 4232923 | 2020-11-13T08:30:46Z | `94066322ab5744e417b8c809250049098388678339a80d07ad4d6fadfd8066ab` | device-f280049c.md（SPRS945E） |
| `TMS320F280049C_詳細版.pdf` | 39047746 | 2020-11-13T08:36:12Z | `6cdc7eeac58023c275d14feeee2b020ac5f8821e142222b11188ed24667b4b10` | device-f280049c.md（SPRUI33D，只整理章節，未貼全文） |
| `TMS320F280049C_開發板電路圖.pdf` | 712223 | 2022-03-19T05:31:56Z | `92fe838f7068526f79fd5e6c884727f457c3571a430198c342c2f14ecae8c4da` | board-pins.md |
| `TMS320F280049C_開發板_LaunchPad接腳說明卡.pdf` | 35315745 | 2022-03-19T05:30:16Z | `a616bdc41419232610029aa3e86b2aca009b0de654dbad4a8a795ce32006b7ea` | board-pins.md（3 頁，接腳是圖，無文字層） |
| `附件_簡報範例.pptx` | 979026 | 2026-09-22T02:12:48Z | `626094133619bf95e681fb3ccda0ae1ce663f213737592158e9a7e07eb5e6bef` | board-pins.md 報告版型 |

## catalogued

| 相對路徑 | bytes | mtime (UTC) | sha256 | 備註 |
| --- | --- | --- | --- | --- |
| `軟體安裝檔案/CCS_21.0.1.00010_win.zip` | 1558380796 | 2026-09-15T06:16:36Z | `60eda4760af6d867d40a13a9b4177d2da2d8054066025f276e5d417ff5930f9b` | 安裝檔，本機已裝在 `C:\ti\ccs2101` |

## skipped-duplicate

| 相對路徑 | bytes | mtime (UTC) | sha256 | 備註 |
| --- | --- | --- | --- | --- |
| `GPIO_EX1/` | 3305901 | 2026-09-19T09:56:21Z | `01772daf895f2a97d7536f93f01de1299b74edc03af180fa448e971ff4838fe2` | 74 個檔。清單雜湊。改工作區那份，不要重讀。 |
| `20250915上課教材.rar` | 76449242 | 2026-09-15T05:25:50Z | `60f781062a1504cc211c323960d0faace444ba59e0c9594b64564c54fd96f6d4` | 未解壓。清單是較舊的同一批講義、datasheet、使用說明、電路圖、接腳卡、分組名單，以及一份 `GPIO_EX1`。內容與資料夾裡已讀的檔重複。 |

## skipped-privacy

| 相對路徑 | bytes | mtime (UTC) | sha256 | 備註 |
| --- | --- | --- | --- | --- |
| `分組名單.pdf` | 270009 | 2026-09-14T13:27:27Z | `5ec175077d937c8a665fe3997cbb706b7b5eef38218f30e97e3fa58fb610cfb1` | 未開啟 |
