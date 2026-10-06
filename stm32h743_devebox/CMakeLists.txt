cmake_minimum_required(VERSION 3.20)

project(tadc_stm32h743_devebox C ASM)

set(STM32CUBEH7_PATH "" CACHE PATH "Path to the STM32CubeH7 repository")
if(NOT STM32CUBEH7_PATH)
    message(FATAL_ERROR "Set STM32CUBEH7_PATH to an STM32CubeH7 checkout")
endif()

set(HAL_ROOT "${STM32CUBEH7_PATH}/Drivers/STM32H7xx_HAL_Driver")
set(CMSIS_ROOT "${STM32CUBEH7_PATH}/Drivers/CMSIS")
set(USB_ROOT "${STM32CUBEH7_PATH}/Middlewares/ST/STM32_USB_Device_Library")

foreach(required_path
        "${HAL_ROOT}/Src/stm32h7xx_hal.c"
        "${CMSIS_ROOT}/Device/ST/STM32H7xx/Include/stm32h743xx.h"
        "${USB_ROOT}/Core/Src/usbd_core.c")
    if(NOT EXISTS "${required_path}")
        message(FATAL_ERROR "Missing STM32CubeH7 dependency: ${required_path}")
    endif()
endforeach()

set(CPU_FLAGS
    -mcpu=cortex-m7
    -mfpu=fpv5-d16
    -mfloat-abi=hard
    -mthumb
)

add_executable(tadc_stm32h743_devebox.elf
    startup_stm32h743vitx.s
    Core/Src/main.c
    Core/Src/stm32h7xx_hal_msp.c
    Core/Src/stm32h7xx_it.c
    Core/Src/syscalls.c
    Core/Src/sysmem.c
    Core/Src/system_stm32h7xx.c
    Core/Src/tadc_capture.c
    Core/Src/usb_device.c
    Core/Src/usbd_cdc_if.c
    Core/Src/usbd_conf.c
    Core/Src/usbd_desc.c
    ${HAL_ROOT}/Src/stm32h7xx_hal.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_cortex.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_exti.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_flash.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_flash_ex.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_gpio.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_pcd.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_pcd_ex.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_pwr.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_pwr_ex.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_rcc.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_rcc_ex.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_tim.c
    ${HAL_ROOT}/Src/stm32h7xx_hal_tim_ex.c
    ${HAL_ROOT}/Src/stm32h7xx_ll_usb.c
    ${USB_ROOT}/Core/Src/usbd_core.c
    ${USB_ROOT}/Core/Src/usbd_ctlreq.c
    ${USB_ROOT}/Core/Src/usbd_ioreq.c
    ${USB_ROOT}/Class/CDC/Src/usbd_cdc.c
)

target_include_directories(tadc_stm32h743_devebox.elf PRIVATE
    Core/Inc
    ${HAL_ROOT}/Inc
    ${HAL_ROOT}/Inc/Legacy
    ${CMSIS_ROOT}/Core/Include
    ${CMSIS_ROOT}/Device/ST/STM32H7xx/Include
    ${USB_ROOT}/Core/Inc
    ${USB_ROOT}/Class/CDC/Inc
)

target_compile_definitions(tadc_stm32h743_devebox.elf PRIVATE
    USE_HAL_DRIVER
    USE_PWR_LDO_SUPPLY
    USE_USB_FS
    STM32H743xx
)

target_compile_options(tadc_stm32h743_devebox.elf PRIVATE
    ${CPU_FLAGS}
    -O2
    -ffunction-sections
    -fdata-sections
    -fstack-usage
    -Wall
    -Wextra
)

target_link_options(tadc_stm32h743_devebox.elf PRIVATE
    ${CPU_FLAGS}
    -T${CMAKE_CURRENT_SOURCE_DIR}/STM32H743VITX_FLASH.ld
    --specs=nano.specs
    --specs=nosys.specs
    -Wl,--gc-sections
    -Wl,--print-memory-usage
    -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/tadc_stm32h743_devebox.map
)

set_target_properties(tadc_stm32h743_devebox.elf PROPERTIES
    LINK_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/STM32H743VITX_FLASH.ld"
)

add_custom_command(TARGET tadc_stm32h743_devebox.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O ihex
            $<TARGET_FILE:tadc_stm32h743_devebox.elf>
            ${CMAKE_CURRENT_BINARY_DIR}/tadc_stm32h743_devebox.hex
    COMMAND ${CMAKE_OBJCOPY} -O binary
            $<TARGET_FILE:tadc_stm32h743_devebox.elf>
            ${CMAKE_CURRENT_BINARY_DIR}/tadc_stm32h743_devebox.bin
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:tadc_stm32h743_devebox.elf>
    VERBATIM
)
