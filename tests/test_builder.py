from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from stm32_agent.builder import (
    build_project,
    doctor_project,
    list_project_builders,
    resolve_builder_kind,
)
from stm32_agent.keil_builder import KeilBuildResult, KeilDoctorResult


class BuilderAbstractionTests(unittest.TestCase):
    def test_list_project_builders_includes_keil_backend(self) -> None:
        builders = list_project_builders()
        self.assertTrue(any(item.kind == "keil" for item in builders))

    def test_resolve_builder_kind_detects_uvprojx_in_directory(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            (project_dir / "demo.uvprojx").write_text("<Project />", encoding="utf-8")
            self.assertEqual(resolve_builder_kind(project_dir), "keil")

    def test_doctor_project_dispatches_to_keil_backend_for_auto(self) -> None:
        expected = KeilDoctorResult(
            ready=True,
            project_dir=r"D:\work\demo",
            uvprojx_path=r"D:\work\demo\demo.uvprojx",
            uv4_path=r"D:\Keil_v5\UV4\UV4.exe",
            fromelf_path=r"D:\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe",
            device_pack_path="",
            build_log_path=r"D:\work\demo\build.log",
            checked_paths=[],
            warnings=[],
            errors=[],
        )
        with patch("stm32_agent.builder.doctor_keil_project", return_value=expected) as mocked:
            result = doctor_project(r"D:\work\demo\demo.uvprojx")
        self.assertIs(result, expected)
        mocked.assert_called_once()

    def test_build_project_reports_unknown_builder_kind(self) -> None:
        result = build_project(r"D:\work\demo", builder_kind="cmake")
        self.assertFalse(result.ready)
        self.assertFalse(result.built)
        self.assertEqual(result.builder_kind, "cmake")
        self.assertTrue(any("Unsupported builder kind" in item for item in result.errors))

    def test_build_project_dispatches_to_keil_backend_for_explicit_kind(self) -> None:
        expected = KeilBuildResult(
            ready=True,
            built=True,
            hex_generated=True,
            project_dir=r"D:\work\demo",
            uvprojx_path=r"D:\work\demo\demo.uvprojx",
            uv4_path=r"D:\Keil_v5\UV4\UV4.exe",
            fromelf_path=r"D:\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe",
            device_pack_path="",
            build_log_path=r"D:\work\demo\build.log",
            hex_file=r"D:\work\demo\Objects\demo.hex",
            command=[],
            hex_command=[],
            exit_code=0,
            summary_lines=["0 Error(s), 0 Warning(s)."],
            warnings=[],
            errors=[],
        )
        with patch("stm32_agent.builder.build_keil_project", return_value=expected) as mocked:
            result = build_project(r"D:\work\demo", builder_kind="keil")
        self.assertIs(result, expected)
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
