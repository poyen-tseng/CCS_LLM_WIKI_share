# PWM 補測驗證完成

更新：2026-11-10T19:30:27+08:00。同 run `F280049C_5_PWM_3_HW_20261110_150311`。

**本次補測 A1–A11、A14 全部 PASS（12項）；A12、A13 保留先前通過證據。整體14 PASS／0 FAIL／0待補。**

原 spec v1.0 SHA-256 重算相符；GPIO2 三通道補測增補 v1.1 已由使用者核准（詳 addendum_approval.json），不變更PWM、死區、中斷頻率或允差。CCS兩個新版本 clean build 0錯誤0警告，RAM map、load/verify/run及板上讀回均成功；詳ccs補測handoff。

## 實際通道與倍率證據

| 通道 | 測點（排針編號） | 本次訊號核對 |
| --- | --- | --- |
| CH1 橘 | 79，GPIO1／封裝78 | 200kHz、OutB高3.70us；原part5則為62.5Hz方向標記 |
| CH2 青 | 80，GPIO0／封裝79 | 200kHz、OutA高0.70us |
| CH3 紫 | 76，GPIO2_BP／封裝77 | 原程式未驅動時平坦；新程式ISR第一個C敘述toggle後25kHz／每20us翻轉、名義0/3.3V |
| CH4 綠 | 70，ADCINA0-DACOUTA／封裝23 | 原part5完整三角波、16ms週期；是示波器實測，不是內部ADC |

TI C2000Ware_5_00_00_00/boards/.meta/LAUNCHXL_F280049C.syscfg.json第156/163/166/167行確認排針映射。76不是GPIO76。通道位置由特定韌體輸出波形交叉確認；探棒開關、地夾及板面修訂版未重新目視確認。四通道軟體皆10×、DC、BW limit off、反相off；CH3在10×設定下量得正常3.3V邏輯、CH4量得正常DAC範圍，支持10×實體衰減。這是倍率辨識，並非校正到3.300V的電壓標準。

## 三通道補測結果

| 要求 | 理論／允差 | 本次實測 | 判定 |
| --- | --- | --- | --- |
| A1 | PWM 200kHz ±1% | 199.9926–200.0767 kHz | PASS |
| A2 | OutA 700ns ±30ns | 699.8305–700.3958 ns | PASS |
| A3 | OutB 3700ns ±30ns | 3700.8049–3704.3017 ns | PASS |
| A4 | 死區前脈寬1000ns ±30ns | 998.3438–998.8333 ns | PASS |
| A5 | 兩側死區300ns ±30ns | 298.3438–300.8210 ns | PASS |
| A6 | High≥3.0V、Low≤0.3V | 置中1V/div重測兩模式各6筆均符合；原堆疊量程CH1部分低準位0.32V（未通過），原資料與初判保留 | PASS |
| A7 | 每GPIO半週期4個PWM脈波 | 兩模式、所有完整半週期均4個；OutA/OutB同時擷取 | PASS |
| A8 | ISR GPIO 25kHz ±1%；高低各20us ±1% | 24.9999–25.0042 kHz；19.9764–20.0193 us | PASS |
| A9 | 同模式同邊緣≥5筆，Δ spread≤50ns | 每組6筆，最大spread 1.314ns | PASS |
| A10 | UpDown−Up，GPIO相對OutA↑差450–550ns | 499.4483–500.2909 ns | PASS |
| A11 | 兩模式Δ差≤50ns | -0.5701–0.4884 ns | PASS |

## 中斷與計數點關係

每次CSV同時含OutA、OutB、ISR GPIO2，避免以拆分build替代同時觀察。Up-Count以OutB下降緣為CTR=0；Up-Down以OutB下降緣+500ns為CTR=0，再由OutA下降緣−500ns交叉確認。Δ包含PIE與編譯器ISR暫存器保存時間；GPIO邊緣不是硬體中斷發生瞬間。

| 模式 | GPIO邊緣 | Δ平均 | GPIO相對OutA上升緣 | Δ max−min |
| --- | --- | --- | --- | --- |
| up_count | rise | 268.595ns | -29.855ns | 1.249ns |
| up_count | fall | 249.228ns | -49.247ns | 1.053ns |
| up_down | rise | 269.084ns | 470.435ns | 1.314ns |
| up_down | fall | 248.657ns | 450.201ns | 1.070ns |

結論：兩模式GPIO標記相對OutA↑相差約500ns，但換算到CTR=0後Δ近似相同；Up-Count中斷點在死區前脈波起點，Up-Down在脈波中心。rise/fall約20ns差異也存在，未改程式追究，未超過核准標準。

## A14 DAC（三角波）

原part5 code409↔3685，理論0.33↔2.97V、62.5Hz，允差±0.1V及±1%。六筆CH4原始CSV皆量得0.36↔3.04V（誤差+0.03/+0.07V）；頻率62.3199–62.8387Hz（平均62.5460Hz，誤差−0.288%～+0.542%），PASS。DAC方向標記與三角波也已同時擷取。

5ms/div、2500點、20us/點、CH4 1V/div；頻率以1.65V交越線性內插，低於1.4V後才重新允許下一次上升，避免慢斜坡量化雜訊在下降段形成假上升。電壓使用原始資料極值，未平滑或改動CSV。初版無遲滯的分析會誤計噪聲交越，已修正分析器；不是韌體／儀器改動。

## 圖片、CSV與設定

每張正式PNG前jev_check_frame回報ready=true，逐張gate JSON留存；每一視圖只擷取一次原生白底PNG，同凍結記錄保存CSV與設定。兩模式V3為5us/div、20ns/點；V4 rise/fall各250ns/div、1ns/點，每組6次單序列CSV，全部STOP。三通道圖上方CH2 OutA 2V/div、中間CH3 ISR 1V/div、下方CH1 OutB 2V/div，皆不截斷。

| 圖檔 | 對應 |
| --- | --- |
| A14_V5c_DAC.png | A14 DAC／方向標記 |
| A14_V5c_DAC_marker.png | A14 DAC／方向標記 |
| up_count_A6_centered.png | A6 置中準位重測，三通道各1V/div |
| up_count_V3_overview.png | A1–A11；概觀／每4事件 |
| up_count_V4_fall.png | A1–A11；ISR延遲與死區 |
| up_count_V4_rise.png | A1–A11；ISR延遲與死區 |
| up_down_A6_centered.png | A6 置中準位重測，三通道各1V/div |
| up_down_V3_overview.png | A1–A11；概觀／每4事件 |
| up_down_V4_fall.png | A1–A11；ISR延遲與死區 |
| up_down_V4_rise.png | A1–A11；ISR延遲與死區 |

新增正式PNG 10張，原始waveform CSV 177份；所有檔案絕對路徑與雜湊見evidence_supplement.json。

## 保留與限制

- A12、A13沿用原part5先前實測，未再重做18個duty點；A14此次由CH4直接補測，內部ADC仍只作參考。
- 原5版.out、4份實作原始碼與舊證據雜湊／大小核對未變；舊報告與原模板未改。
- 未重新目視探棒檔位、地夾、板面型號標示；接線與倍率由已知韌體特徵及幅度推定。此任務未執行探棒頻率補償校正。
- 儀器原生固定右側功能列仍可見，未覆蓋波形區；menu checker回報hide_supported=false。保留原始320×240圖片，沒有合成波形或修改像素。
- scope螢幕時間約慢5分鐘，設定與acquisitions JSON採PC時間。
- 曾因短程序尚未完成時嘗試開另一USB連線而失敗；未重複擷取正式PNG，改為等待前一程序完成後串行操作。曾以不支援的VTOP/VBASE原生字串查詢被拒，最終準位採CSV平台中位數。
- A6原堆疊2V/div、CH1位置−3.58div量得部分低準位0.32V，初判FAIL；不更改0.3V門檻，僅以置中1V/div提高解析度後重測，每模式6筆。原CSV及supplement_results_initial_stacked.json全部保留，新的判定詳A6。
- 最終板上留補測up_count版本持續執行；A6重測換版後已ccs_release(shutdown=true)，最後ccs_env確認owner=free、daemon_alive=false。
- 此次未改USB驅動；關閉本任務前後回合持有USB的tek MCP程序，之後以既有tek.py短程序與jev-scope串行操作。

## 下一節點

硬體補測完成，可交PPT更新。請由Workflow建立者依序交接PPT與新的中立評審；本agent未聯絡PPT／評審。舊PPT尚未更新，不能稱為新版完成報告。
