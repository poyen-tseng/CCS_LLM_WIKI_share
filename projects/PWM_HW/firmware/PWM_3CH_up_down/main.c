
// Included Files

#include "F28x_Project.h"
#include "Init.h"


// [作業] 5_PWM_3_HW.pdf：ePWM1 產生 OutA／OutB（死區），每 4 次 CTR=0 事件中斷並翻轉 GPIO；
// 版本由 Init.h 的 HW_PART 選擇（spec v1.0 第 5.1 節）。
void main(void)
{
    InitSysCtrl();
    Init_GPIO();
    Init_ePWM1();
    Init_DAC();         // 只有 HW_PART 5 有內容
    Init_PIE();
    while(1)
    {
    }
}
