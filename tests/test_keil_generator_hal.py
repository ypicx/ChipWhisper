from __future__ import annotations

import unittest
from unittest.mock import patch

import stm32_agent.keil_generator_hal as hal
from stm32_agent.catalog import STM32F103C8T6, STM32G431RBT6
from stm32_agent.keil_generator_hal import (
    _render_mx_gpio_init_body,
    _render_can_init_v2,
    _render_with_family_backend,
    _render_dma_setup_lines,
    _render_hal_adc_msp_deinit,
    _render_hal_can_msp_deinit,
    _render_hal_can_msp_init_v2,
    _render_hal_pcd_msp_deinit,
    _render_hal_pcd_msp_init_v2,
    _render_hal_spi_msp_init_v2,
    _render_hal_tim_encoder_msp_init_v2,
    _render_dac_init_v2,
    _render_spi_init_v2,
    _render_system_clock_config,
    _timer_profile_settings_v2,
    _render_tim_oc_init_v2,
    _render_tim_init_v2,
)


class KeilGeneratorHalTests(unittest.TestCase):
    def test_render_system_clock_config_dispatches_by_family(self) -> None:
        f1_lines = _render_system_clock_config(STM32F103C8T6)
        g4_lines = _render_system_clock_config(STM32G431RBT6)

        self.assertTrue(any("RCC_PLL_NONE" in line for line in f1_lines))
        self.assertTrue(any("HAL_PWREx_ControlVoltageScaling" in line for line in g4_lines))

    def test_render_spi_init_v2_dispatches_family_specific_fields(self) -> None:
        spi = {"instance": "SPI1", "handle": "hspi1"}

        f1_rendered = "\n".join(_render_spi_init_v2(spi, STM32F103C8T6))
        g4_rendered = "\n".join(_render_spi_init_v2(spi, STM32G431RBT6))

        self.assertNotIn("Init.CRCLength", f1_rendered)
        self.assertIn("Init.CRCLength", g4_rendered)
        self.assertIn("Init.NSSPMode", g4_rendered)

    def test_render_can_init_v2_dispatches_can_vs_fdcan(self) -> None:
        f1_rendered = "\n".join(
            _render_can_init_v2({"instance": "CAN1", "handle": "hcan1"}, STM32F103C8T6)
        )
        g4_rendered = "\n".join(
            _render_can_init_v2({"instance": "FDCAN1", "handle": "hfdcan1"}, STM32G431RBT6)
        )

        self.assertIn("HAL_CAN_Init(&hcan1)", f1_rendered)
        self.assertIn("HAL_FDCAN_Init(&hfdcan1)", g4_rendered)

    def test_render_hal_can_msp_init_v2_dispatches_signatures(self) -> None:
        can_ports_f1 = [{"instance": "CAN1", "pins": {"tx": "PB9", "rx": "PB8"}}]
        can_ports_g4 = [{"instance": "FDCAN1", "pins": {"tx": "PA12", "rx": "PA11"}}]

        f1_rendered = "\n".join(_render_hal_can_msp_init_v2(can_ports_f1, STM32F103C8T6))
        g4_rendered = "\n".join(_render_hal_can_msp_init_v2(can_ports_g4, STM32G431RBT6))

        self.assertIn("void HAL_CAN_MspInit(CAN_HandleTypeDef* hcan)", f1_rendered)
        self.assertIn("void HAL_FDCAN_MspInit(FDCAN_HandleTypeDef* hfdcan)", g4_rendered)

    def test_render_hal_pcd_msp_init_v2_dispatches_usb_instance_binding(self) -> None:
        usb_devices = [{"instance": "USB_FS", "pins": {"dm": "PA11", "dp": "PA12"}}]

        f1_rendered = "\n".join(_render_hal_pcd_msp_init_v2(usb_devices, STM32F103C8T6))
        g4_rendered = "\n".join(_render_hal_pcd_msp_init_v2(usb_devices, STM32G431RBT6))

        self.assertIn("if (hpcd->Instance == USB)", f1_rendered)
        self.assertIn("__HAL_RCC_USB_CLK_ENABLE();", f1_rendered)
        self.assertIn("if (hpcd->Instance == USB_FS)", g4_rendered)
        self.assertIn("__HAL_RCC_USB_FS_CLK_ENABLE();", g4_rendered)

    def test_render_hal_pcd_msp_deinit_dispatches_usb_instance_binding(self) -> None:
        usb_devices = [{"instance": "USB_FS", "pins": {"dm": "PA11", "dp": "PA12"}}]

        f1_rendered = "\n".join(_render_hal_pcd_msp_deinit(usb_devices, "STM32F1"))
        g4_rendered = "\n".join(_render_hal_pcd_msp_deinit(usb_devices, "STM32G4"))

        self.assertIn("if (hpcd->Instance == USB)", f1_rendered)
        self.assertIn("__HAL_RCC_USB_CLK_DISABLE();", f1_rendered)
        self.assertIn("if (hpcd->Instance == USB_FS)", g4_rendered)
        self.assertIn("__HAL_RCC_USB_FS_CLK_DISABLE();", g4_rendered)

    def test_render_hal_spi_msp_init_v2_dispatches_family_specific_gpio_modes(self) -> None:
        spi_buses = [{"instance": "SPI1", "pins": {"nss": "PA4", "sck": "PA5", "miso": "PA6", "mosi": "PA7"}}]

        f1_rendered = "\n".join(_render_hal_spi_msp_init_v2(spi_buses, STM32F103C8T6))
        g4_rendered = "\n".join(_render_hal_spi_msp_init_v2(spi_buses, STM32G431RBT6))

        self.assertIn("GPIO_MODE_INPUT", f1_rendered)
        self.assertNotIn("GPIO_InitStruct.Alternate = GPIO_AF5_SPI1;", f1_rendered)
        self.assertIn("GPIO_InitStruct.Alternate = GPIO_AF5_SPI1;", g4_rendered)
        self.assertIn("GPIO_SPEED_FREQ_VERY_HIGH", g4_rendered)

    def test_render_hal_can_msp_deinit_dispatches_signatures(self) -> None:
        can_ports_f1 = [{"instance": "CAN1", "pins": {"tx": "PB9", "rx": "PB8"}}]
        can_ports_g4 = [{"instance": "FDCAN1", "pins": {"tx": "PA12", "rx": "PA11"}}]

        f1_rendered = "\n".join(_render_hal_can_msp_deinit(can_ports_f1, "STM32F1"))
        g4_rendered = "\n".join(_render_hal_can_msp_deinit(can_ports_g4, "STM32G4"))

        self.assertIn("void HAL_CAN_MspDeInit(CAN_HandleTypeDef* hcan)", f1_rendered)
        self.assertIn("void HAL_FDCAN_MspDeInit(FDCAN_HandleTypeDef* hfdcan)", g4_rendered)

    def test_render_hal_adc_msp_deinit_dispatches_shared_clock_behavior(self) -> None:
        adc_inputs_f1 = [{"instance": "ADC1", "channels": [{"pin": "PA0"}]}]
        adc_inputs_g4 = [
            {"instance": "ADC1", "channels": [{"pin": "PA0"}]},
            {"instance": "ADC2", "channels": [{"pin": "PA1"}]},
        ]

        f1_rendered = "\n".join(_render_hal_adc_msp_deinit(adc_inputs_f1, "STM32F1"))
        g4_rendered = "\n".join(_render_hal_adc_msp_deinit(adc_inputs_g4, "STM32G4"))

        self.assertIn("__HAL_RCC_ADC1_CLK_DISABLE();", f1_rendered)
        self.assertIn("ADC12 clock is shared by multiple planned ADC instances.", g4_rendered)

    def test_render_tim_init_v2_dispatches_post_init_for_g4_only(self) -> None:
        timer = {
            "timer": "TIM2",
            "handle": "htim2",
            "pwm_profile": "default",
            "channels": [{"channel_macro": "TIM_CHANNEL_1", "pin": "PA0"}],
        }

        f1_rendered = "\n".join(_render_tim_init_v2(timer, STM32F103C8T6))
        g4_rendered = "\n".join(_render_tim_init_v2(timer, STM32G431RBT6))

        self.assertNotIn("HAL_TIM_MspPostInit", f1_rendered)
        self.assertIn("HAL_TIM_MspPostInit(&htim2);", g4_rendered)

    def test_render_tim_oc_init_v2_dispatches_family_specific_fields(self) -> None:
        timer = {
            "timer": "TIM2",
            "handle": "htim2",
            "channels": [{"channel_macro": "TIM_CHANNEL_1"}],
        }

        f1_rendered = "\n".join(_render_tim_oc_init_v2(timer, STM32F103C8T6))
        g4_rendered = "\n".join(_render_tim_oc_init_v2(timer, STM32G431RBT6))

        self.assertIn("Init.Prescaler = 71;", f1_rendered)
        self.assertNotIn("OCNPolarity", f1_rendered)
        self.assertIn("Init.Prescaler = 79;", g4_rendered)
        self.assertIn("OCNPolarity", g4_rendered)

    def test_render_dac_init_v2_dispatches_family_specific_fields(self) -> None:
        dac = {
            "dac": "DAC1",
            "handle": "hdac1",
            "channels": [{"channel_macro": "DAC_CHANNEL_1"}],
        }

        f1_rendered = "\n".join(_render_dac_init_v2(dac, STM32F103C8T6))
        g4_rendered = "\n".join(_render_dac_init_v2(dac, STM32G431RBT6))

        self.assertNotIn("DAC_ConnectOnChipPeripheral", f1_rendered)
        self.assertIn("DAC_ConnectOnChipPeripheral", g4_rendered)
        self.assertIn("DAC_UserTrimming", g4_rendered)

    def test_render_hal_tim_encoder_msp_init_v2_dispatches_pin_mode(self) -> None:
        encoder_timers = [{"timer": "TIM2", "pins": {"ch1": "PA0", "ch2": "PA1"}}]

        f1_rendered = "\n".join(_render_hal_tim_encoder_msp_init_v2(encoder_timers, STM32F103C8T6))
        g4_rendered = "\n".join(_render_hal_tim_encoder_msp_init_v2(encoder_timers, STM32G431RBT6))

        self.assertIn("GPIO_MODE_INPUT", f1_rendered)
        self.assertNotIn("GPIO_InitStruct.Alternate", f1_rendered)
        self.assertIn("GPIO_MODE_AF_PP", g4_rendered)
        self.assertIn("GPIO_InitStruct.Alternate", g4_rendered)

    def test_timer_profile_settings_v2_dispatches_family_specific_motor_pwm(self) -> None:
        self.assertEqual((35, 999, 0), _timer_profile_settings_v2("motor_pwm", "STM32F1"))
        self.assertEqual((79, 999, 0), _timer_profile_settings_v2("motor_pwm", "STM32G4"))

    def test_render_with_family_backend_rejects_missing_supported_family_backend(self) -> None:
        with self.assertRaisesRegex(KeyError, "STM32G4"):
            _render_with_family_backend(
                "STM32G4",
                {
                    "STM32F1": lambda: ["f1"],
                },
            )

    def test_timer_profile_settings_v2_rejects_missing_supported_family_backend(self) -> None:
        with patch.object(hal, "_timer_profile_settings_g4", None):
            with self.assertRaisesRegex(KeyError, "STM32G4"):
                _timer_profile_settings_v2("motor_pwm", "STM32G4")

    def test_render_dma_setup_lines_uses_family_support_flags(self) -> None:
        dma_allocations = [
            {
                "handle": "hdma_test_rx",
                "channel": "DMA1_Channel1",
                "direction": "rx",
                "link_field": "hdmarx",
                "request_macro": "DMA_REQUEST_USART2_RX",
            }
        ]

        f1_rendered = "\n".join(_render_dma_setup_lines(dma_allocations, "huart", "STM32F1"))
        g4_rendered = "\n".join(_render_dma_setup_lines(dma_allocations, "huart", "STM32G4"))

        self.assertNotIn("DMAMUX1", f1_rendered)
        self.assertNotIn("Init.Request", f1_rendered)
        self.assertIn("__HAL_RCC_DMAMUX1_CLK_ENABLE();", g4_rendered)
        self.assertIn("hdma_test_rx.Init.Request = DMA_REQUEST_USART2_RX;", g4_rendered)

    def test_render_mx_gpio_init_body_skips_unused_struct_when_no_direct_gpios(self) -> None:
        rendered = "\n".join(_render_mx_gpio_init_body([]))

        self.assertIn("void MX_GPIO_Init(void)", rendered)
        self.assertNotIn("GPIO_InitTypeDef GPIO_InitStruct = {0};", rendered)
        self.assertIn("No direct GPIO-only signals were requested by the planner.", rendered)


if __name__ == "__main__":
    unittest.main()
