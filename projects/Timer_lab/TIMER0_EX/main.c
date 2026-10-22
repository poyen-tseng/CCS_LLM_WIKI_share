
// Included Files

#include "F28x_Project.h"
#include "Init.h"


// 3_TIMER_lecture.pdf 第 16 頁 Step 4。
// Timer0 每 0.2 s 中斷一次，TIMER0_ISR（在 f28004x_defaultisr.c）切換 GPIO0。
void main(void)
{
    InitSysCtrl();
    Init_GPIO();
    Init_CpuTimer();
    Init_PIE();
    while(1)
    {
    }
}
