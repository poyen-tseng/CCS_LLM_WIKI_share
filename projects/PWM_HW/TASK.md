# PWM 實驗技術摘要

來源為本機 PWM 作業的已實作設定與歷史量測紀錄。原講義不公開；本文件摘要工程行為，不代表完整轉錄講義或獨立符合性認證。

## 平台與版本

LAUNCHXL-F280049C／TMS320F280049C，SYSCLK 與 TBCLK 設定 100 MHz，RAM 連結。ePWM1 的目標週期 5 µs（200 kHz），DBRED／DBFED 各 30 個 TBCLK（300 ns）。原專案以 `HW_PART` 選擇：

| HW_PART | 計數模式 | GPIO0／接頭80 | GPIO1／接頭79 | DAC |
| --- | --- | --- | --- | --- |
| 1 | Up-Count | OutA | OutB | 關閉 |
| 2 | Up-Down | OutA | OutB | 關閉 |
| 3 | Up-Count | OutA | ISR 翻轉標記 | 關閉 |
| 4 | Up-Down | OutA | ISR 翻轉標記 | 關閉 |
| 5 | Up-Count | OutA，指令10→90→10% | 上升段 High／下降段 Low 標記 | DACOUTA |

兩個 `PWM_3CH_*` 補測專案為另存版本，固定 OutA／OutB，並在 GPIO2／接頭76輸出 ISR 翻轉標記；不啟用 DAC。其原始碼和主專案分開保留。

## 接線定義

| 示波器 | 接頭位置（課程 pin map） | 訊號 |
| --- | --- | --- |
| CH1 | 79，GPIO1 | 依版本為 OutB、ISR 或方向標記 |
| CH2 | 80，GPIO0 | EPWM1A／OutA |
| CH3 | 76，GPIO2 | 三通道補測版的 ISR 標記 |
| CH4 | 70，DACOUTA | 原 HW_PART 5 的類比輸出 |

這些數字是開發板接頭位置，並非晶片封裝腳號。歷史通道對應主要由程式及波形核對；未重新目視探棒開關、地夾、補償及供電。腳位背景見 [板子接腳 Wiki](../../docs/wiki/board-pins.md)。

## 計算與解讀

- Up-Count：`TBPRD=499`，`f=100 MHz/(499+1)=200 kHz`，固定 `CMPA=100`。
- Up-Down：`TBPRD=250`，`f=100 MHz/(2×250)=200 kHz`，固定 `CMPA=50`。
- 固定 20% 指死區前 AQ 波形。OutA 高脈寬理論約 1.0−0.3=0.7 µs，腳位 duty 約14%；OutB 高脈寬約3.7 µs。不能把腳位 OutA 說成20%。
- 每4個 CTR=0 事件觸發一次 ISR，約50 k次/s。GPIO 每次 ISR 翻轉，故方波25 kHz，半週期20 µs。GPIO 標記在軟體指令執行時才改變，包含進入中斷後的軟體延遲，不能直接當成真正 ISR 入口。
- HW_PART 5：CMPA 在50～450間每次 ISR 改1；800次 ISR 為一輪，約16 ms／62.5 Hz。`DAC code=floor(CMPA×4095/500)`。DAC 使用內部參考與 ×2 gain 設定，名義電壓約0.33～2.97 V。
- CMPA 使用 shadow、CTR=0 載入；DAC 使用另一條更新路徑。共同調變量及取樣正向關聯不等同兩個輸出每瞬間完全一致或零延遲。

## 驗證界線

建置、暫存器讀回、內部 ADC 與外部示波器為不同證據。內部 ADC 回讀不能代替完整外部 DAC 波形。18組配對只支持取點的正向關聯；方向等效、真正 ISR 入口、絕對電壓精度與更新延遲未完成獨立驗證。沒有新增允差來把這些問題判成 PASS。
