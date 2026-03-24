from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stm32_agent.extension_packs import load_catalog
from stm32_agent.keil_generator import preview_project_file_changes, scaffold_from_request
from stm32_agent.planner import plan_request


class PackPluginTests(unittest.TestCase):
    def test_pack_plugin_can_extend_plan_and_generate_extra_files(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            packs_dir = Path(tmp_dir)
            module_root = packs_dir / "modules" / "plugin_demo"
            module_root.mkdir(parents=True, exist_ok=True)
            (module_root / "module.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "kind": "module",
                        "key": "plugin_demo",
                        "display_name": "Plugin Demo",
                        "summary": "Plugin-generated demo module",
                        "hal_components": [],
                        "template_files": [],
                        "resource_requests": [],
                        "depends_on": [],
                        "simulation": {"renode": {"attach": []}},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (module_root / "plugin.py").write_text(
                """
from __future__ import annotations

def on_plan(context: dict) -> dict:
    return {
        "warnings": ["plugin engaged"],
        "template_files": ["app/plugin_generated.c", "app/plugin_generated.h"],
        "generated_files": {
            "app/plugin_generated.h": "void PluginGenerated_Run(void);\\n",
        },
        "c_init_template": ["    PluginGenerated_Run();"],
    }


def on_generate(context: dict) -> dict:
    return {
        "generated_files": {
            "app/plugin_generated.c": '#include "plugin_generated.h"\\n\\nvoid PluginGenerated_Run(void) {}\\n',
        }
    }
""".strip()
                + "\n",
                encoding="utf-8",
            )
            payload = {
                "chip": "STM32F103C8T6",
                "board": "chip_only",
                "modules": [{"kind": "plugin_demo", "name": "plugin_demo0", "options": {}}],
                "app_logic_goal": "",
                "app_logic": {"AppTop": "", "AppInit": "", "AppLoop": "", "AppCallbacks": ""},
                "generated_files": {},
            }

            plan = plan_request(payload, packs_dir=packs_dir)

            self.assertTrue(plan.feasible)
            self.assertIn("plugin engaged", plan.warnings)
            self.assertIn("app/plugin_generated.c", plan.template_files)
            self.assertIn("app/plugin_generated.h", plan.template_files)
            self.assertIn("app/plugin_generated.h", plan.project_ir["build"]["generated_files"])
            self.assertTrue(plan.project_ir["modules"][0]["plugin_path"].endswith("plugin.py"))

            registry = load_catalog(packs_dir)
            self.assertIn("STM32F103C8T6", registry.chips)
            changes = preview_project_file_changes(plan, packs_dir / "out", chip=registry.chips[plan.chip])
            relative_paths = {item.relative_path for item in changes}
            self.assertIn("App/Inc/plugin_generated.h", relative_paths)
            self.assertIn("App/Src/plugin_generated.c", relative_paths)

            scaffold = scaffold_from_request(payload, packs_dir / "generated_project", packs_dir=packs_dir)
            self.assertTrue(scaffold.feasible)
            self.assertTrue((Path(scaffold.project_dir) / "App" / "Inc" / "plugin_generated.h").exists())
            self.assertTrue((Path(scaffold.project_dir) / "App" / "Src" / "plugin_generated.c").exists())
            self.assertIn("PluginGenerated_Run();", (Path(scaffold.project_dir) / "App" / "Src" / "app_main.c").read_text(encoding="utf-8"))
            self.assertIn("plugin_generated.c", Path(scaffold.project_file).read_text(encoding="utf-8"))
