#include "tadc_capture.h"

#include "main.h"
#include "usb_device.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"

#include <stddef.h>

/*
 * DevEBox STM32H743VIT6 signal assignment:
 *   DATA[0:8] = PE7:PE15 (one atomic GPIOE->IDR read)
 *   CKO       = PA0 / TIM2_CH1 input capture
 *   ADC_CLK   = PA6 / TIM3_CH1 PWM
 *   ADC_EN    = PC0 GPIO output
 *   START     = PE3 onboard K1, active low
 *   STATUS    = PA1 onboard D2, active low
 *   USB CDC   = PA11/PA12 through the board's J5 connector
 */

#define TADC_DATA_GPIO              GPIOE
#define TADC_DATA_SHIFT             7U
#define TADC_DATA_MASK              0x01FFU

#define TADC_EN_GPIO                GPIOC
#define TADC_EN_PIN                 GPIO_PIN_0

#define TADC_START_GPIO             GPIOE
#define TADC_START_PIN              GPIO_PIN_3

#define TADC_LED_GPIO               GPIOA
#define TADC_LED_PIN                GPIO_PIN_1

#define TADC_CKO_TIMER              htim2
#define TADC_CKO_CHANNEL            TIM_CHANNEL_1
#define TADC_CLOCK_TIMER            htim3
#define TADC_CLOCK_CHANNEL          TIM_CHANNEL_1

#define TADC_DATA_SETTLE_NS         300U
#define TADC_DATA_VERIFY_NS         100U
#define TADC_USB_PACKET_BYTES       64U
#define TADC_UART_HEADER_BYTES      16U
#define TADC_UART_RECORD_BYTES      8U

extern TIM_HandleTypeDef htim2;
extern TIM_HandleTypeDef htim3;
extern USBD_HandleTypeDef hUsbDeviceHS;

typedef struct {
    uint32_t timestamp;
    uint16_t code_flags;
    uint16_t reserved;
} tadc_sample_t;

static tadc_sample_t sample_buffer[TADC_SAMPLE_COUNT];
static volatile uint32_t sample_count;
static volatile tadc_state_t state;

static uint8_t usb_tx_buffer[TADC_USB_PACKET_BYTES] __attribute__((aligned(32)));
static uint32_t stream_index;
static bool stream_header_sent;
static bool stream_final_packet_queued;
static GPIO_PinState previous_button_state;

static inline void led_on(void)
{
    HAL_GPIO_WritePin(TADC_LED_GPIO, TADC_LED_PIN, GPIO_PIN_RESET);
}

static inline void led_off(void)
{
    HAL_GPIO_WritePin(TADC_LED_GPIO, TADC_LED_PIN, GPIO_PIN_SET);
}

static inline uint16_t read_adc_bus(void)
{
    return (uint16_t)((TADC_DATA_GPIO->IDR >> TADC_DATA_SHIFT) & TADC_DATA_MASK);
}

static void cycle_counter_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static void delay_ns(uint32_t nanoseconds)
{
    uint32_t cycles = (uint32_t)((((uint64_t)SystemCoreClock * nanoseconds)
                                  + 999999999ULL) / 1000000000ULL);
    uint32_t start = DWT->CYCCNT;
    while ((uint32_t)(DWT->CYCCNT - start) < cycles) {
        __NOP();
    }
}

static void put_u16_le(uint8_t *destination, uint16_t value)
{
    destination[0] = (uint8_t)value;
    destination[1] = (uint8_t)(value >> 8);
}

static void put_u32_le(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)value;
    destination[1] = (uint8_t)(value >> 8);
    destination[2] = (uint8_t)(value >> 16);
    destination[3] = (uint8_t)(value >> 24);
}

static void build_header(uint8_t *destination)
{
    destination[0] = 'T';
    destination[1] = 'A';
    destination[2] = 'D';
    destination[3] = 'C';
    destination[4] = TADC_PROTOCOL_VERSION;
    destination[5] = TADC_UART_RECORD_BYTES;
    put_u16_le(&destination[6], TADC_SAMPLE_COUNT);
    put_u32_le(&destination[8], TADC_TIMER_CLOCK_HZ);
    put_u32_le(&destination[12], TADC_ADC_CLOCK_HZ);
}

static void build_record(uint8_t *destination, const tadc_sample_t *sample)
{
    destination[0] = 0xA5U;
    destination[1] = 0x5AU;
    put_u16_le(&destination[2], sample->code_flags);
    put_u32_le(&destination[4], sample->timestamp);
}

static bool usb_is_configured_and_idle(void)
{
    USBD_CDC_HandleTypeDef *cdc;

    if (hUsbDeviceHS.dev_state != USBD_STATE_CONFIGURED ||
        hUsbDeviceHS.pClassData == NULL) {
        return false;
    }

    cdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceHS.pClassData;
    return cdc->TxState == 0U;
}

static bool usb_transmit(uint8_t *data, uint16_t length)
{
    return CDC_Transmit_HS(data, length) == USBD_OK;
}

static void stream_task(void)
{
    uint32_t records_this_packet;
    uint32_t index;

    if (!usb_is_configured_and_idle()) {
        return;
    }

    if (stream_final_packet_queued) {
        state = TADC_STATE_DONE;
        led_off();
        return;
    }

    if (!stream_header_sent) {
        build_header(usb_tx_buffer);
        if (usb_transmit(usb_tx_buffer, TADC_UART_HEADER_BYTES)) {
            stream_header_sent = true;
        }
        return;
    }

    records_this_packet = TADC_USB_PACKET_BYTES / TADC_UART_RECORD_BYTES;
    if (records_this_packet > TADC_SAMPLE_COUNT - stream_index) {
        records_this_packet = TADC_SAMPLE_COUNT - stream_index;
    }

    for (index = 0U; index < records_this_packet; ++index) {
        build_record(&usb_tx_buffer[index * TADC_UART_RECORD_BYTES],
                     &sample_buffer[stream_index + index]);
    }

    if (usb_transmit(usb_tx_buffer,
                     (uint16_t)(records_this_packet * TADC_UART_RECORD_BYTES))) {
        stream_index += records_this_packet;
        if (stream_index == TADC_SAMPLE_COUNT) {
            stream_final_packet_queued = true;
        }
    }
}

void tadc_capture_init(void)
{
    sample_count = 0U;
    state = TADC_STATE_IDLE;
    stream_index = 0U;
    stream_header_sent = false;
    stream_final_packet_queued = false;
    previous_button_state = HAL_GPIO_ReadPin(TADC_START_GPIO, TADC_START_PIN);

    HAL_GPIO_WritePin(TADC_EN_GPIO, TADC_EN_PIN, GPIO_PIN_RESET);
    led_off();
    cycle_counter_init();

    if (HAL_TIM_IC_Start_IT(&TADC_CKO_TIMER, TADC_CKO_CHANNEL) != HAL_OK) {
        state = TADC_STATE_ERROR;
    }
}

bool tadc_capture_start(void)
{
    if (state != TADC_STATE_IDLE && state != TADC_STATE_DONE) {
        return false;
    }

    __disable_irq();
    sample_count = 0U;
    stream_index = 0U;
    stream_header_sent = false;
    stream_final_packet_queued = false;
    __HAL_TIM_SET_COUNTER(&TADC_CKO_TIMER, 0U);
    __HAL_TIM_SET_COUNTER(&TADC_CLOCK_TIMER, 0U);
    __HAL_TIM_CLEAR_FLAG(&TADC_CKO_TIMER, TIM_FLAG_CC1 | TIM_FLAG_UPDATE);
    state = TADC_STATE_CAPTURING;
    __enable_irq();

    led_on();
    HAL_GPIO_WritePin(TADC_EN_GPIO, TADC_EN_PIN, GPIO_PIN_SET);
    if (HAL_TIM_PWM_Start(&TADC_CLOCK_TIMER, TADC_CLOCK_CHANNEL) != HAL_OK) {
        HAL_GPIO_WritePin(TADC_EN_GPIO, TADC_EN_PIN, GPIO_PIN_RESET);
        state = TADC_STATE_ERROR;
        return false;
    }
    return true;
}

void tadc_capture_task(void)
{
    GPIO_PinState button_state = HAL_GPIO_ReadPin(TADC_START_GPIO, TADC_START_PIN);

    if (previous_button_state == GPIO_PIN_SET && button_state == GPIO_PIN_RESET) {
        HAL_Delay(20U);
        if (HAL_GPIO_ReadPin(TADC_START_GPIO, TADC_START_PIN) == GPIO_PIN_RESET) {
            (void)tadc_capture_start();
        }
    }
    previous_button_state = button_state;

    if (state == TADC_STATE_READY) {
        stream_index = 0U;
        stream_header_sent = false;
        stream_final_packet_queued = false;
        state = TADC_STATE_STREAMING;
    }

    if (state == TADC_STATE_STREAMING) {
        stream_task();
    }
}

tadc_state_t tadc_capture_state(void)
{
    return state;
}

uint32_t tadc_capture_count(void)
{
    return sample_count;
}

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *timer)
{
    uint32_t index;
    uint32_t timestamp;
    uint16_t first_code;
    uint16_t second_code;
    uint16_t flags;

    if (timer->Instance != TIM2 || timer->Channel != HAL_TIM_ACTIVE_CHANNEL_1 ||
        state != TADC_STATE_CAPTURING) {
        return;
    }

    timestamp = HAL_TIM_ReadCapturedValue(timer, TADC_CKO_CHANNEL);
    delay_ns(TADC_DATA_SETTLE_NS);
    first_code = read_adc_bus();
    delay_ns(TADC_DATA_VERIFY_NS);
    second_code = read_adc_bus();
    flags = second_code;
    if (first_code != second_code) {
        flags |= (1U << 9);
    }

    index = sample_count;
    if (index >= TADC_SAMPLE_COUNT) {
        return;
    }

    sample_buffer[index].timestamp = timestamp;
    sample_buffer[index].code_flags = flags;
    sample_buffer[index].reserved = 0U;
    __DMB();
    sample_count = index + 1U;

    if (sample_count == TADC_SAMPLE_COUNT) {
        HAL_GPIO_WritePin(TADC_EN_GPIO, TADC_EN_PIN, GPIO_PIN_RESET);
        (void)HAL_TIM_PWM_Stop(&TADC_CLOCK_TIMER, TADC_CLOCK_CHANNEL);
        state = TADC_STATE_READY;
    }
}
