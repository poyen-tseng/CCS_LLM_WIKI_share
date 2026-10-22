/*
 * Init.h
 *
 */

#ifndef INIT_H_
#define INIT_H_

// [作業] 4_TIMER_Interrupt_HW.pdf：選擇要建置的工作，改完重新建置、下載。
//   1：工作 1，GPIO1 輸出 100 Hz 方波，GPIO2 為 ISR 脈波（PRD = 500000，ISR 每 5 ms）
//   2：工作 2，GPIO1 輸出 100 Hz、GPIO2 輸出 500 Hz，GPIO0 為 ISR 脈波（PRD = 100000，ISR 每 1 ms）
// 工作 3（ISR 執行時間）就量這兩個建置的 ISR 脈波。
#define HW_PART 1

extern void Init_GPIO(void);
extern void Init_CpuTimer(void);
extern void Init_PIE(void);


#endif /* INIT_H_ */
