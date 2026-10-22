/*
 * Comm.c
 *
 */

#include "F28x_Project.h"
#include "Comm.h"


APP_COMM_STRUCT sAPP_COMM;

APP_COMM_STRUCT* Initial_APP_COMM(void)
{

    sAPP_COMM.Comm_Status = _Wait;

    return &sAPP_COMM;

}


void transmitSCIBMessage(unsigned char * msg)
{
    int i;
    i = 0;
    while(msg[i] != '\0')
    {
        transmitSCIBChar(msg[i]);
        i++;
    }
}


void transmitSCIBChar(uint16_t a)
{
    while (ScibRegs.SCIFFTX.bit.TXFFST != 0)
    {

    }
    ScibRegs.SCITXBUF.all = a;
}



void COMM_DATA_Process(APP_COMM_STRUCT* psAPP_COMM)
{
    uint16_t     i,temp16=0,CellNumber=0;
    uint32_t    temp32;

    switch(psAPP_COMM->Comm_Status)
    {
    case _Wait:
        break;

    case _QueryDAQAddress:


        psAPP_COMM->Comm_Status = _Wait;
        break;


    case _QueryBatteryVoltage:

        // AA -> DAQ address
        psAPP_COMM->sCommData.TxData[0] = '#';
        psAPP_COMM->sCommData.TxData[1] = '0';
        psAPP_COMM->sCommData.TxData[2] = '1';
        psAPP_COMM->sCommData.TxData[3] = 0x0D;
        transmitSCIBMessage(&psAPP_COMM->sCommData.TxData[0]);
        GpioDataRegs.GPATOGGLE.bit.GPIO26=1;
        psAPP_COMM->Comm_Status = _Wait;
        break;


    case _RecieveBatteryVoltage:

        /*
        command: #21(cr)
        response: >+7.2111+7.2567+7.3125+7.1000     :30
        +7.4712+7.2555+7.1234+7.5678 (cr)           :29
        */


        while(psAPP_COMM->sCommData.URFIFO[temp16] != 0x0D)
        {
            if(psAPP_COMM->sCommData.URFIFO[temp16] == '+' || psAPP_COMM->sCommData.URFIFO[temp16] == '-')
            {
                temp32 = (psAPP_COMM->sCommData.URFIFO[temp16+1]-0x30)*10000;
                temp32 += (psAPP_COMM->sCommData.URFIFO[temp16+2]-0x30)*1000;
                temp32 += (psAPP_COMM->sCommData.URFIFO[temp16+4]-0x30)*100;
                temp32 += (psAPP_COMM->sCommData.URFIFO[temp16+5]-0x30)*10;
                temp32 += (psAPP_COMM->sCommData.URFIFO[temp16+6]-0x30);

                psAPP_COMM->sBatteryData.Battery_Voltage[CellNumber] = temp32;
                CellNumber++;

            }
            temp16++;
        }

        for(i=0;i<70;i++)
        {
            psAPP_COMM->sCommData.URFIFO[i] = 0;
        }
        GpioDataRegs.GPATOGGLE.bit.GPIO15= 1;
        psAPP_COMM->flagTimer =1;

        psAPP_COMM->Comm_Status = _Wait;
        break;


    case _TransBatteryVoltageTo:

 //       psAPP_COMM->sCommData.TxData[0] =  psAPP_COMM->sBatteryData.Battery_Voltage[0]>>8 & 0xFF;
 //       psAPP_COMM->sCommData.TxData[1] =  psAPP_COMM->sBatteryData.Battery_Voltage[1] & 0xFF;

        for(i=0;i<8;)
        {

            psAPP_COMM->sCommData.TxData[i] =  psAPP_COMM->sBatteryData.Battery_Voltage[i] & 0xFF;
            psAPP_COMM->sCommData.TxData[i+1] =  psAPP_COMM->sBatteryData.Battery_Voltage[i+1] & 0xFF;
            i+=2;
        }

        transmitSCIBMessage(&psAPP_COMM->sCommData.TxData[0]);

        psAPP_COMM->Comm_Status = _Wait;
        break;

    }
}








