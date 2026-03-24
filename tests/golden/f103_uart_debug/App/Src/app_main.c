/*
 * 应用层实现文件：
 * 1. 放置用户业务逻辑、软件中间件调度以及回调函数。
 * 2. 建议优先在 USER CODE 区域中补充业务代码，避免与重新生成冲突。
 */

#include "app_main.h"
#include "main.h"
#include "peripherals.h"
#include "debug_uart.h"

/* 文件级静态变量、局部工具函数等可放在这里。 */
/* USER CODE BEGIN AppTop */
static uint32_t g_last_heartbeat_ms = 0U;
/* USER CODE END AppTop */

void App_Init(void)
{
    /* 应用层初始化入口：先执行用户逻辑，再初始化模块级软件组件。 */
    /* USER CODE BEGIN AppInit */
    (void)DebugUart_WriteLine(&huart1, "stm32_agent renode smoke boot", 100);
    /* USER CODE END AppInit */

    DebugUart_Init(&huart1);
}

void App_Loop(void)
{
    /* 主循环中的应用调度入口：建议保持非阻塞。 */
    /* USER CODE BEGIN AppLoop */
    if ((HAL_GetTick() - g_last_heartbeat_ms) >= 1000U) {
        g_last_heartbeat_ms = HAL_GetTick();
        (void)DebugUart_WriteLine(&huart1, "heartbeat", 100);
    }
    /* USER CODE END AppLoop */

}

/* HAL 回调、模块桥接回调等建议集中放在这里。 */
/* USER CODE BEGIN AppCallbacks */
/* APP_LOGIC_PLACEHOLDER:AppCallbacks */
/* USER CODE END AppCallbacks */
