# PWM_HW：F280049C PWM 與 DAC 實驗（report3）

本目錄是 2026-11-10～11 的 report3 開發與量測資料之公開副本，整理於 2026-11-12。包含三個可匯入的 CCS 專案、實驗技術摘要、438 份 CSV、36 張原生示波器截圖，以及去識別的設定與分析紀錄。原始私人專案保留在本機；本次沒有重新建置、燒錄或量測。

| 入口 | 內容 |
| --- | --- |
| [TASK.md](TASK.md) | 實驗範圍、版本、接線與計算定義 |
| [STATUS.md](STATUS.md) | 歷史驗證結果、最新任務4預覽與尚未確認事項 |
| [BUILD.md](BUILD.md) | CCS 匯入、C2000Ware 路徑與版本切換 |
| [evidence/README.md](evidence/README.md) | 原始波形、配對資料與歷史結果的閱讀順序 |
| [PRIVACY.md](PRIVACY.md) | 公開範圍、去識別方式與驗證界線 |
| [PUBLICATION_MANIFEST.json](PUBLICATION_MANIFEST.json) | 公開檔案與來源 SHA-256 對照 |

## 程式

- [firmware/PWM_HW](firmware/PWM_HW)：原五種實驗版本；`Init.h` 的 `HW_PART=1…5` 選擇。
- [firmware/PWM_3CH_up_count](firmware/PWM_3CH_up_count)：補測用 Up-Count，OutA／OutB／GPIO2 ISR 標記可同時觀測。
- [firmware/PWM_3CH_up_down](firmware/PWM_3CH_up_down)：補測用 Up-Down，同樣保留獨立 GPIO2 標記。

## 任務4代表圖

以下是歷史實測與待確認預覽，並非已核准 PPT。CH2 青色為 OutA，CH4 綠色為 DACOUTA。兩張端點圖使用相同 0 V 位置與 1 V/div；總覽為較早一輪的原生擷取。

| 最高端點 | 最低端點 | DAC 總覽 |
| --- | --- | --- |
| ![最高端點](evidence/task4_zero_aligned_v2/maximum.png) | ![最低端點](evidence/task4_zero_aligned_v2/minimum.png) | ![DAC總覽](evidence/task4_preview_20261111_0254/overview.png) |

端點的腳位實測 duty 約 84.01%／4.01%；10%→90%→10% 是死區前指令。保留 300 ns 死區後，OutA 高準位約減少 6 個百分點。不可把推算的死區前 duty 寫成另一個實測腳位值。完整條件與限制見 [STATUS.md](STATUS.md)。

本次公開不包含 PPT／PDF、課程講義、報告範本、聊天、審查交接、被否決稿、編譯產物、私人路徑或帳號。TI 支援程式的原授權及版權聲明保留。
