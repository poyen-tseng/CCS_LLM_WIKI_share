# GPIO 實驗：輸入採樣與輸出控制

本文件只記錄 `2_GPIO_lecture.pdf` 第 30–36 頁的實驗操作。下一個 coding agent 依這裡的程式、腳位與量測現象操作。

不開啟、不修改任何既有 CCS 專案。講義上的 `GPIO_EX1/...` 只是投影片標註的路徑，不是磁碟上的工作指示。

## 範圍

- 來源：`2_GPIO_lecture.pdf` 第 30–36 頁，標題 *LAB Experiment - GPIO input sample and output control*。
- 裝置：TMS320F280049C。Pin map 標題為 LAUNCHXL-F280049C。
- 第 29 頁的 rise/fall 不超過 8 ns，只用來對照 Example 1 手寫的「8 ns」，不是另外一個實驗步驟。
- 第 1–28 頁暫存器講義不在操作步驟裡。
- 第 29 頁表格上的 GPIO 切換頻率上限 25 MHz 不是本實驗步驟。實驗沒有做 25 MHz 翻轉。
- 講義沒寫的儀器型號、觸發方式、外部信號源，維持未指定。不要自行補上。

## 實驗目標（第 30 頁）

設定 OSC 暫存器與 GPIO 暫存器，採樣並控制 GPIO 狀態。

1. 將 GPIO0 輸出高準位。確認上升時間與電壓值。
2. 將 GPIO0 設為輸入，使用 qualification 模組讀取 GPIO0，並改變 GPIO6 的輸出狀態。

時脈：兩個範例都只呼叫 `InitSysCtrl()`。投影片沒有另外手寫 OSC 或 PLL 暫存器。不要補時脈初始化程式。

## 腳位

| 信號    | 晶片腳    | 開發板               | Pin map 標示    |
| ----- | ------ | ----------------- | ------------- |
| GPIO0 | Pin 80 | header J8，腳位編號 80 | PWM1A / GPIO0 |
| GPIO6 | Pin 78 | header J8，腳位編號 78 | PWM4A / GPIO6 |

第 32 頁紅字填空只寫了 GPIO0：*GPIO0 is connected to the J8 header on the development board. The pin number is 80.* GPIO6 的 J8 / 78 來自第 30 頁的 Pin 78，以及第 32 頁同一張 pin map 的 J8 欄。

## Example 1：GPIO0 輸出高準位

第 31 頁標題寫：*Set GPIO0 to output function with high/low level to measure the voltage value and switching time.*

實際給出的程式只把 GPIO0 拉高，然後空轉。第 33 頁只示範高準位直流與上升時間。要做的就是這支程式與這兩張波形。不要另做低準位輸出，也不要另量下降時間。

投影片路徑：

- `GPIO_EX1/main.c` 的 `main`
- `GPIO_EX1/Init.c` 的 `Init_GPIO`

### main

```c
void main(void)
{
    InitSysCtrl();
    Init_GPIO();

    while(1)
    {
    }
}
```

### Init_GPIO

```c
void Init_GPIO(void)
{
    // 初始化GPIO
    InitGpio();
    EALLOW;
    // 關閉所有GPIO內部上拉，減少功率損耗
    GpioCtrlRegs.GPAPUD.all = 0xFFFFFFFF;
    // 設定GPIO0
    // 使GPIO0腳位為輸出。
    GpioCtrlRegs.GPADIR.bit.GPIO0 = 1;
    // 選擇GPIO0腳位的功能。GPAGMUX1:GPAMUX1 = 00:00 => GPIO0為GPIO功能。
    GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 0;
    GpioCtrlRegs.GPAGMUX1.bit.GPIO0 = 0;
    // 關閉GPIO0的Pull-up電阻。
    GpioCtrlRegs.GPAPUD.bit.GPIO0 = 1;
    // 將GPIO0交由CPU控制。(除了CPU可以控制GPIO以外，浮點數處理核心CLA也可以控制GPIO)
    GpioCtrlRegs.GPACSEL1.bit.GPIO0 = 0;
    // 使GPIO0輸出高準位
    GpioDataRegs.GPASET.bit.GPIO0 = 1;
    EDIS;
}
```

暫存器設定：

- `InitGpio()`，然後 `EALLOW`
- `GpioCtrlRegs.GPAPUD.all = 0xFFFFFFFF`：關閉 GPIOA 內部上拉
- `GPADIR.bit.GPIO0 = 1`：輸出
- `GPAMUX1.bit.GPIO0 = 0`，`GPAGMUX1.bit.GPIO0 = 0`：GPIO 功能
- `GPAPUD.bit.GPIO0 = 1`：關閉該腳上拉
- `GPACSEL1.bit.GPIO0 = 0`：CPU 控制
- `GpioDataRegs.GPASET.bit.GPIO0 = 1`：輸出高準位
- `EDIS`

### 量測（第 32–33 頁）

探棒接 J8 pin 80（GPIO0）。

- 高準位：穩態直流高。例圖時間軸約 5.00 μs/div，電壓軸 1.00 V/div。投影片沒有標出量到的電壓數字。
- 上升時間：單次由低到高，手寫 **8 ns**。例圖 20.00 ns/div、1.00 V/div。第 29 頁規格為 rise 與 fall 不超過 8 ns（GPIO23_VSW 除外；數值假設 40 pF 負載）。

程式把 GPIO0 拉高後就停在空的 `while(1)`。上升緣只在這支程式開始把腳位拉高時出現。講義沒有寫觸發方式，也沒有寫要按 Reset。這兩項維持未指定。不要把程式改成連續翻轉來製造上升緣。

## Example 2：GPIO0 輸入，GPIO6 反相輸出

第 34 頁沒有另外的檔案路徑。它是把 `Init_GPIO` 與 `main` 改寫。不要假設第二個專案名稱。

此頁程式對應第 36 頁：`GPyQSEL = 2`，`GPyCTRL = 255`。

### Init_GPIO

```c
void Init_GPIO(void)
{
    // 初始化GPIO
    InitGpio();
    EALLOW;
    // 關閉所有GPIO內部上拉，減少功率損耗
    GpioCtrlRegs.GPAPUD.all = 0xFFFFFFFF;
    // 設定GPIO0
    // 使GPIO0腳位為輸入。
    GpioCtrlRegs.GPADIR.bit.GPIO0 = 0;
    // 選擇GPIO0腳位的功能。GPAGMUX1:GPAMUX1 = 00:00 => GPIO0為GPIO功能。
    GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 0;
    GpioCtrlRegs.GPAGMUX1.bit.GPIO0 = 0;
    // 關閉GPIO0的Pull-up電阻。
    GpioCtrlRegs.GPAPUD.bit.GPIO0 = 1;
    // 關閉GPIO0輸入反相功能。
    GpioCtrlRegs.GPAINV.bit.GPIO0 = 0;
    // 調整GPIO0採樣頻率
    GpioCtrlRegs.GPACTRL.bit.QUALPRD0 = 255;
    // 調整GPIO0的採樣窗格
    GpioCtrlRegs.GPAQSEL1.bit.GPIO0 = 2;

    // 設定GPIO6
    // 使GPIO6腳位為輸出。
    GpioCtrlRegs.GPADIR.bit.GPIO6 = 1;
    // 選擇GPIO6腳位的功能。GPAGMUX1:GPAMUX1 = 00:00 => GPIO6為GPIO功能。
    GpioCtrlRegs.GPAMUX1.bit.GPIO6 = 0;
    GpioCtrlRegs.GPAGMUX1.bit.GPIO6 = 0;
    // 關閉GPIO6的Pull-up電阻。
    GpioCtrlRegs.GPAPUD.bit.GPIO6 = 1;
    // 將GPIO6交由CPU控制。(除了CPU可以控制GPIO以外，浮點數處理核心CLA也可以控制GPIO)
    GpioCtrlRegs.GPACSEL1.bit.GPIO6 = 0;
    // 使GPIO6輸出高準位
    GpioDataRegs.GPASET.bit.GPIO6 = 1;
    EDIS;
}
```

GPIO0 是輸入。此頁沒有設定 GPIO0 的 `GPACSEL1`。

GPIO6 暫存器：

- `GPADIR.bit.GPIO6 = 1`：輸出
- `GPAMUX1.bit.GPIO6 = 0`，`GPAGMUX1.bit.GPIO6 = 0`：GPIO 功能
- `GPAPUD.bit.GPIO6 = 1`：關閉該腳上拉
- `GPACSEL1.bit.GPIO6 = 0`：CPU 控制
- `GpioDataRegs.GPASET.bit.GPIO6 = 1`：一開始輸出高準位

### main

```c
void main(void)
{
    InitSysCtrl();
    Init_GPIO();

    while(1)
    {
        // 功能：當GPIO0採樣為低態(0V)時，GPIO6輸出高態(3.3v)
        if (GpioDataRegs.GPADAT.bit.GPIO0 == 0)
        {
            GpioDataRegs.GPASET.bit.GPIO6 = 1;
        }
        else
        {
            GpioDataRegs.GPACLEAR.bit.GPIO6 = 1;
        }
    }
}
```

邏輯是反相，不要改成同相：

- `GPADAT.GPIO0 == 0`：`GPASET.GPIO6 = 1`（GPIO6 高）
- 否則：`GPACLEAR.GPIO6 = 1`（GPIO6 低）

第 35 頁原文：

- the input (GPIO0) is high, the output (GPIO6) is low.
- the input (GPIO0) is low, the output (GPIO6) is high.

### 兩組 qualification

同一支程式量兩次。投影片標題的 `GPyQSEL`、`GPyCTRL` 對到：

- `GpioCtrlRegs.GPAQSEL1.bit.GPIO0`
- `GpioCtrlRegs.GPACTRL.bit.QUALPRD0`

| 投影片    | 設定                                                    | 切換放大後應看到的現象      |
| ------ | ----------------------------------------------------- | ---------------- |
| 第 35 頁 | `GPAQSEL1.bit.GPIO0 = 0`，`GPACTRL.bit.QUALPRD0 = 0`   | GPIO6 在輸入緣附近多次抖動 |
| 第 36 頁 | `GPAQSEL1.bit.GPIO0 = 2`，`GPACTRL.bit.QUALPRD0 = 255` | GPIO6 只乾淨切換一次    |

第 34 頁印出的程式就是第 36 頁這組。第 35 頁要把這兩個欄位改成 0 再量一次。其餘暫存器與 `main` 的反相判斷保持不變。

### 量測接線

- 輸入 GPIO0：J8 pin 80
- 輸出 GPIO6：J8 pin 78

例圖把準位標成 3.3 V 與 0 V。輸入為高時輸出為低，輸入為低時輸出為高。

GPIO0 的外部信號從哪來、頻率、邊沿斜率，講義都沒寫，維持未指定。不要補函數產生器設定。畫面上要能看到 GPIO0 在 0 V 與 3.3 V 之間切換，並同時看 GPIO6。

## 操作界線

- 依上面的程式與腳位操作。
- 不要把反相邏輯改成同相。
- 不要把 Example 1 改成連續方波。
- 不要為了量下降時間而另外做一版低準位輸出。
- 講義沒寫的儀器型號、觸發方式、信號源，保持未指定。
- 不要依本文件去開啟或修改任何既有 CCS 專案。
