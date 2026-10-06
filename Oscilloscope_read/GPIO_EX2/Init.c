
/* Init.c */

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
    // 使GPIO0腳位為輸入。
    GpioCtrlRegs.GPADIR.bit.GPIO0 = 0;
    // 選擇GPIO0腳位的功能。GPAGMUX1:GPAMUX1 = 00:00 => GPIO0為GPIO功能。
    GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 0;
    GpioCtrlRegs.GPAGMUX1.bit.GPIO0 = 0;
    // 關閉GPIO0的Pull-up電阻。
    GpioCtrlRegs.GPAPUD.bit.GPIO0 = 1;
    // 關閉GPIO0輸入反相功能。
    GpioCtrlRegs.GPAINV.bit.GPIO0 = 0;
    // 調整GPIO0採樣頻率。
    // 第 35 頁另一次量測把 QUALPRD0 與 GPAQSEL1.GPIO0 都改成 0。
    // 這支程式停在第 36 頁：QUALPRD0 = 255、GPAQSEL1.GPIO0 = 2。
    GpioCtrlRegs.GPACTRL.bit.QUALPRD0 = 255;
    // 調整GPIO0的採樣窗格
    GpioCtrlRegs.GPAQSEL1.bit.GPIO0 = 2;
    // 設定GPIO6--------------------------------------------------------------------------------------------
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
    //------------------------------------------------------------------------------------------------------
    EDIS;
}


void Init_PIE(void)
{
    //
    // Initialize PIE and clear PIE registers. Disables CPU interrupts.
    //
    DINT;
    PieCtrlRegs.PIECTRL.bit.ENPIE  =  1;  // Enable the PIE Vector Table
    //
    // Initialize the PIE control registers to their default state.
    // The default state is all PIE interrupts disabled and flags
    // are cleared.
    //
    InitPieCtrl();

    // Disable CPU interrupts and clear all CPU interrupt flags
    IER = 0x0000;
    IFR = 0x0000;

    // Initialize the PIE vector table with pointers to the shell Interrupt
    // Service Routines (ISR).
    InitPieVectTable();

    PieCtrlRegs.PIEIER3.bit.INTx1= 1;
    IER |= M_INT3;
    EINT;
    ERTM;
}


void Init_CpuTimer(void)
{
    EALLOW;
    //設定Timer0
    //  初始化位址 CPU Timer0 位址
    CpuTimer0.RegsAddr = &CpuTimer0Regs;
    //  設定週期暫存器，TSYSCLK = 10ns，每經過一個TSYSCLK，Timer就減1，減到0後傳遞中斷要求並將Timer重制回PRD
    CpuTimer0Regs.PRD.all  = 2000; //TSYSCLK*PRD = Period = 10n*20000000 = 0.2s
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

    // Enable CPU int1 which is connected to CPU-Timer 0
    IER |= M_INT1;

    // Enable TINT0 in the PIE: Group 1 interrupt 7
    PieCtrlRegs.PIEIER1.bit.INTx7 = 1;

    // Enable global Interrupts and higher priority real-time debug events
    EINT;
    ERTM;

    EDIS;
}


void Init_ePWM(void)
{
    EALLOW;
    //TB submodule----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    //計數器TBCTR與週期PRD設定
    //EPwm1---------------------------------------------------------------------------------------------------------------
    //啟用CPU給EPWM的Clock(SYSCLK)
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    CpuSysRegs.PCLKCR2.bit.EPWM1 = 1;
    //設定分頻器。均設為0，使TBCLK = SYSCLK = 100MHz，T_TBCLK = 1/100M = 10ns。
    EPwm1Regs.TBCTL.bit.HSPCLKDIV = 0;
    EPwm1Regs.TBCTL.bit.CLKDIV = 0;
    //設定FREE_SOFT。設定FREE_SOFT = 2 => TBCTR自由運行(正常計數)，若FREE_SOFT為0或1將停止TBCTR計數狀態。
    EPwm1Regs.TBCTL.bit.FREE_SOFT = 2;
    //設定計數器計數模式，CTRMOD = 1 => 下數模式。
    EPwm1Regs.TBCTL.bit.CTRMODE = 1;
    //初始化計數器TBCTR。
    EPwm1Regs.TBCTR = 0;
    //設定PRD調整EPWM週期，下數狀態。
    EPwm1Regs.TBPRD = 999; //(1+PRD)*T_TBCLK = 1000*10n = 10us = T_PWM => F_PWM = 1/T_PWM = 100kHz。
    //設定PRDLD，更動TBPRD值時，調整讀取新TBPRD值的時機，建議使用Shadow Mode。
    EPwm1Regs.TBCTL.bit.PRDLD = 0;
    //設定PRDLDSYNC，Shadow Mode的指定條件。
    EPwm1Regs.TBCTL2.bit.PRDLDSYNC = 0; //更動TBPRD時，當TBCTR數到0，才會Load新的TBCTR。
    //CC submodule--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    //EPwm1---------------------------------------------------------------------------------------------------------------
    //設定比較器CMPA
    EPwm1Regs.CMPA.bit.CMPA = 0.5*(EPwm1Regs.TBPRD);
    //設定比較器CMPB
    EPwm1Regs.CMPB.bit.CMPB = EPwm1Regs.CMPA.bit.CMPA;
    //設定SHDWxMODE，更動CMPx值時，調整讀取新CMPx值的時機，建議使用Shadow Mode。
    EPwm1Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm1Regs.CMPCTL.bit.SHDWBMODE = CC_SHADOW;
    //設定LOADxSYNC，Shadow Mode的指定條件。LOADxMODE = 0 => 根據LOADxMODE來Load新的CMPx
    EPwm1Regs.CMPCTL.bit.LOADASYNC = 0;
    EPwm1Regs.CMPCTL.bit.LOADBSYNC = 0;
    //設定LOADxMODE。LOADxMODE = 0 => 更動CMPx時，當計數器TBCTR數到0才會Load新的CMPx
    EPwm1Regs.CMPCTL.bit.LOADAMODE = 0;
    EPwm1Regs.CMPCTL.bit.LOADBMODE = 0;
    //AQ submodule--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    //EPwm1---------------------------------------------------------------------------------------------------------------
    //下數模式，TBCTR數到ZRO時SET(EPWM1A輸出High)，數到CMPA時CLEAR(EPWM1A輸出Low)。
    EPwm1Regs.AQCTLA.bit.ZRO = 2;
    EPwm1Regs.AQCTLA.bit.CAD = 1;
    EPwm1Regs.AQCTLA.bit.CBD = 0;
    EPwm1Regs.AQCTLA.bit.PRD = 0;
    //設定RLDCSF調整讀取軟體控制訊號的時機。
    EPwm1Regs.AQSFRC.bit.RLDCSF = 0;
    //本例題不會使用到軟體強控EPWM輸出 => CSFA/CSFB = 0 => 關閉軟體強控EPWM1A/EPWM1B。
    EPwm1Regs.AQCSFRC.bit.CSFA = 0;
    EPwm1Regs.AQCSFRC.bit.CSFB = 0;
    //DB submodule--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    //EPwm1---------------------------------------------------------------------------------------------------------------
    //路徑設定，關閉DB模組
    EPwm1Regs.DBCTL.bit.OUT_MODE = 0;
    //ET submodule---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    //EPwm1---------------------------------------------------------------------------------------------------------------
    //設定INTSEL，選擇事件觸發條件。INTSEL = 1 => 當TBCTR數到0時，Interrupt事件計數器CNT就會加1。 => 每週期(10us)，CNT+1。
    EPwm1Regs.ETSEL.bit.INTSEL = 1;
    //啟用EPWM1中斷
    EPwm1Regs.ETSEL.bit.INTEN = 1;//啟用
    //清除中斷旗標
    EPwm1Regs.ETCLR.bit.INT = 1;
    //調整中斷週期，每個事件時間為10us。設定為每1個事件觸發中斷 => 10us中斷一次 => 中斷頻率 = 100kHz
    EPwm1Regs.ETPS.bit.INTPSSEL = 0;
    EPwm1Regs.ETPS.bit.INTPRD = 1;
    EDIS;
}

void Init_ADC(void) //啟用ADC
{
    //設定Adcx的參考準位來源。
    SetVREF(ADC_ADCA, ADC_INTERNAL, ADC_VREF3P3); //設定ADCA為內部參考準位模式。
    EALLOW;
    //啟用CPU給ADCA的Clock(SYSCLK)。
    CpuSysRegs.PCLKCR13.bit.ADC_A = 1;
    //將Input Clock分頻成ADCCLK給ADCA。
    AdcaRegs.ADCCTL2.bit.PRESCALE = 2; //PRESCALE = 2，ADCCLK = Input Clock/2 = 100M/2 = 50M。
    //設定INTPULSEPOS調整EOC pulse產生的時機。INTPULSEPOS : 1 => 當SOC轉換結束並改變ADCRESULT時，會產生EOC pulse，進而觸發ADCA中斷。
    AdcaRegs.ADCCTL1.bit.INTPULSEPOS = 1;
    //啟用ADCA模組中的類比電路。
    AdcaRegs.ADCCTL1.bit.ADCPWDNZ = 1;
    //ADC模組啟用需一點時間，可參考詳細版P.1462。
    DELAY_US(1000);
    EDIS;
}


void Init_ADCSOC(void) //設定SOC
{
    EALLOW;
    //設定SOCPRIORITY選擇那些SOC是High Priority。SOCPRIORITY : 10h => SOC0~SOC15都是High Priority。
    AdcaRegs.ADCSOCPRICTL.bit.SOCPRIORITY = 0x10;
    //使用ADCA的SOC0通道-----------------------------------------------------------------------------------------------------------------------------------
    //設定ADCSOC0CTL.TRIGSEL調整SOC0觸發源。ADCSOC0CTL.TRIGSEL : 5 => 以EPWM1的SOCA觸發SOC0。
    AdcaRegs.ADCSOC0CTL.bit.TRIGSEL = 5;   //
    //設定ADCSOC0CTL.CHSEL調整SOC0選擇要採樣哪一個ADCIN並轉換。ADCSOC0CTL.CHSEL : 1 => SOC0採樣ADCIN1(A1)
    AdcaRegs.ADCSOC0CTL.bit.CHSEL = 1;
    //ACQPS設定採樣窗格。Acquisition window = (ACQPS+1)*TSYSCLK。
    AdcaRegs.ADCSOC0CTL.bit.ACQPS = 35;     // Acquisition window = (35+1)*10ns = 360ns
    //使用ADCA的SOC3通道-----------------------------------------------------------------------------------------------------------------------------------
    //設定ADCSOC3CTL.TRIGSEL調整SOC3觸發源。ADCSOC0CTL.TRIGSEL : 5 => 以EPWM1的SOCA觸發SOC3。
    AdcaRegs.ADCSOC3CTL.bit.TRIGSEL = 5;   //
    //設定ADCSOC3CTL.CHSEL調整SOC3選擇要採樣哪一個ADCIN並轉換。ADCSOC3CTL.CHSEL : 3 => SOC3採樣ADCIN3(A3)
    AdcaRegs.ADCSOC3CTL.bit.CHSEL = 3;
    //ACQPS設定採樣窗格。Acquisition window = (ACQPS+1)*TSYSCLK。
    AdcaRegs.ADCSOC3CTL.bit.ACQPS = 35;     // Acquisition window = (35+1)*10ns = 360ns
    //使用ADCA的SOC12通道-----------------------------------------------------------------------------------------------------------------------------------
    //設定ADCSOC12CTL.TRIGSEL調整SOC12觸發源。ADCSOC0CTL.TRIGSEL : 5 => 以EPWM1的SOCA觸發SOC3。
    AdcaRegs.ADCSOC12CTL.bit.TRIGSEL = 5;   //
    //設定ADCSOC12CTL.CHSEL調整SOC12選擇要採樣哪一個ADCIN並轉換。ADCSOC12CTL.CHSEL : 12 => SOC12採樣ADCIN12(A12)
    AdcaRegs.ADCSOC12CTL.bit.CHSEL = 12;
    //ACQPS設定採樣窗格。Acquisition window = (ACQPS+1)*TSYSCLK。
    AdcaRegs.ADCSOC12CTL.bit.ACQPS = 35;     // Acquisition window = (35+1)*10ns = 360ns
    //ADCAINT-----------------------------------------------------------------------------------------------------------------------------------------------
    //啟用ADCAINT1中斷
    AdcaRegs.ADCINTSEL1N2.bit.INT1E = 1;
    //ADCAINT1為連續中斷模式，不論ADCAINT1旗標是否為1，ADCA都會產生ADCAINT1要求給PIE
    AdcaRegs.ADCINTSEL1N2.bit.INT1CONT = 1;
    //選擇ADCAINT1觸發源。ADCINTSEL1N2.INT1SEL : 0 => 選擇使用EOC0觸發ADCAINT1
    AdcaRegs.ADCINTSEL1N2.bit.INT1SEL = 0;
    //初始化，清除ADCAINT1旗標
    AdcaRegs.ADCINTFLGCLR.bit.ADCINT1 = 1; // 0 <- X,  1 <- INT1 flag cleared
    EDIS;
}

// configureDAC - Configure specified DAC output
void Init_DAC(void)
{
    EALLOW;
    //Setting DACa-----------------------------------------------------------------------------------------------
    //設定LOADMODE決定何時Load DACVALS值，LOADMODE : 0 => 每經SYSCLK就Load DACVALS值並更新到DACVALA
    DacaRegs.DACCTL.bit.LOADMODE = 0;
    //設定MODE選擇緩衝器增益，MODE : 1 => 兩倍增益模式
    DacaRegs.DACCTL.bit.MODE = 1;
    //設定DACREFSEL選擇DAC參考準位，DACREFSEL : 1 => 與ADC使用同一組參考準位(內部3.3v Range)
    DacaRegs.DACCTL.bit.DACREFSEL = 1;
    //設定DACOUTEN啟用DAC，DACOUTE : 1 => 啟用DAC
    DacaRegs.DACOUTEN.bit.DACOUTEN = 1;
    //設定要轉換的數位值DACVALS
    DacaRegs.DACVALS.bit.DACVALS = 2048;
    EDIS;
}
void Init_PGA(void)
{
    EALLOW;
    //Setting PGA2-----------------------------------------------------------------------------------------------------------
    // PGAEN : 1 => 啟用PGA
    Pga2Regs.PGACTL.bit.PGAEN = 1;
    // 設定GAIN調整PGA增益。GAIN : 0 => x3 Mode
    Pga2Regs.PGACTL.bit.GAIN = 0;
    // 設定PGA輸出的RC濾波器電阻值。FILTRESSEL : 1 => RFilter = 200 Ohm
    Pga2Regs.PGACTL.bit.FILTRESSEL = 1; //PGA_OUT在開發版沒有外接pin腳，測量時需使用PGA_OF來觀察PGA倍率。
    EDIS;
}

void InitSCIB(void)
{
    EALLOW;
    //
    // Note: Clocks were turned on to the SCIA peripheral
    // in the InitSysCtrl() function
    //
    ScibRegs.SCICCR.all = 0x0007;           // 1 stop bit,  No loopback
                                            // No parity, 8 char bits,
                                            // async mode, idle-line protocol
    ScibRegs.SCICTL1.all = 0x0003;          // enable TX, RX, internal SCICLK,
                                            // Disable RX ERR, SLEEP, TXWAKE
    ScibRegs.SCICTL2.bit.TXINTENA = 1;
    ScibRegs.SCICTL2.bit.RXBKINTENA = 1;

    ScibRegs.SCIHBAUD.all = 0x0005;
    ScibRegs.SCILBAUD.all = 0x0015;

    ScibRegs.SCICTL1.all = 0x0023;          // Relinquish SCI from Reset

    ScibRegs.SCIFFTX.all = 0xE040;
    ScibRegs.SCIFFRX.all = 0x2044;
    ScibRegs.SCIFFCT.all = 0x0;
    EDIS;
}


void InitSCIBFIFO(void)
{
    EALLOW;
    ScibRegs.SCIFFTX.all = 0xE040;
    ScibRegs.SCIFFRX.all = 0x2044;
    ScibRegs.SCIFFCT.all = 0x0;
    EDIS;
}


void Init_XBAR(void)
{
    EALLOW;
    //資料路由1 : 將CMPSS1的CTRIPOUTH傳遞至OUTPUT X-BAR的OUTBUT1，再將OUTPUT X-BAR的OUTBUT1由GPIO2輸出。
    //OutputXbarRegs.OUTPUT1MUX0TO15CFG.bit.MUX0 : 0 => 選擇使用OUTPUT X-BAR的OUTBUT1傳遞CMPSS1的CTRIPOUTH資料(MUX0.0)。
    OutputXbarRegs.OUTPUT1MUX0TO15CFG.bit.MUX0 = 0;
    //OutputXbarRegs.OUTPUT1MUXENABLE.bit.MUX0 : 1 => 啟用OUTPUT X-BAR的MUX0路徑。
    OutputXbarRegs.OUTPUT1MUXENABLE.bit.MUX0 = 1;
    //OutputXbarRegs.OUTPUTLATCHENABLE.bit.OUTPUT1 : 0 => OUTPUT X-BAR的OUTBUT1不經過D-LATCH。
    OutputXbarRegs.OUTPUTLATCHENABLE.bit.OUTPUT1 = 0;
    //OutputXbarRegs.OUTPUTINV.bit.OUTPUT1 : 0 => 不將OUTPUT X-BAR的OUTBUT1反相。
    OutputXbarRegs.OUTPUTINV.bit.OUTPUT1 = 0;
    //資料路由2 : 將GPIO1的資料傳遞到INPUT XBAR的INPUT1，再將INPUT XBAR的INPUT1傳遞至EPWM的TZ模組(TZ1)。
    //InputXbarRegs.INPUT1SELECT : 1 => 選擇使用INPUT X-BAR的INPUT1傳遞GPIO1資料。
    InputXbarRegs.INPUT1SELECT = 1;
    EDIS;
}
