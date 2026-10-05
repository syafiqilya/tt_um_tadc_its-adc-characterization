#ifndef TADC_CAPTURE_H
#define TADC_CAPTURE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TADC_SAMPLE_COUNT       4096U
#define TADC_TIMER_CLOCK_HZ     10000000UL
#define TADC_ADC_CLOCK_HZ       1000000UL
#define TADC_PROTOCOL_VERSION   3U

typedef enum {
    TADC_STATE_IDLE = 0,
    TADC_STATE_CAPTURING,
    TADC_STATE_READY,
    TADC_STATE_STREAMING,
    TADC_STATE_DONE,
    TADC_STATE_ERROR
} tadc_state_t;

void tadc_capture_init(void);
void tadc_capture_task(void);
bool tadc_capture_start(void);
tadc_state_t tadc_capture_state(void);
uint32_t tadc_capture_count(void);

#ifdef __cplusplus
}
#endif

#endif
