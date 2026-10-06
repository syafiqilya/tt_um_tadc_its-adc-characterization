#include "usbd_cdc_if.h"

#include "usb_device.h"

#define APP_RX_DATA_SIZE 64U
#define APP_TX_DATA_SIZE 64U

static uint8_t user_rx_buffer[APP_RX_DATA_SIZE];
static uint8_t user_tx_buffer[APP_TX_DATA_SIZE];

static int8_t CDC_Init_FS(void);
static int8_t CDC_DeInit_FS(void);
static int8_t CDC_Control_FS(uint8_t command, uint8_t *buffer,
                             uint16_t length);
static int8_t CDC_Receive_FS(uint8_t *buffer, uint32_t *length);
static int8_t CDC_TransmitCplt_FS(uint8_t *buffer, uint32_t *length,
                                  uint8_t endpoint);

USBD_CDC_ItfTypeDef USBD_Interface_fops_FS = {
    CDC_Init_FS,
    CDC_DeInit_FS,
    CDC_Control_FS,
    CDC_Receive_FS,
    CDC_TransmitCplt_FS,
};

static int8_t CDC_Init_FS(void)
{
    (void)USBD_CDC_SetTxBuffer(&hUsbDeviceFS, user_tx_buffer, 0U);
    (void)USBD_CDC_SetRxBuffer(&hUsbDeviceFS, user_rx_buffer);
    return (int8_t)USBD_OK;
}

static int8_t CDC_DeInit_FS(void)
{
    return (int8_t)USBD_OK;
}

static int8_t CDC_Control_FS(uint8_t command, uint8_t *buffer,
                             uint16_t length)
{
    (void)command;
    (void)buffer;
    (void)length;
    return (int8_t)USBD_OK;
}

static int8_t CDC_Receive_FS(uint8_t *buffer, uint32_t *length)
{
    (void)buffer;
    (void)length;
    (void)USBD_CDC_SetRxBuffer(&hUsbDeviceFS, user_rx_buffer);
    (void)USBD_CDC_ReceivePacket(&hUsbDeviceFS);
    return (int8_t)USBD_OK;
}

static int8_t CDC_TransmitCplt_FS(uint8_t *buffer, uint32_t *length,
                                  uint8_t endpoint)
{
    (void)buffer;
    (void)length;
    (void)endpoint;
    return (int8_t)USBD_OK;
}

uint8_t CDC_Transmit_FS(uint8_t *buffer, uint16_t length)
{
    USBD_CDC_HandleTypeDef *cdc;

    cdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
    if (cdc == NULL || cdc->TxState != 0U) {
        return USBD_BUSY;
    }

    (void)USBD_CDC_SetTxBuffer(&hUsbDeviceFS, buffer, length);
    return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}
