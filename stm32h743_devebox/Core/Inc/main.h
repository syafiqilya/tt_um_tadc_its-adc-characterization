#ifndef MAIN_H
#define MAIN_H

#include "stm32h7xx_hal.h"

void Error_Handler(void);
void HAL_TIM_MspPostInit(TIM_HandleTypeDef *timer);

#endif
