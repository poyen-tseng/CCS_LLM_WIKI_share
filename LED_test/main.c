// Included Files

#include "F28x_Project.h"

void main(void)
{
    // InitSysCtrl() disables the watchdog, locks the PLL at 100 MHz,
    // and (when _FLASH is defined) copies .TI.ramfunc into RAM and calls InitFlash().
    InitSysCtrl();

    // LaunchPad LEDs are active low: drive 0 = ON, drive 1 = OFF.
    // LED4 (red)  = GPIO23. This pin boots as analog VSW, so GPAAMSEL must be cleared.
    // LED5 (green) = GPIO34 on port B.
    EALLOW;

    // GPIO23: digital GPIO, mux 0, CPU1, push-pull output.
    GpioCtrlRegs.GPAAMSEL.bit.GPIO23 = 0;
    GpioCtrlRegs.GPAMUX2.bit.GPIO23 = 0;
    GpioCtrlRegs.GPAGMUX2.bit.GPIO23 = 0;
    GpioCtrlRegs.GPACSEL3.bit.GPIO23 = 0;
    GpioCtrlRegs.GPAODR.bit.GPIO23 = 0;
    GpioDataRegs.GPASET.bit.GPIO23 = 1;
    GpioCtrlRegs.GPADIR.bit.GPIO23 = 1;

    // GPIO34: digital GPIO, mux 0, CPU1, push-pull output.
    GpioCtrlRegs.GPBMUX1.bit.GPIO34 = 0;
    GpioCtrlRegs.GPBGMUX1.bit.GPIO34 = 0;
    GpioCtrlRegs.GPBCSEL1.bit.GPIO34 = 0;
    GpioCtrlRegs.GPBODR.bit.GPIO34 = 0;
    GpioDataRegs.GPBSET.bit.GPIO34 = 1;
    GpioCtrlRegs.GPBDIR.bit.GPIO34 = 1;

    EDIS;

    while(1)
    {
        // LED4 on, LED5 off.
        GpioDataRegs.GPACLEAR.bit.GPIO23 = 1;
        GpioDataRegs.GPBSET.bit.GPIO34 = 1;
        DELAY_US(500000);

        // LED4 off, LED5 on.
        GpioDataRegs.GPASET.bit.GPIO23 = 1;
        GpioDataRegs.GPBCLEAR.bit.GPIO34 = 1;
        DELAY_US(500000);
    }
}
