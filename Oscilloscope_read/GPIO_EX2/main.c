
// Included Files

#include "F28x_Project.h"
#include "Init.h"


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



