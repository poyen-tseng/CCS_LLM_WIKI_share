# 量測證據索引

本目錄保存438份CSV、36張原生PNG及去識別JSON／技術紀錄。檔名中的時間及版本是歷史擷取標記。專案根目錄 [STATUS.md](../STATUS.md) 提供目前解讀；個別歷史結果中的PASS／未測狀態不可直接當成最新結論。

| 目錄 | 用途 |
| --- | --- |
| [evidence](evidence) | 最初五版波形；B1／B2死區、B3／B4 ISR、B5調變 |
| [supplement_20261110_181526](supplement_20261110_181526) | 三通道補測、置中重測及DAC概觀，含原先失敗數據 |
| [paired_20261111_010020](paired_20261111_010020) | 18組PWM／DAC同記錄配對；`records/`有54份原CSV |
| [task4_preview_20261111_0254](task4_preview_20261111_0254) | 單項預覽：最高、最低與總覽，含條件及限制 |
| [task4_zero_aligned_v2](task4_zero_aligned_v2) | 再擷取最高／最低，CH2／CH4同0 V位置與量程 |

## 建議閱讀

1. [18組配對數列](paired_20261111_010020/paired_values.csv)、[方向比較](paired_20261111_010020/direction_comparison.csv)、[配對技術紀錄](paired_20261111_010020/validation_paired.md)。其中CSV來源路徑已去識別，但量測數值保持。
2. [最近端點檢查](task4_zero_aligned_v2/alignment_checks.json)，配合原始CSV和PNG。
3. [第一輪預覽說明](task4_preview_20261111_0254/result_summary.txt)，了解慢時基總覽與短時基duty量測的差別。
4. [歷史補測說明](supplement_20261110_181526/validation_supplement.md)，必要時再查完整舊數列。

JSON內的`evidence/...`路徑以`projects/PWM_HW/`為根。CSV可能保留Windows風格相對分隔符；使用其他平台讀取時需正規化。部分歷史紀錄引用的私人腳本／建置記錄未公開，不能將那些引用當成有效下載連結。設定／gate是歷史取景紀錄，不代表本次重新操作過儀器。
