/*
 * Comm.h
 *
 */

#ifndef COMM_H_
#define COMM_H_


enum {
  _QueryDAQAddress,
  _QueryBatteryVoltage,
  _RecieveBatteryVoltage,
  _TransBatteryVoltageTo,





  _Wait,

};




typedef struct{

    uint16_t                       Battery_Voltage[8];

}BATTERY_DATA_STRUCT;


typedef struct {

    uint16_t                   ADCbuff;
    unsigned char              TxData[20];
    unsigned char              URFIFO[70];
    unsigned char              Data_In;
    unsigned char              Data_Out;
    unsigned char              Data_Point;


}COMM_DATA_STRUCT;


typedef struct {


    COMM_DATA_STRUCT                                    sCommData;
    BATTERY_DATA_STRUCT                                 sBatteryData;


    uint32_t                                            SystemCount;
    uint32_t                                            MiniSecCount;
    uint32_t                                            AD_Value;

    uint16_t                                            SystemFlag;
    uint16_t                                            URPoint;
    uint16_t                                            flagTimer;

    uint16_t                                            Comm_Status;







}APP_COMM_STRUCT;


extern APP_COMM_STRUCT* Initial_APP_COMM(void);
extern void transmitSCIBChar(uint16_t a);
extern void transmitSCIBMessage(unsigned char * msg);
extern void URData_Process(APP_COMM_STRUCT* psHUD_APP);
extern void COMM_DATA_Process(APP_COMM_STRUCT* psHUD_APP);

#endif /* COMM_H_ */
