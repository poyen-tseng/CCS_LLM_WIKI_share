
/* Init.c */
// 由 TIMER_HW 專案複製後改寫，依 5_PWM_3_HW.pdf 作業與 spec v1.0（run F280049C_5_PWM_3_HW_20261110_150311）修改（標 [作業]）。
// 時脈：InitSysCtrl() → SYSCLK = 20 MHz × 10 / 2 = 100 MHz；EPWMCLK = SYSCLK；TBCLK = EPWMCLK/(1×1) = 100 MHz，1 count = 10 ns。

#include "F28x_Project.h"
#include "Init.h"

volatile Uint32 isrCount   = 0;
volatile Uint16 rampCmpa   = RAMP_MIN;
volatile int16  rampStep   = 1;
volatile Uint16 adcBufIdx  = 0;
volatile Uint16 adcBufDone = 0;
#pragma DATA_SECTION(adcBuf, "ramgs0")
Uint16 adcBuf[ADC_BUF_LEN];
#pragma DATA_SECTION(dacBuf, "ramgs0")
Uint16 dacBuf[ADC_BUF_LEN];

#if DUTY_RAMP
static Uint16 adcRecording = 0;         // 1 = 已過第一個下轉折點（CMPA = 10 %），開始存一個完整三角波
static Uint16 adcPending   = 0;         // 1 = 上次 ISR 已觸發 SOC0，本次可讀結果
static Uint16 adcPendCode  = 0;         // 上次觸發 SOC0 時 DAC 正在輸出的 code
#endif

void Init_GPIO(void)
{
    // 初始化GPIO
    InitGpio();
    EALLOW;
    // 關閉所有GPIO內部上拉，減少功率損耗
    GpioCtrlRegs.GPAPUD.all = 0xFFFFFFFF;
    // [作業] GPIO0（第 80 腳）= EPWM1A → OutA ---------------------------------------------------------------
    // GPAGMUX1:GPAMUX1 = 00:01 => GPIO0 為 EPWM1A。
    GpioCtrlRegs.GPAGMUX1.bit.GPIO0 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 1;
    // [作業] GPIO1（第 79 腳）-----------------------------------------------------------------------------------
#if PIN79_FUNC == PIN79_OUTB
    // 版本 1/2：GPAGMUX1:GPAMUX1 = 00:01 => GPIO1 為 EPWM1B（OutB）。
    // ISR 仍會寫 GPATOGGLE，只改資料鎖存器，不影響腳位。
    GpioCtrlRegs.GPAGMUX1.bit.GPIO1 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO1 = 1;
#else
    // 版本 3/4（ISR GPIO）、版本 5（轉折標記）：GPAGMUX1:GPAMUX1 = 00:00 => GPIO1 為 GPIO 功能，輸出，CPU 控制。
    GpioCtrlRegs.GPAGMUX1.bit.GPIO1 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO1 = 0;
    GpioCtrlRegs.GPACSEL1.bit.GPIO1 = 0;
#if PIN79_FUNC == PIN79_MARK
    GpioDataRegs.GPASET.bit.GPIO1 = 1;      // 一開始 CMPA = 10 %，處於上升段 → High
#else
    GpioDataRegs.GPACLEAR.bit.GPIO1 = 1;    // ISR GPIO 起始為 Low
#endif
    GpioCtrlRegs.GPADIR.bit.GPIO1 = 1;
#endif
    // Approved v1.1 supplement: header pin 76 = GPIO2_BP (package pin 77).
    // Preserve GPIO0/1 ePWM mux; initialize GPIO2 latch LOW before enabling output.
    GpioCtrlRegs.GPAGMUX1.bit.GPIO2 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO2 = 0;
    GpioCtrlRegs.GPACSEL1.bit.GPIO2 = 0;
    GpioDataRegs.GPACLEAR.bit.GPIO2 = 1;
    GpioCtrlRegs.GPADIR.bit.GPIO2 = 1;
    EDIS;
    //------------------------------------------------------------------------------------------------------
}


void Init_ePWM1(void)
{
    EALLOW;
    // 啟用 ePWM1 時脈；設定期間先停住所有 ePWM 的 TBCLK（TBCLKSYNC = 0），Init_PIE() 最後再設 1。
    CpuSysRegs.PCLKCR2.bit.EPWM1 = 1;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    EDIS;

    // ---- TB：時基 -------------------------------------------------------------------------------------------
    // Up-Count：f = TBCLK/(TBPRD+1) = 100 MHz/(499+1) = 200 kHz
    // Up-Down ：f = TBCLK/(2·TBPRD) = 100 MHz/(2×250) = 200 kHz
    EPwm1Regs.TBCTL.bit.CTRMODE   = CNT_MODE;   // 0 = Up-Count，2 = Up-Down
    EPwm1Regs.TBCTL.bit.PHSEN     = 0;          // 不載入相位
    EPwm1Regs.TBCTL.bit.PRDLD     = 1;          // TBPRD 直接寫入 active（固定值，不需 shadow）
    EPwm1Regs.TBCTL.bit.SYNCOSEL  = 3;          // 不輸出 sync
    EPwm1Regs.TBCTL.bit.HSPCLKDIV = 0;          // ÷1，明確寫 0，不依賴重設值
    EPwm1Regs.TBCTL.bit.CLKDIV    = 0;          // ÷1 → TBCLK = 100 MHz
    EPwm1Regs.TBCTL.bit.FREE_SOFT = 2;          // 除錯停住 CPU 時 PWM 繼續跑
    EPwm1Regs.TBPRD               = PWM_TBPRD;
    EPwm1Regs.TBPHS.bit.TBPHS     = 0;
    EPwm1Regs.TBCTR               = 0;

    // ---- CC：比較值 -----------------------------------------------------------------------------------------
    // Up-Count：CMPA = D·(TBPRD+1) = 0.2×500 = 100；Up-Down：CMPA = D·TBPRD = 0.2×250 = 50
    // 先以 immediate 寫入 active，再改成 shadow、CTR=0 載入（執行中改 CMPA 用），並把同一值再寫進 shadow。
    // 注意：shadow 模式下讀寫 CMPA 都是 shadow；若 shadow 留 0，第一次 CTR=0 會把 active 蓋成 0
    // （2026-11-10 上板實測：只寫 immediate 時 CMPA 讀回 0）。
#if DUTY_RAMP
#define CMPA_INIT   RAMP_MIN                    // 版本 5 從 10 % 開始
#else
#define CMPA_INIT   PWM_CMPA
#endif
    EPwm1Regs.CMPCTL.bit.SHDWAMODE = 1;         // immediate
    EPwm1Regs.CMPA.bit.CMPA        = CMPA_INIT; // → active
    EPwm1Regs.CMPCTL.bit.SHDWAMODE = 0;         // shadow
    EPwm1Regs.CMPCTL.bit.LOADAMODE = 0;         // CTR=0 時載入
    EPwm1Regs.CMPA.bit.CMPA        = CMPA_INIT; // → shadow（與 active 相同）

    // ---- AQ：ePWM1A、ePWM1B 產生相同的 20 % 波形（都用 CMPA 事件）-------------------------------------------
    EPwm1Regs.AQCTLA.all = 0;
    EPwm1Regs.AQCTLB.all = 0;
#if CNT_MODE == CNT_UP
    // Up-Count：CTR=0 set、CTR=CMPA（上數）clear → 高準位 CMPA×10 ns = 1.000 µs，從 CTR=0 開始（邊緣對齊）
    EPwm1Regs.AQCTLA.bit.ZRO = 2;
    EPwm1Regs.AQCTLA.bit.CAU = 1;
    EPwm1Regs.AQCTLB.bit.ZRO = 2;
    EPwm1Regs.AQCTLB.bit.CAU = 1;
#else
    // Up-Down：上數到 CMPA clear、下數到 CMPA set → 高準位 2×CMPA×10 ns = 1.000 µs，以 CTR=0 為中心（提案 P3）
    EPwm1Regs.AQCTLA.bit.CAU = 1;
    EPwm1Regs.AQCTLA.bit.CAD = 2;
    EPwm1Regs.AQCTLB.bit.CAU = 1;
    EPwm1Regs.AQCTLB.bit.CAD = 2;
#endif

    // ---- DB：死區（PDF 紅字「AB都要輸入，再去產生outAB」）-----------------------------------------------------
    // IN_MODE = 2：ePWMxA → RED，ePWMxB → FED；POLSEL = 2（AHC，FED 路徑反相）；OUT_MODE = 3（兩路都經死區）
    // DBRED = DBFED = 300 ns / 10 ns = 30
    // OutA 高準位 = 1.0 − 0.3 = 0.7 µs；OutB = NOT FED(B)，高準位 = 5.0 − 1.0 − 0.3 = 3.7 µs
    EPwm1Regs.DBCTL.bit.HALFCYCLE = 0;
    EPwm1Regs.DBCTL.bit.DEDB_MODE = 0;
    EPwm1Regs.DBCTL.bit.OUTSWAP   = 0;
    EPwm1Regs.DBCTL.bit.IN_MODE   = 2;
    EPwm1Regs.DBCTL.bit.POLSEL    = 2;
    EPwm1Regs.DBCTL.bit.OUT_MODE  = 3;
    EPwm1Regs.DBRED.bit.DBRED     = PWM_DB;
    EPwm1Regs.DBFED.bit.DBFED     = PWM_DB;

    // ---- ET：每 4 次 CTR=0 事件進一次中斷 ---------------------------------------------------------------------
    // ETPS.INTPRD 只有 2 bit（最多每 3 次），所以改用 INTPSSEL = 1 + ETINTPS.INTPRD2 = 4（4 bit，最多 15）。
    // 中斷間隔 = 4 × 5 µs = 20 µs → ISR GPIO 方波週期 40 µs（25 kHz）。
    EPwm1Regs.ETSEL.bit.INTSEL     = 1;         // ET_CTR_ZERO
    EPwm1Regs.ETPS.bit.INTPSSEL    = 1;
    EPwm1Regs.ETINTPS.bit.INTPRD2  = ET_EVENTS;
    EPwm1Regs.ETCLR.bit.INT        = 1;
    EPwm1Regs.ETSEL.bit.INTEN      = 1;
}


void Init_DAC(void)
{
#if DUTY_RAMP
    // [作業] 選做：DACOUTA（第 70 腳，ADCINA0）輸出 duty 指令；ADC-A 回讀同一腳（提案 P5，內部 ADC，非示波器）。
    EALLOW;
    CpuSysRegs.PCLKCR13.bit.ADC_A = 1;
    CpuSysRegs.PCLKCR13.bit.ADC_B = 1;
    CpuSysRegs.PCLKCR16.bit.DAC_A = 1;
    EDIS;
    // 內部 3.3 V 參考模式（VREFHI 內部輸出 1.65 V）。100 腳封裝 VREFHIA/VREFHIB 共用，兩個 ADC 設成同一模式。
    SetVREF(ADC_ADCA, ADC_INTERNAL, ADC_VREF3P3);
    SetVREF(ADC_ADCB, ADC_INTERNAL, ADC_VREF3P3);
    EALLOW;
    // DAC：參考 = VREFHI（DACREFSEL = 1），gain ×2（MODE = 1）→ 輸出 0–3.3 V。
    // 依據：C2000Ware f28004x aci_motor_benchmark device.c「When using the internal reference of 3.3V, the DAC gain of x2 should be set」（待確認 O1 結論）。
    DacaRegs.DACCTL.bit.DACREFSEL = 1;
    DacaRegs.DACCTL.bit.MODE      = 1;
    DacaRegs.DACCTL.bit.LOADMODE  = 0;          // 下一個 SYSCLK 就載入
    DacaRegs.DACVALS.bit.DACVALS  = (Uint16)((Uint32)RAMP_MIN * 4095 / 500);
    DacaRegs.DACOUTEN.bit.DACOUTEN = 1;
    // ADC-A：ADCCLK = 100 MHz / 2 = 50 MHz；SOC0 = ADCINA0，軟體觸發，取樣窗 (49+1)×10 ns = 500 ns。
    AdcaRegs.ADCCTL2.bit.PRESCALE    = 2;
    AdcaRegs.ADCCTL1.bit.INTPULSEPOS = 1;
    AdcaRegs.ADCCTL1.bit.ADCPWDNZ    = 1;
    AdcaRegs.ADCSOC0CTL.bit.CHSEL    = 0;
    AdcaRegs.ADCSOC0CTL.bit.ACQPS    = 49;
    AdcaRegs.ADCSOC0CTL.bit.TRIGSEL  = 0;
    EDIS;
    DELAY_US(1000);                             // ADC 上電與 DAC 穩定
#endif
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
    // 初始化中斷向量表
    InitPieVectTable();
    // [作業] INT3.1 => ePWM1 中斷，指向本檔的 epwm1_isr
    EALLOW;
    PieVectTable.EPWM1_INT = &epwm1_isr;
    EDIS;
    PieCtrlRegs.PIEIER3.bit.INTx1 = 1;
    // 啟用CPU中斷
    IER |= M_INT3;
    // 關閉屏蔽功能
    EINT;
    ERTM;
    // [作業] 全部設定完才啟動 TBCLK。放在 PIE 就緒之後：若 ETFLG 在 PIE 清除前就被設起，ePWM 不會再發中斷。
    EPwm1Regs.ETCLR.bit.INT = 1;
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
}


// [作業] ePWM1 中斷：每 4 次 CTR=0 事件（每 20 µs）進一次。
__interrupt void epwm1_isr(void)
{
#if !DUTY_RAMP
    // Approved v1.1: first C statement toggles GPIO2 (pin76); pin79 remains OutB.
    // Compiler ISR context save still precedes this C statement.
    GpioDataRegs.GPATOGGLE.bit.GPIO2 = 1;
    isrCount++;
#else
    // 版本 5：duty 10 %→90 %→10 %，每次 ±1 count，800 次 = 16 ms。
    Uint16 cmpa;
    isrCount++;
    // ADC 回讀：讀上次觸發的結果，再觸發一次（取樣的是上次 ISR 寫入、已穩定 20 µs 的 DAC code）。
    if (adcRecording && adcPending && !adcBufDone)
    {
        adcBuf[adcBufIdx] = AdcaResultRegs.ADCRESULT0;
        dacBuf[adcBufIdx] = adcPendCode;
        adcBufIdx++;
        if (adcBufIdx >= ADC_BUF_LEN) adcBufDone = 1;
    }
    adcPendCode = DacaRegs.DACVALS.bit.DACVALS;
    AdcaRegs.ADCSOCFRC1.bit.SOC0 = 1;
    adcPending = 1;

    cmpa = rampCmpa + rampStep;
    if (cmpa >= RAMP_MAX)       { cmpa = RAMP_MAX; rampStep = -1; GpioDataRegs.GPACLEAR.bit.GPIO1 = 1; }  // 90 %，開始下降
    else if (cmpa <= RAMP_MIN)  { cmpa = RAMP_MIN; rampStep =  1; GpioDataRegs.GPASET.bit.GPIO1 = 1;      // 10 %，開始上升
                                  adcRecording = 1; }
    rampCmpa = cmpa;
    EPwm1Regs.CMPA.bit.CMPA = cmpa;                                     // shadow，CTR=0 載入
    DacaRegs.DACVALS.bit.DACVALS = (Uint16)((Uint32)cmpa * 4095 / 500); // 409（10 %）… 3685（90 %）
#endif
    // 清除 ePWM1 中斷旗標，並回應 PIE 第 3 組
    EPwm1Regs.ETCLR.bit.INT = 1;
    PieCtrlRegs.PIEACK.all = PIEACK_GROUP3;
}
