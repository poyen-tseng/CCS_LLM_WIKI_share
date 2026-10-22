
// Included Files

#include "F28x_Project.h"
#include "Init.h"


// 3_TIMER_lecture.pdf 第 16 頁 Step 4（4_TIMER_Interrupt_HW.pdf 第 3 頁同一段）。
// Timer0 中斷由 TIMER0_ISR（在 f28004x_defaultisr.c）切換 GPIO；工作由 Init.h 的 HW_PART 選擇。
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
