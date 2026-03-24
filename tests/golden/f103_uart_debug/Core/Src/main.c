/*
 * 文件说明：
 * 1. 本文件是整个 STM32 工程的入口。
 * 2. 负责完成 HAL 初始化、系统时钟配置、外设初始化以及应用层调度。
 * 3. 业务逻辑请尽量放到 App/Src/app_main.c 的用户区域中维护。
 */


#include "main.h"

#include "peripherals.h"

#include "app_main.h"


/* 仅在 main.c 需要的附加头文件，请放在下面的用户代码区。 */
/* USER CODE BEGIN MainIncludes */
/* USER CODE END MainIncludes */

/* 系统时钟配置函数声明。具体实现由芯片族/板卡时钟方案生成。 */
static void SystemClock_Config(void);

int main(void)
{
    /* 初始化 HAL 库，建立 SysTick 和底层运行环境。 */
    HAL_Init();
    /* 配置系统主时钟、总线时钟以及 Flash 等待周期。 */
    SystemClock_Config();

    /* 与芯片启动直接相关的底层初始化预留区。 */
    /* USER CODE BEGIN MainInit */
    /* USER CODE END MainInit */

    /* 初始化本工程规划到的所有外设。 */

    MX_GPIO_Init();

    MX_USART1_UART_Init();

    MX_NVIC_Init();


    /* 初始化应用层状态、软件中间件和模块级入口。 */
    App_Init();

    while (1) {
        /* 主循环预留区：建议只放极少量与调度相关的代码。 */
        /* USER CODE BEGIN MainLoop */
        /* USER CODE END MainLoop */
        /* 实际业务逻辑统一放到 App_Loop() 中执行。 */
        App_Loop();
    }
}

static void SystemClock_Config(void)
{
    /* 下面的时钟配置代码由生成器自动填充，请勿手工随意改动。 */
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
        Error_Handler();
    }

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                 | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) {
        Error_Handler();
    }
}

void Error_Handler(void)
{
    /* 出现不可恢复错误时会进入这里。可在用户区补充日志或指示灯处理。 */
    /* USER CODE BEGIN ErrorHandler */
    /* USER CODE END ErrorHandler */
    __disable_irq();
    while (1) {
    }
}

/* 本次规划到的模块清单：

 * - debug_port (uart_debug): Debug UART using one USART TX/RX pair.

 */
