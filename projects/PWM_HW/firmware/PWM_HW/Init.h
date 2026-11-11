/*
 * Init.h
 *
 */

#ifndef INIT_H_
#define INIT_H_

// [作業] 5_PWM_3_HW.pdf（spec v1.0，SHA-256 204166F8…01FB）：選擇要建置的版本，改完重新建置、下載。
//   1：Up-Count，第 79 腳 = OutB（EPWM1B），duty 20 % 固定       → R1、R3 波形
//   2：Up-Down， 第 79 腳 = OutB（EPWM1B），duty 20 % 固定       → R1（Up-Down）、R3 波形
//   3：Up-Count，第 79 腳 = ISR GPIO1，     duty 20 % 固定       → R2、R3 ISR 進入時間
//   4：Up-Down， 第 79 腳 = ISR GPIO1，     duty 20 % 固定       → R2、R3 ISR 進入時間
//   5：Up-Count，第 79 腳 = 三角波轉折標記，duty 10→90→10 %，DAC → R4（選做）
// 第 80 腳（GPIO0）固定為 OutA（EPWM1A）。
#ifndef HW_PART
#define HW_PART 1
#endif

// ---- 由 HW_PART 導出的設定 -------------------------------------------------------------------------------
#define CNT_UP      0                   // TBCTL.CTRMODE = TB_COUNT_UP
#define CNT_UPDOWN  2                   // TBCTL.CTRMODE = TB_COUNT_UPDOWN

#define PIN79_OUTB  0                   // GPIO1 = EPWM1B（OutB）
#define PIN79_ISR   1                   // GPIO1 = ISR 進入時翻轉的 GPIO
#define PIN79_MARK  2                   // GPIO1 = 三角波轉折標記（上升段 High、下降段 Low）

#if   HW_PART == 1
#define CNT_MODE    CNT_UP
#define PIN79_FUNC  PIN79_OUTB
#define DUTY_RAMP   0
#elif HW_PART == 2
#define CNT_MODE    CNT_UPDOWN
#define PIN79_FUNC  PIN79_OUTB
#define DUTY_RAMP   0
#elif HW_PART == 3
#define CNT_MODE    CNT_UP
#define PIN79_FUNC  PIN79_ISR
#define DUTY_RAMP   0
#elif HW_PART == 4
#define CNT_MODE    CNT_UPDOWN
#define PIN79_FUNC  PIN79_ISR
#define DUTY_RAMP   0
#elif HW_PART == 5
#define CNT_MODE    CNT_UP
#define PIN79_FUNC  PIN79_MARK
#define DUTY_RAMP   1
#else
#error "HW_PART 必須是 1 到 5"
#endif

// ---- spec 3.2 的常數（TBCLK = 100 MHz，1 count = 10 ns）----------------------------------------------------
#if CNT_MODE == CNT_UP
#define PWM_TBPRD   499                 // f = TBCLK/(TBPRD+1) = 100 MHz/500 = 200 kHz
#define PWM_CMPA    100                 // D·(TBPRD+1) = 0.2 × 500 = 100 → 高準位 1.000 µs（從 CTR=0 開始）
#else
#define PWM_TBPRD   250                 // f = TBCLK/(2·TBPRD) = 100 MHz/500 = 200 kHz
#define PWM_CMPA    50                  // D·TBPRD = 0.2 × 250 = 50 → 高準位 2·CMPA·10 ns = 1.000 µs（以 CTR=0 為中心）
#endif
#define PWM_DB      30                  // 300 ns / 10 ns = 30（DBRED = DBFED）
#define ET_EVENTS   4                   // 每 4 次 CTR=0 事件進一次中斷（ETINTPS.INTPRD2）

// ---- 選做三角波（HW_PART 5，spec 3.6 / 提案 P4、P5）---------------------------------------------------------
#define RAMP_MIN    50                  // 10 % × 500
#define RAMP_MAX    450                 // 90 % × 500
#define ADC_BUF_LEN 800                 // 一個完整三角波 = 400 上升 + 400 下降 = 800 次 ISR（16 ms）

extern void Init_GPIO(void);
extern void Init_ePWM1(void);
extern void Init_DAC(void);
extern void Init_PIE(void);
extern __interrupt void epwm1_isr(void);

extern volatile Uint32 isrCount;        // ISR 執行次數（CCS 讀變數檢查中斷頻率用）
extern volatile Uint16 rampCmpa;        // 版本 5：目前的 CMPA
extern volatile int16  rampStep;        // 版本 5：+1 上升、-1 下降
extern volatile Uint16 adcBufIdx;       // 版本 5：ADC 回讀已存筆數
extern volatile Uint16 adcBufDone;      // 版本 5：1 = 800 筆已存滿
extern Uint16 adcBuf[ADC_BUF_LEN];      // 版本 5：ADC 回讀 DAC 腳（ADCINA0）結果，內部 ADC，非示波器
extern Uint16 dacBuf[ADC_BUF_LEN];      // 版本 5：與 adcBuf 同一筆時，當時已輸出（取樣時）的 DAC code

#endif /* INIT_H_ */
