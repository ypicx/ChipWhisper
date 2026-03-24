from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from stm32_agent.keil_generator import scaffold_from_request


class CodegenSnapshotTests(unittest.TestCase):
    def test_f103_uart_debug_snapshot(self) -> None:
        payload = {
            "chip": "STM32F103C8T6",
            "board": "blue_pill_f103c8",
            "keep_swd": True,
            "modules": [
                {
                    "kind": "uart_debug",
                    "name": "debug_port",
                    "options": {"instance": "USART1"},
                }
            ],
            "requirements": [
                "Build a minimal STM32F103 debug UART project for snapshot testing.",
                "Print a short boot message over USART1 so runtime validation has observable output.",
            ],
            "app_logic_goal": "Emit a boot banner over the debug UART, then print a heartbeat once per second without blocking the loop.",
            "app_logic": {
                "AppTop": "static uint32_t g_last_heartbeat_ms = 0U;",
                "AppInit": '    (void)DebugUart_WriteLine(&huart1, "stm32_agent renode smoke boot", 100);',
                "AppLoop": '    if ((HAL_GetTick() - g_last_heartbeat_ms) >= 1000U) {\n        g_last_heartbeat_ms = HAL_GetTick();\n        (void)DebugUart_WriteLine(&huart1, "heartbeat", 100);\n    }',
                "AppCallbacks": "",
            },
        }

        snapshot_root = Path(__file__).resolve().parent / "golden" / "f103_uart_debug"
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "snapshot_project"
            result = scaffold_from_request(payload, output_dir, project_name="golden_f103_uart_debug")
            self.assertTrue(result.feasible, msg=result.errors)
            project_dir = Path(result.project_dir)

            self._assert_snapshot_file(
                project_dir / "Core" / "Src" / "main.c",
                snapshot_root / "Core" / "Src" / "main.c",
            )
            self._assert_snapshot_file(
                project_dir / "Core" / "Src" / "peripherals.c",
                snapshot_root / "Core" / "Src" / "peripherals.c",
            )
            self._assert_snapshot_file(
                project_dir / "App" / "Src" / "app_main.c",
                snapshot_root / "App" / "Src" / "app_main.c",
            )
            self._assert_snapshot_file(
                project_dir / "Core" / "Inc" / "app_config.h",
                snapshot_root / "Core" / "Inc" / "app_config.h",
            )
            self._assert_snapshot_file(
                project_dir / "MDK-ARM" / "golden_f103_uart_debug.uvprojx",
                snapshot_root / "MDK-ARM" / "golden_f103_uart_debug.uvprojx",
            )

    def _assert_snapshot_file(self, actual_path: Path, expected_path: Path) -> None:
        actual = self._normalize_snapshot_text(actual_path.read_text(encoding="utf-8"))
        expected = self._normalize_snapshot_text(expected_path.read_text(encoding="utf-8"))
        self.assertEqual(expected, actual, msg=f"Snapshot mismatch for {actual_path.name}")

    def _normalize_snapshot_text(self, value: str) -> str:
        normalized = value.replace("\r\n", "\n")
        return normalized.rstrip("\n") + "\n"


if __name__ == "__main__":
    unittest.main()
