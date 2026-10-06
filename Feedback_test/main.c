//###########################################################################
//
// FILE:   main.c
//
// TITLE:  F280049C LaunchPad self-feedback test
//
// Polling only. No interrupts. Watchdog is disabled by codestart
// (WD_DISABLE) and again by InitSysCtrl().
//
//###########################################################################

#include "F28x_Project.h"

//
// SYSCLK = 10 MHz XTAL * IMULT_10 / PLLCLK_BY_2 = 100 MHz.
// InitSysCtrl() / InitPeripheralClocks() never write ClkCfgRegs.LOSPCP.
// LSPCLKDIV reset value is 2, which driverlib documents as
// SYSCTL_LSPCLK_PRESCALE_4 (default): LSPCLK = SYSCLK / 4 = 25 MHz.
// driverlib SysCtl_getLowSpeedClock() divides by (2 * LSPCLKDIV) when
// LSPCLKDIV != 0, which is the same /4.
//
// BRR = LSPCLK / (baud * 8) - 1
//     = 25000000 / (115200 * 8) - 1
//     = 27.1267... - 1
//     = 26.1267...
// Integer division truncates 25000000/921600 to 27, then subtracts 1,
// so the programmed BRR is 26 (0x001A). Same constant as the LaunchPad
// demo (SCIHBAUD = 0x00, SCILBAUD = 0x1A).
//
// Actual baud = 25000000 / ((26 + 1) * 8) = 115740.74 Hz
// Error = (115740.74 - 115200) / 115200 = +0.469%
//
#define SYSCLK_HZ            100000000UL
#define LSPCLK_DIV           4UL
#define LSPCLK_HZ            (SYSCLK_HZ / LSPCLK_DIV)
#define SCIA_BAUD_TARGET     115200UL
#define SCIA_BRR             ((LSPCLK_HZ / (SCIA_BAUD_TARGET * 8UL)) - 1UL)

#if (SCIA_BRR != 26)
#error "SCIA_BRR is not 26; check LSPCLK or the baud formula"
#endif

#define GPIO_READBACK_PASSES 4U
#define SCI_SPIN_LIMIT       200000UL

static void Sci_Config(volatile struct SCI_REGS *sci, Uint16 loopback);
static void Sci_SendByte(volatile struct SCI_REGS *sci, Uint16 data);
static void SciA_SendString(const char *msg);
static Uint16 Gpio0_ReadbackTest(void);
static Uint16 SciB_LoopbackTest(void);
static void SciA_Init(void);
static void SciA_SendReport(Uint16 gpioPass, Uint16 sciPass);
static Uint16 SciA_WaitForRx(void);
static void SciA_RecoverRx(void);
static void SciA_EchoOnce(void);

static void Sci_Config(volatile struct SCI_REGS *sci, Uint16 loopback)
{
    // FIFO on, both FIFOs out of reset. 0xE040 / 0x2044 match the
    // proven C2000Ware SCI FIFO loopback init (SCIRST, SCIFFENA,
    // TXFIFORESET, RXFIFORESET, interrupt flags cleared).
    sci->SCIFFTX.all = 0xE040;
    sci->SCIFFRX.all = 0x2044;
    sci->SCIFFCT.all = 0x0000;

    // 8 data bits, idle-line, no parity, 1 stop. Loopback is applied below.
    sci->SCICCR.all = 0x0007;
    // TX and RX enabled, SCI held in software reset.
    sci->SCICTL1.all = 0x0003;
    // Polling only: receiver and transmitter interrupts stay off.
    sci->SCICTL2.all = 0x0000;

    sci->SCIHBAUD.all = (Uint16)((SCIA_BRR >> 8) & 0x00FFU);
    sci->SCILBAUD.all = (Uint16)(SCIA_BRR & 0x00FFU);

    sci->SCICCR.bit.LOOPBKENA = loopback;

    // Release software reset. TXENA and RXENA stay set.
    sci->SCICTL1.all = 0x0023;
}

static void Sci_SendByte(volatile struct SCI_REGS *sci, Uint16 data)
{
    Uint32 spin;

    spin = 0UL;
    while(sci->SCIFFTX.bit.TXFFST >= 16U)
    {
        spin++;
        if(spin > SCI_SPIN_LIMIT)
        {
            return;
        }
    }

    sci->SCITXBUF.all = data & 0x00FFU;
}

static void SciA_SendString(const char *msg)
{
    while(*msg != 0)
    {
        Sci_SendByte(&SciaRegs, (Uint16)(*msg) & 0x00FFU);
        msg++;
    }
}

//
// GPIO0 is a plain push-pull output with its pull-up disabled.
// GPADAT is read back after each level. GPIO0 is left high.
//
static Uint16 Gpio0_ReadbackTest(void)
{
    Uint16 pass;
    Uint16 n;

    pass = 1U;

    EALLOW;
    GpioCtrlRegs.GPAGMUX1.bit.GPIO0 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO0 = 1;
    GpioCtrlRegs.GPAPUD.bit.GPIO0 = 1;
    GpioCtrlRegs.GPAODR.bit.GPIO0 = 0;
    GpioCtrlRegs.GPAINV.bit.GPIO0 = 0;
    GpioCtrlRegs.GPACSEL1.bit.GPIO0 = 0;
    EDIS;

    for(n = 0U; n < GPIO_READBACK_PASSES; n++)
    {
        GpioDataRegs.GPACLEAR.bit.GPIO0 = 1;
        DELAY_US(10);
        if(GpioDataRegs.GPADAT.bit.GPIO0 != 0U)
        {
            pass = 0U;
        }

        GpioDataRegs.GPASET.bit.GPIO0 = 1;
        DELAY_US(10);
        if(GpioDataRegs.GPADAT.bit.GPIO0 != 1U)
        {
            pass = 0U;
        }
    }

    GpioDataRegs.GPASET.bit.GPIO0 = 1;
    return(pass);
}

//
// SCIB internal loopback. No SCIB pins are muxed.
// Bytes 0x00..0xFF are sent one at a time and compared with SCIRXBUF.
// SCIB is held in reset and its clock is gated off afterwards.
//
static Uint16 SciB_LoopbackTest(void)
{
    Uint16 pass;
    Uint16 value;
    Uint16 raw;
    Uint32 spin;

    pass = 1U;
    Sci_Config(&ScibRegs, 1U);

    for(value = 0U; value < 256U; value++)
    {
        spin = 0UL;
        while(ScibRegs.SCIFFTX.bit.TXFFST != 0U)
        {
            spin++;
            if(spin > SCI_SPIN_LIMIT)
            {
                pass = 0U;
                break;
            }
        }
        if(pass == 0U)
        {
            break;
        }

        ScibRegs.SCITXBUF.all = value;

        spin = 0UL;
        while(ScibRegs.SCIFFRX.bit.RXFFST == 0U)
        {
            spin++;
            if(spin > SCI_SPIN_LIMIT)
            {
                pass = 0U;
                break;
            }
        }
        if(pass == 0U)
        {
            break;
        }

        if((ScibRegs.SCIRXST.bit.RXERROR != 0U) ||
           (ScibRegs.SCIFFRX.bit.RXFFOVF != 0U))
        {
            pass = 0U;
            (void)ScibRegs.SCIRXBUF.all;
            break;
        }

        raw = ScibRegs.SCIRXBUF.all;
        if((raw & 0xC000U) != 0U)
        {
            pass = 0U;
            break;
        }
        if((raw & 0x00FFU) != value)
        {
            pass = 0U;
            break;
        }
    }

    ScibRegs.SCICTL1.all = 0x0000;
    ScibRegs.SCICCR.all = 0x0000;
    ScibRegs.SCIFFTX.all = 0x0000;
    ScibRegs.SCIFFRX.all = 0x0000;
    ScibRegs.SCIFFCT.all = 0x0000;

    EALLOW;
    CpuSysRegs.PCLKCR7.bit.SCI_B = 0;
    EDIS;

    return(pass);
}

//
// SCIA on the LaunchPad XDS110 virtual COM port:
//   GPIO28 mux 1 = SCIRXDA, asynchronous input, pull-up enabled
//   GPIO29 mux 1 = SCITXDA
// 115200 8N1, FIFO enabled, loopback off.
//
static void SciA_Init(void)
{
    EALLOW;
    GpioCtrlRegs.GPAGMUX2.bit.GPIO28 = 0;
    GpioCtrlRegs.GPAMUX2.bit.GPIO28 = 1;
    GpioCtrlRegs.GPAQSEL2.bit.GPIO28 = 3;
    GpioCtrlRegs.GPAPUD.bit.GPIO28 = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO28 = 0;

    GpioCtrlRegs.GPAGMUX2.bit.GPIO29 = 0;
    GpioCtrlRegs.GPAMUX2.bit.GPIO29 = 1;
    GpioCtrlRegs.GPAPUD.bit.GPIO29 = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO29 = 1;
    EDIS;

    Sci_Config(&SciaRegs, 0U);
}

static void SciA_SendReport(Uint16 gpioPass, Uint16 sciPass)
{
    SciA_SendString("\r\nF280049C Feedback_test\r\nGPIO_READBACK: ");
    SciA_SendString((gpioPass != 0U) ? "PASS\r\n" : "FAIL\r\n");
    SciA_SendString("SCI_LOOPBACK: ");
    SciA_SendString((sciPass != 0U) ? "PASS\r\n" : "FAIL\r\n");
    SciA_SendString("ECHO: READY (send any byte)\r\n");
}

//
// About 1 second, sliced into 1 ms delays so an arriving byte ends the wait.
// The byte is left in the RX FIFO for the echo phase.
//
static Uint16 SciA_WaitForRx(void)
{
    Uint16 slice;

    for(slice = 0U; slice < 1000U; slice++)
    {
        if(SciaRegs.SCIFFRX.bit.RXFFST != 0U)
        {
            return(1U);
        }
        DELAY_US(1000);
    }

    return(0U);
}

static void SciA_RecoverRx(void)
{
    SciaRegs.SCICTL1.bit.SWRESET = 0;
    SciaRegs.SCIFFRX.bit.RXFIFORESET = 0;
    SciaRegs.SCIFFTX.bit.TXFIFORESET = 0;

    SciaRegs.SCICTL1.bit.TXENA = 1;
    SciaRegs.SCICTL1.bit.RXENA = 1;
    SciaRegs.SCIFFTX.bit.SCIRST = 1;
    SciaRegs.SCIFFTX.bit.SCIFFENA = 1;
    SciaRegs.SCIFFRX.bit.RXFFOVRCLR = 1;
    SciaRegs.SCIFFRX.bit.RXFFINTCLR = 1;
    SciaRegs.SCIFFTX.bit.TXFFINTCLR = 1;

    SciaRegs.SCICTL1.bit.SWRESET = 1;
    SciaRegs.SCIFFTX.bit.TXFIFORESET = 1;
    SciaRegs.SCIFFRX.bit.RXFIFORESET = 1;
}

static void SciA_EchoOnce(void)
{
    Uint16 raw;

    if((SciaRegs.SCIRXST.bit.RXERROR != 0U) ||
       (SciaRegs.SCIFFRX.bit.RXFFOVF != 0U))
    {
        SciA_RecoverRx();
        return;
    }

    if(SciaRegs.SCIFFRX.bit.RXFFST == 0U)
    {
        return;
    }

    raw = SciaRegs.SCIRXBUF.all;
    if((raw & 0xC000U) != 0U)
    {
        SciA_RecoverRx();
        return;
    }

    // Binary transparent: the low 8 bits are sent back unchanged.
    Sci_SendByte(&SciaRegs, raw & 0x00FFU);
}

void main(void)
{
    Uint16 gpioPass;
    Uint16 sciPass;

    InitSysCtrl();

    DINT;
    IER = 0x0000;
    IFR = 0x0000;

    gpioPass = Gpio0_ReadbackTest();
    sciPass = SciB_LoopbackTest();
    SciA_Init();

    for(;;)
    {
        SciA_SendReport(gpioPass, sciPass);
        if(SciA_WaitForRx() != 0U)
        {
            break;
        }
    }

    for(;;)
    {
        SciA_EchoOnce();
    }
}
