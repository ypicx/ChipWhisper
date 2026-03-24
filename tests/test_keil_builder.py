from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stm32_agent.keil_builder import (
    _decode_text_output,
    _extract_build_summary,
    _load_target_family,
    read_text_with_fallback,
)


class KeilBuilderEncodingTests(unittest.TestCase):
    def test_decode_text_output_falls_back_to_gb18030(self) -> None:
        self.assertEqual(_decode_text_output("中文报错".encode("gb18030")), "中文报错")

    def test_read_text_with_fallback_handles_gbk_build_log(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            build_log = Path(tmp_dir) / "build.log"
            build_log.write_bytes("main.c(12): error: 中文路径错误".encode("gb18030"))

            self.assertIn("中文路径错误", read_text_with_fallback(build_log))

    def test_extract_build_summary_reads_non_utf8_log_without_garbling(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            build_log = Path(tmp_dir) / "build.log"
            build_log.write_bytes(
                "\n".join(
                    [
                        'compiling main.c...',
                        'main.c(12): error: 中文注释导致报错',
                        'Target not created.',
                        'Build Time Elapsed: 00:00:01',
                    ]
                ).encode("gb18030")
            )

            summary = _extract_build_summary(build_log, "", "")

            self.assertTrue(any("中文注释导致报错" in line for line in summary))
            self.assertTrue(any("Target not created." in line for line in summary))

    def test_load_target_family_raises_when_project_ir_is_missing(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "project_ir.json"
            with self.assertRaisesRegex(ValueError, "cannot determine target family"):
                _load_target_family(missing)


if __name__ == "__main__":
    unittest.main()
