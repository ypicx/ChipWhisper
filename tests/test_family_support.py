from __future__ import annotations

import unittest

from stm32_agent.catalog import STM32F103C8T6, STM32G431RBT6
from stm32_agent.family_support import get_family_support
from stm32_agent.keil_generator import _render_hal_conf_v2


class FamilySupportTests(unittest.TestCase):
    def test_family_support_exposes_can_and_usb_helpers(self) -> None:
        f1 = get_family_support("STM32F1")
        g4 = get_family_support("STM32G4")

        self.assertEqual(f1.cube_package_config_key, "stm32cube_f1_package_path")
        self.assertEqual(f1.build_can_handle_name("CAN1"), "hcan1")
        self.assertEqual(f1.resolve_usb_irq("USB_FS"), "USB_LP_CAN1_RX0_IRQn")

        self.assertEqual(g4.cube_package_config_key, "stm32cube_g4_package_path")
        self.assertEqual(g4.build_can_handle_name("FDCAN1"), "hfdcan1")
        self.assertEqual(g4.resolve_usb_irq("USB_OTG_FS"), "OTG_FS_IRQn")

    def test_render_hal_conf_v2_uses_family_support_settings(self) -> None:
        rendered_f1 = _render_hal_conf_v2(["CAN"], STM32F103C8T6)
        self.assertIn("#define HAL_CAN_MODULE_ENABLED", rendered_f1)
        self.assertIn('#include "stm32f1xx_hal_can.h"', rendered_f1)
        self.assertIn("#define HSE_VALUE 8000000U", rendered_f1)
        self.assertIn("#define LSI_VALUE 40000U", rendered_f1)

        rendered_g4 = _render_hal_conf_v2(["CAN", "PWR"], STM32G431RBT6)
        self.assertIn("#define HAL_FDCAN_MODULE_ENABLED", rendered_g4)
        self.assertIn('#include "stm32g4xx_hal_fdcan.h"', rendered_g4)
        self.assertIn('#include "stm32g4xx_hal_pwr_ex.h"', rendered_g4)
        self.assertIn("#define HSE_VALUE 24000000U", rendered_g4)
        self.assertIn("#define HSI_VALUE 16000000U", rendered_g4)
        self.assertIn("#define LSI_VALUE 32000U", rendered_g4)

    def test_unknown_family_raises_instead_of_silent_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "暂未适配该芯片族"):
            get_family_support("STM32F4")


if __name__ == "__main__":
    unittest.main()
