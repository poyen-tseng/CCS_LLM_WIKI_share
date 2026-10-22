
/* Init.c */
// 3_TIMER_lecture.pdf 第 13–15 頁 Step 1–3。

#include "F28x_Project.h"
#include "Init.h"

void Init_GPIO(void)
{
    // 初始化GPIO
    InitGpio();
    EALLOW;
    // 關閉所有GPIO內部上拉，減少功率損耗
    GpioCtrlRegs.GPAPUD.all = 0xFFFFFFFF;
    // 設定GPIO0--------------------------------------------------------------------------------------------
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
    //------------------------------------------------------------------------------------------------------
}


void Init_PIE(void)
{
    //
    // 啟用屏蔽功能，屏蔽所有中斷需求，停止中斷功能。
    DINT;
    // 初始化，清空PIE內所有的暫存器。
    InitPieCtrl();
    // 初始化，清空CPU中IER暫存器與IFR暫存器。
    IER = 0x0000;
    IFR = 0x0000;
    // 啟用PIE模組
    PieCtrlRegs.PIECTRL.bit.ENPIE = 1;
    // 初始化中斷向量表（1.7 指向 f28004x_defaultisr.c 的 TIMER0_ISR）
    InitPieVectTable();
    // 設定PIEIER暫存器，選擇使用哪種中斷
    PieCtrlRegs.PIEIER1.bit.INTx7 = 1; // INT1.7 => Timer0中斷
    // 啟用CPU中斷
    IER |= M_INT1; // 由於要使用INT1.7，所以需將INT1啟用。
    // 關閉屏蔽功能
    EINT;
    ERTM;

}


void Init_CpuTimer(void)
{

    EALLOW;
    //  /設定Timer0--------------------------------------------------------------------------------------------
    //  初始化位址 CPU Timer0 位址
    CpuTimer0.RegsAddr = &CpuTimer0Regs;
    //  設定週期暫存器，TSYSCLK = 10ns，每經過一個TSYSCLK，Timer就減1，減到0後傳遞中斷要求並將Timer重制回PRD
    CpuTimer0Regs.PRD.all  = 20000000; //TSYSCLK*PRD = Period = 10n*20000000 = 0.2s
    //  設定分頻器，本例題週期0.2s不需用到分頻器，均設為0即可
    CpuTimer0Regs.TPR.all  = 0;
    CpuTimer0Regs.TPRH.all = 0;
    //  TSS : 暫停Timer計數。TSS = 1 => 暫停Timer計數；TSS = 0 => 開啟Timer計數。
    CpuTimer0Regs.TCR.bit.TSS = 0;
    //  TIE : 啟用Timer0中斷。TIE = 1 => 啟用Timer中斷；TIE = 0 => 關閉Timer中斷。
    CpuTimer0Regs.TCR.bit.TIE = 1;
    //  初始化TIF。當Timer數到0時，TIF = 1，並清除該旗標使TIF = 0，開始下一輪計數。
    CpuTimer0Regs.TCR.bit.TIF = 1;
    //  初始化中斷計數器。中斷計數器 : 紀錄Timer0中斷執行了幾次。
    CpuTimer0.InterruptCount = 0;
    //------------------------------------------------------------------------------------------------------
    EDIS;
}
