from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from .catalog import ChipDefinition
from .extension_packs import load_catalog
from .family_support import get_family_support
from .keil_generator_docs import (
    render_drivers_readme_v2 as _render_drivers_readme_v2,
    render_generated_readme_v2 as _render_generated_readme_v2,
    render_project_report as _render_project_report,
)
from .keil_generator_makefile import render_linker_script, render_makefile
from .keil_generator_core import (
    render_hal_msp_c_v2 as _render_hal_msp_c_template_v2,
    render_it_c_v2 as _render_it_c_template_v2,
    render_it_h_v2 as _render_it_h_template_v2,
    render_main_c_v2 as _render_main_c_template_v2,
    render_main_h_v2 as _render_main_h_template_v2,
)
from .keil_generator_hal import (
    _render_adc_init_v2,
    _render_can_init_v2,
    _render_dac_init_v2,
    _render_hal_adc_msp_init_v2,
    _render_hal_can_msp_init_v2,
    _render_hal_dac_msp_init_v2,
    _render_hal_i2c_msp_init_v2,
    _render_hal_pcd_msp_init_v2,
    _render_hal_spi_msp_init_v2,
    _render_hal_tim_encoder_msp_init_v2,
    _render_hal_tim_ic_msp_init_v2,
    _render_hal_tim_oc_msp_init_v2,
    _render_hal_tim_pwm_msp_init_v2,
    _render_hal_uart_msp_init_v2,
    _render_i2c_init_v2,
    _render_mx_gpio_init_body,
    _render_spi_init_v2,
    _render_system_clock_config,
    _render_tim_encoder_init_v2,
    _render_tim_ic_init_v2,
    _render_tim_oc_init_v2,
    _render_tim_init_v2,
    _render_uart_init_v2,
    _render_usb_pcd_init_v2,
)
from .keil_generator_app import (
    _render_app_init_calls_v2,
    _render_app_loop_lines_v2,
    _render_app_main_c,
    _render_app_main_h,
    _render_app_top_lines_v2,
)
from .keil_generator_app_config import render_app_config_v2 as _render_app_config_template_v2
from .keil_generator_context import (
    CodegenContext,
    _build_codegen_context,
    _can_handle_type,
    _group_exti_irqs,
)
from .keil_generator_peripherals import (
    render_peripherals_c_v2 as _render_peripherals_c_v2,
    render_peripherals_h_v2 as _render_peripherals_h_v2,
)
from .keil_generator_project import (
    assemble_project_files_to_write as _assemble_project_files_to_write,
    project_directories as _project_directories,
)
from .keil_generator_uvprojx import render_uvprojx_v2 as _render_uvprojx_v2
from .planner import PlanResult, plan_request

@dataclass
class ScaffoldResult:
    feasible: bool
    project_dir: str
    project_file: str
    report_file: str
    summary: str
    warnings: List[str]
    errors: List[str]
    generated_files: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "feasible": self.feasible,
            "project_dir": self.project_dir,
            "project_file": self.project_file,
            "report_file": self.report_file,
            "summary": self.summary,
            "warnings": self.warnings,
            "errors": self.errors,
            "generated_files": self.generated_files,
        }


@dataclass(frozen=True)
class ProjectFileChange:
    path: str
    relative_path: str
    status: str
    change_summary: str = ""
    diff_preview: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "status": self.status,
            "change_summary": self.change_summary,
            "diff_preview": self.diff_preview,
        }


def _user_code_block(name: str, indent: str = "") -> List[str]:
    return [
        f"{indent}/* USER CODE BEGIN {name} */",
        f"{indent}/* USER CODE END {name} */",
    ]


def _join_code_block(lines: Iterable[str]) -> str:
    return "\n".join(str(line) for line in lines)


def scaffold_from_request(
    payload: Dict[str, object],
    output_dir: str | Path,
    project_name: str | None = None,
    packs_dir: str | Path | None = None,
    generate_makefile: bool = False,
    ) -> ScaffoldResult:
    registry = load_catalog(packs_dir)
    plan = plan_request(payload, packs_dir=packs_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not plan.feasible:
        return ScaffoldResult(
            feasible=False,
            project_dir=str(output_path),
            project_file="",
            report_file="",
            summary="规划失败，未生成 Keil 工程骨架",
            warnings=plan.warnings,
            errors=plan.errors,
            generated_files=[],
        )

    resolved_project_name = _sanitize_project_name(project_name or output_path.name or "stm32_project")
    if resolved_project_name != output_path.name:
        output_path = output_path / resolved_project_name
        output_path.mkdir(parents=True, exist_ok=True)

    chip = registry.chips[plan.chip]
    generated_files: List[str] = []
    try:
        generated_files.extend(_write_project_files(plan, output_path, resolved_project_name, chip, generate_makefile=generate_makefile))
    except ValueError as exc:
        return ScaffoldResult(
            feasible=False,
            project_dir=str(output_path),
            project_file="",
            report_file="",
            summary="Keil project generation was blocked by an unsupported chip family.",
            warnings=plan.warnings,
            errors=[str(exc)],
            generated_files=[],
        )

    return ScaffoldResult(
        feasible=True,
        project_dir=str(output_path),
        project_file=str(output_path / "MDK-ARM" / f"{resolved_project_name}.uvprojx"),
        report_file=str(output_path / "REPORT.generated.md"),
        summary=f"已生成 {resolved_project_name} 的 Keil5 工程骨架",
        warnings=plan.warnings,
        errors=[],
        generated_files=generated_files,
    )


def preview_project_file_changes(
    plan: PlanResult,
    output_dir: str | Path,
    chip: ChipDefinition,
    project_name: str | None = None,
) -> List[ProjectFileChange]:
    output_path = Path(output_dir)
    resolved_project_name = _sanitize_project_name(project_name or output_path.name or "stm32_project")
    if resolved_project_name != output_path.name:
        output_path = output_path / resolved_project_name

    files_to_write = _build_project_files_to_write(plan, output_path, resolved_project_name, chip)
    changes: List[ProjectFileChange] = []
    for path, content in files_to_write.items():
        existing = ""
        if not path.exists():
            status = "create"
        else:
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError:
                status = "update"
            else:
                status = "unchanged" if existing == content else "update"
        changes.append(
            ProjectFileChange(
                path=str(path),
                relative_path=path.relative_to(output_path).as_posix(),
                status=status,
                change_summary=_summarize_project_file_change(status, existing, content),
                diff_preview=_build_project_file_diff_preview(
                    path.relative_to(output_path).as_posix(),
                    status,
                    existing,
                    content,
                ),
            )
        )
    changes.sort(key=lambda item: (item.status, item.relative_path))
    return changes


def _summarize_project_file_change(status: str, existing: str, content: str) -> str:
    existing_lines = len(existing.splitlines())
    content_lines = len(content.splitlines())
    if status == "create":
        return f"新建文件，预计写入 {content_lines} 行。"
    if status == "unchanged":
        return f"内容未变化，保持 {content_lines} 行。"
    added = max(0, content_lines - existing_lines)
    removed = max(0, existing_lines - content_lines)
    if added or removed:
        return f"预计改动 {content_lines} 行（新增 {added}，减少 {removed}）。"
    return f"预计更新文件，共 {content_lines} 行。"


def _build_project_file_diff_preview(
    relative_path: str,
    status: str,
    existing: str,
    content: str,
    *,
    context_lines: int = 3,
    max_lines: int = 160,
) -> str:
    if status == "unchanged":
        return "当前文件内容未发生变化。"

    before_lines = existing.splitlines()
    after_lines = content.splitlines()
    from_path = "/dev/null" if status == "create" and not existing else f"a/{relative_path}"
    to_path = f"b/{relative_path}"
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_path,
            tofile=to_path,
            n=context_lines,
            lineterm="",
        )
    )
    if not diff_lines:
        return "当前预览无法生成可展示的差异。"
    if len(diff_lines) > max_lines:
        hidden = len(diff_lines) - max_lines
        diff_lines = [*diff_lines[:max_lines], f"... ({hidden} more diff lines hidden)"]
    return "\n".join(diff_lines)


def _write_project_files(plan: PlanResult, root: Path, project_name: str, chip: ChipDefinition, *, generate_makefile: bool = False) -> List[str]:
    generated: List[str] = []
    dirs = _project_directories(root)
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
    files_to_write = _build_project_files_to_write(plan, root, project_name, chip, generate_makefile=generate_makefile)

    for path, content in files_to_write.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        generated.append(str(path))

    return generated


def _build_project_files_to_write(plan: PlanResult, root: Path, project_name: str, chip: ChipDefinition, *, generate_makefile: bool = False) -> Dict[Path, str]:
    context = _build_codegen_context(plan, chip)
    support = context.support

    rendered_files: Dict[str, str] = {
        "project_ir.json": json.dumps(plan.project_ir, ensure_ascii=False, indent=2) + "\n",
        "README.generated.md": _render_generated_readme_v2(project_name, chip),
        "REPORT.generated.md": _render_project_report(plan, project_name, chip),
        "Drivers/README.md": _render_drivers_readme_v2(chip),
        "Core/Inc/main.h": _render_main_h_v2(chip, context),
        "Core/Inc/peripherals.h": _render_peripherals_h(plan, chip, context),
        f"Core/Inc/{support.it_header}": _render_it_h_v2(plan, chip, context),
        "Core/Inc/app_config.h": _render_app_config(plan),
        f"Core/Inc/{support.hal_conf_header}": _render_hal_conf_v2(plan.hal_components, chip, plan),
        "Core/Src/main.c": _render_main_c_v2(plan, chip, context),
        "Core/Src/peripherals.c": _render_peripherals_c(plan, chip, context),
        f"Core/Src/{support.it_source}": _render_it_c_v2(plan, chip, context),
        f"Core/Src/{support.hal_msp_source}": _render_hal_msp_c_v2(chip, context),
        "App/Inc/app_main.h": _render_app_main_h(),
        "App/Src/app_main.c": _render_app_main_c(plan, context.app_headers, context.module_headers),
        f"MDK-ARM/{project_name}.uvprojx": _render_uvprojx_v2(
            plan,
            project_name,
            chip,
            context.hal_sources,
            context.app_sources,
            context.module_sources,
        ),
        "MDK-ARM/build_keil.ps1": _render_build_ps1(project_name),
        "MDK-ARM/flash_keil.ps1": _render_flash_ps1(project_name),
    }

    if generate_makefile:
        rendered_files["Makefile"] = render_makefile(
            plan,
            project_name,
            chip,
            context.hal_sources,
            context.app_sources,
            context.module_sources,
        )
        rendered_files["STM32_FLASH.ld"] = render_linker_script(chip)
    return _assemble_project_files_to_write(plan, root, context, rendered_files, chip)


def _sanitize_project_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return clean or "stm32_project"











def _render_peripherals_h(
    plan: PlanResult,
    chip: ChipDefinition | None = None,
    context: CodegenContext | None = None,
) -> str:
    context = context or _build_codegen_context(plan, chip)

    handle_declarations: List[str] = []
    for bus in context.i2c_buses:
        handle_declarations.append(f"extern I2C_HandleTypeDef {bus['handle']};")
    for bus in context.spi_buses:
        handle_declarations.append(f"extern SPI_HandleTypeDef {bus['handle']};")
    for uart in context.uart_ports:
        handle_declarations.append(f"extern UART_HandleTypeDef {uart['handle']};")
    for adc in context.adc_inputs:
        handle_declarations.append(f"extern ADC_HandleTypeDef {adc['handle']};")
    for dac in context.dac_units:
        handle_declarations.append(f"extern DAC_HandleTypeDef {dac['handle']};")
    for can in context.can_ports:
        handle_declarations.append(f"extern {_can_handle_type(plan, can)} {can['handle']};")
    for usb in context.usb_devices:
        handle_declarations.append(f"extern PCD_HandleTypeDef {usb['handle']};")
    for timer in context.pwm_timers:
        handle_declarations.append(f"extern TIM_HandleTypeDef {timer['handle']};")
    for timer in context.timer_oc_timers:
        handle_declarations.append(f"extern TIM_HandleTypeDef {timer['handle']};")
    for timer in context.timer_ic_timers:
        handle_declarations.append(f"extern TIM_HandleTypeDef {timer['handle']};")
    for timer in context.encoder_timers:
        handle_declarations.append(f"extern TIM_HandleTypeDef {timer['handle']};")
    for dma in context.dma_allocations:
        handle_declarations.append(f"extern DMA_HandleTypeDef {dma['handle']};")

    function_declarations = ["void MX_GPIO_Init(void);"]
    for bus in context.i2c_buses:
        function_declarations.append(f"void MX_{bus['instance']}_Init(void);")
    for bus in context.spi_buses:
        function_declarations.append(f"void MX_{bus['instance']}_Init(void);")
    for uart in context.uart_ports:
        function_declarations.append(f"void MX_{uart['instance']}_UART_Init(void);")
    for adc in context.adc_inputs:
        function_declarations.append(f"void MX_{adc['instance']}_Init(void);")
    for dac in context.dac_units:
        function_declarations.append(f"void MX_{dac['dac']}_Init(void);")
    for can in context.can_ports:
        function_declarations.append(f"void MX_{can['instance']}_Init(void);")
    for usb in context.usb_devices:
        function_declarations.append(f"void MX_{usb['instance']}_Init(void);")
    for timer in context.pwm_timers:
        function_declarations.append(f"void MX_{timer['timer']}_Init(void);")
    for timer in context.timer_oc_timers:
        function_declarations.append(f"void MX_{timer['timer']}_OC_Init(void);")
    for timer in context.timer_ic_timers:
        function_declarations.append(f"void MX_{timer['timer']}_IC_Init(void);")
    for timer in context.encoder_timers:
        function_declarations.append(f"void MX_{timer['timer']}_Encoder_Init(void);")
    if context.irqs:
        function_declarations.append("void MX_NVIC_Init(void);")

    return _render_peripherals_h_v2(handle_declarations, function_declarations)


def _render_peripherals_c(
    plan: PlanResult,
    chip: ChipDefinition | None = None,
    context: CodegenContext | None = None,
) -> str:
    context = context or _build_codegen_context(plan, chip)

    handle_definitions: List[str] = []
    for bus in context.i2c_buses:
        handle_definitions.append(f"I2C_HandleTypeDef {bus['handle']};")
    for bus in context.spi_buses:
        handle_definitions.append(f"SPI_HandleTypeDef {bus['handle']};")
    for uart in context.uart_ports:
        handle_definitions.append(f"UART_HandleTypeDef {uart['handle']};")
    for adc in context.adc_inputs:
        handle_definitions.append(f"ADC_HandleTypeDef {adc['handle']};")
    for dac in context.dac_units:
        handle_definitions.append(f"DAC_HandleTypeDef {dac['handle']};")
    for can in context.can_ports:
        handle_definitions.append(f"{_can_handle_type(plan, can)} {can['handle']};")
    for usb in context.usb_devices:
        handle_definitions.append(f"PCD_HandleTypeDef {usb['handle']};")
    for timer in context.pwm_timers:
        handle_definitions.append(f"TIM_HandleTypeDef {timer['handle']};")
    for timer in context.timer_oc_timers:
        handle_definitions.append(f"TIM_HandleTypeDef {timer['handle']};")
    for timer in context.timer_ic_timers:
        handle_definitions.append(f"TIM_HandleTypeDef {timer['handle']};")
    for timer in context.encoder_timers:
        handle_definitions.append(f"TIM_HandleTypeDef {timer['handle']};")
    for dma in context.dma_allocations:
        handle_definitions.append(f"DMA_HandleTypeDef {dma['handle']};")

    init_blocks = [_join_code_block(_render_mx_gpio_init_body(context.direct_gpios))]
    for bus in context.i2c_buses:
        init_blocks.append(_join_code_block(_render_i2c_init_v2(bus, chip)))
    for bus in context.spi_buses:
        init_blocks.append(_join_code_block(_render_spi_init_v2(bus, chip)))
    for uart in context.uart_ports:
        init_blocks.append(_join_code_block(_render_uart_init_v2(uart, chip)))
    for adc in context.adc_inputs:
        init_blocks.append(_join_code_block(_render_adc_init_v2(adc, chip)))
    for dac in context.dac_units:
        init_blocks.append(_join_code_block(_render_dac_init_v2(dac, chip)))
    for can in context.can_ports:
        init_blocks.append(_join_code_block(_render_can_init_v2(can, chip)))
    for usb in context.usb_devices:
        init_blocks.append(_join_code_block(_render_usb_pcd_init_v2(usb, chip)))
    for timer in context.pwm_timers:
        init_blocks.append(_join_code_block(_render_tim_init_v2(timer, chip)))
    for timer in context.timer_oc_timers:
        init_blocks.append(_join_code_block(_render_tim_oc_init_v2(timer, chip)))
    for timer in context.timer_ic_timers:
        init_blocks.append(_join_code_block(_render_tim_ic_init_v2(timer, chip)))
    for timer in context.encoder_timers:
        init_blocks.append(_join_code_block(_render_tim_encoder_init_v2(timer, chip)))
    if context.irqs:
        init_blocks.append(_join_code_block(_render_mx_nvic_init_body(context.irqs)))

    msp_blocks: List[str] = []
    if context.i2c_buses:
        msp_blocks.append(_join_code_block(_render_hal_i2c_msp_init_v2(context.i2c_buses, chip, dma_allocations=context.dma_allocations)))
    if context.spi_buses:
        msp_blocks.append(_join_code_block(_render_hal_spi_msp_init_v2(context.spi_buses, chip)))
    if context.uart_ports:
        msp_blocks.append(_join_code_block(_render_hal_uart_msp_init_v2(context.uart_ports, chip, dma_allocations=context.dma_allocations)))
    if context.adc_inputs:
        msp_blocks.append(_join_code_block(_render_hal_adc_msp_init_v2(context.adc_inputs, chip)))
    if context.dac_units:
        msp_blocks.append(_join_code_block(_render_hal_dac_msp_init_v2(context.dac_units, chip)))
    if context.can_ports:
        msp_blocks.append(_join_code_block(_render_hal_can_msp_init_v2(context.can_ports, chip)))
    if context.usb_devices:
        msp_blocks.append(_join_code_block(_render_hal_pcd_msp_init_v2(context.usb_devices, chip)))
    if context.pwm_timers:
        msp_blocks.append(_join_code_block(_render_hal_tim_pwm_msp_init_v2(context.pwm_timers, chip)))
    if context.timer_oc_timers:
        msp_blocks.append(_join_code_block(_render_hal_tim_oc_msp_init_v2(context.timer_oc_timers, chip)))
    if context.timer_ic_timers:
        msp_blocks.append(_join_code_block(_render_hal_tim_ic_msp_init_v2(context.timer_ic_timers, chip)))
    if context.encoder_timers:
        msp_blocks.append(_join_code_block(_render_hal_tim_encoder_msp_init_v2(context.encoder_timers, chip)))

    return _render_peripherals_c_v2(
        handle_definitions=handle_definitions,
        user_code_top=_join_code_block(_user_code_block("PeripheralsTop")),
        gpio_init_block=_join_code_block(_render_mx_gpio_init_body(context.direct_gpios)),
        init_blocks=init_blocks[1:],
        msp_blocks=msp_blocks,
        user_code_bottom=_join_code_block(_user_code_block("PeripheralsBottom")) + "\n",
    )


def _render_app_config(plan: PlanResult) -> str:
    return _render_app_config_template_v2(plan)


def _render_main_h_v2(chip: ChipDefinition, context: CodegenContext | None = None) -> str:
    support = context.support if context is not None else get_family_support(chip.family)
    return _render_main_h_template_v2(
        main_hal_header=support.main_hal_header,
        extra_headers=list(support.main_extra_includes),
    )


def _render_it_h_v2(
    plan: PlanResult,
    chip: ChipDefinition | None = None,
    context: CodegenContext | None = None,
) -> str:
    context = context or _build_codegen_context(plan, chip)
    support = context.support
    guard = support.it_header.replace(".", "_").upper()
    handler_declarations = ["void SysTick_Handler(void);"]
    for dma in context.dma_allocations:
        handler_declarations.append(f"void {dma['irq_handler']}(void);")
    for exti in _group_exti_irqs(plan):
        handler_declarations.append(f"void {exti['irq_handler']}(void);")
    for uart in context.uart_ports:
        handler_declarations.append(f"void {uart['instance']}_IRQHandler(void);")
    for usb in context.usb_devices:
        irq_handler = str(usb.get("irq_handler", "")).strip()
        if irq_handler:
            handler_declarations.append(f"void {irq_handler}(void);")
    for timer in context.timer_ic_timers:
        handler_declarations.append(f"void {str(timer['irq']).replace('_IRQn', '_IRQHandler')}(void);")
    return _render_it_h_template_v2(
        guard=guard,
        handler_declarations=handler_declarations,
    )


def _render_main_c_v2(
    plan: PlanResult,
    chip: ChipDefinition,
    context: CodegenContext | None = None,
) -> str:
    context = context or _build_codegen_context(plan, chip)
    init_calls = ["    MX_GPIO_Init();"]
    for bus in context.i2c_buses:
        init_calls.append(f"    MX_{bus['instance']}_Init();")
    for bus in context.spi_buses:
        init_calls.append(f"    MX_{bus['instance']}_Init();")
    for uart in context.uart_ports:
        init_calls.append(f"    MX_{uart['instance']}_UART_Init();")
    for adc in context.adc_inputs:
        init_calls.append(f"    MX_{adc['instance']}_Init();")
    for dac in context.dac_units:
        init_calls.append(f"    MX_{dac['dac']}_Init();")
    for can in context.can_ports:
        init_calls.append(f"    MX_{can['instance']}_Init();")
    for usb in context.usb_devices:
        init_calls.append(f"    MX_{usb['instance']}_Init();")
    for timer in context.pwm_timers:
        init_calls.append(f"    MX_{timer['timer']}_Init();")
    for timer in context.timer_oc_timers:
        init_calls.append(f"    MX_{timer['timer']}_OC_Init();")
    for timer in context.timer_ic_timers:
        init_calls.append(f"    MX_{timer['timer']}_IC_Init();")
    for timer in context.encoder_timers:
        init_calls.append(f"    MX_{timer['timer']}_Encoder_Init();")
    if context.irqs:
        init_calls.append("    MX_NVIC_Init();")

    planned_modules = []
    for module in plan.project_ir.get("modules", []):
        if not isinstance(module, dict):
            continue
        planned_modules.append(
            {
                "name": str(module.get("name", "")),
                "kind": str(module.get("kind", "")),
                "summary": str(module.get("summary", "")),
            }
        )

    return _render_main_c_template_v2(
        include_lines=[
            '#include "main.h"',
            '#include "peripherals.h"',
            '#include "app_main.h"',
        ],
        main_init_block=_join_code_block(_user_code_block("MainInit", "    ")),
        init_calls=init_calls,
        system_clock_block=_join_code_block(_render_system_clock_config(chip, plan)),
        planned_modules=planned_modules,
    )


def _render_it_c_v2(
    plan: PlanResult,
    chip: ChipDefinition | None = None,
    context: CodegenContext | None = None,
) -> str:
    context = context or _build_codegen_context(plan, chip)
    support = context.support
    interrupt_blocks: List[str] = []
    for dma in context.dma_allocations:
        irq_handler = str(dma["irq_handler"])
        handle = str(dma["handle"])
        interrupt_blocks.append(
            _join_code_block(
                [
                    f"void {irq_handler}(void)",
                    "{",
                    f"    /* USER CODE BEGIN {irq_handler}_Pre */",
                    f"    /* USER CODE END {irq_handler}_Pre */",
                    f"    HAL_DMA_IRQHandler(&{handle});",
                    f"    /* USER CODE BEGIN {irq_handler}_Post */",
                    f"    /* USER CODE END {irq_handler}_Post */",
                    "}",
                ]
            )
        )
    for exti in _group_exti_irqs(plan):
        irq_handler = str(exti["irq_handler"])
        block_lines = [
            f"void {irq_handler}(void)",
            "{",
            f"    /* USER CODE BEGIN {irq_handler}_Pre */",
            f"    /* USER CODE END {irq_handler}_Pre */",
        ]
        for pin_macro in exti["pin_macros"]:
            block_lines.append(f"    HAL_GPIO_EXTI_IRQHandler({pin_macro});")
        block_lines.extend(
            [
                f"    /* USER CODE BEGIN {irq_handler}_Post */",
                f"    /* USER CODE END {irq_handler}_Post */",
                "}",
            ]
        )
        interrupt_blocks.append(_join_code_block(block_lines))
    for uart in context.uart_ports:
        instance = str(uart["instance"])
        handle = str(uart["handle"])
        interrupt_blocks.append(
            _join_code_block(
                [
                    f"void {instance}_IRQHandler(void)",
                    "{",
                    f"    /* USER CODE BEGIN {instance}_IRQHandler_Pre */",
                    f"    /* USER CODE END {instance}_IRQHandler_Pre */",
                    f"    HAL_UART_IRQHandler(&{handle});",
                    f"    /* USER CODE BEGIN {instance}_IRQHandler_Post */",
                    f"    /* USER CODE END {instance}_IRQHandler_Post */",
                    "}",
                ]
            )
        )
    for usb in context.usb_devices:
        irq_handler = str(usb.get("irq_handler", "")).strip()
        handle = str(usb.get("handle", "")).strip()
        if not irq_handler or not handle:
            continue
        interrupt_blocks.append(
            _join_code_block(
                [
                    f"void {irq_handler}(void)",
                    "{",
                    f"    /* USER CODE BEGIN {irq_handler}_Pre */",
                    f"    /* USER CODE END {irq_handler}_Pre */",
                    f"    HAL_PCD_IRQHandler(&{handle});",
                    f"    /* USER CODE BEGIN {irq_handler}_Post */",
                    f"    /* USER CODE END {irq_handler}_Post */",
                    "}",
                ]
            )
        )
    for timer in context.timer_ic_timers:
        irq = str(timer["irq"])
        handle = str(timer["handle"])
        irq_handler = irq.replace("_IRQn", "_IRQHandler")
        interrupt_blocks.append(
            _join_code_block(
                [
                    f"void {irq_handler}(void)",
                    "{",
                    f"    /* USER CODE BEGIN {irq_handler}_Pre */",
                    f"    /* USER CODE END {irq_handler}_Pre */",
                    f"    HAL_TIM_IRQHandler(&{handle});",
                    f"    /* USER CODE BEGIN {irq_handler}_Post */",
                    f"    /* USER CODE END {irq_handler}_Post */",
                    "}",
                ]
            )
        )
    return _render_it_c_template_v2(
        include_lines=[
            '#include "main.h"',
            '#include "peripherals.h"',
            f'#include "{support.it_header}"',
        ],
        interrupt_blocks=interrupt_blocks,
    )


def _render_hal_msp_c_v2(chip: ChipDefinition, context: CodegenContext | None = None) -> str:
    support = context.support if context is not None else get_family_support(chip.family)
    return _render_hal_msp_c_template_v2(list(support.global_msp_init_lines))


def _render_hal_conf_v2(components: Iterable[str], chip: ChipDefinition, plan: PlanResult | None = None) -> str:
    support = get_family_support(chip.family)
    requested = set(components)
    requested.update(support.implicit_hal_components)
    if "TIM" in requested:
        requested.add("DMA")

    module_macros = ["HAL_MODULE_ENABLED", "HAL_CORTEX_MODULE_ENABLED", "HAL_RCC_MODULE_ENABLED"]
    if "FLASH" in requested:
        module_macros.append("HAL_FLASH_MODULE_ENABLED")
    if "GPIO" in requested:
        module_macros.append("HAL_GPIO_MODULE_ENABLED")
    if "DMA" in requested:
        module_macros.append("HAL_DMA_MODULE_ENABLED")
    if "ADC" in requested:
        module_macros.append("HAL_ADC_MODULE_ENABLED")
    if "I2C" in requested:
        module_macros.append("HAL_I2C_MODULE_ENABLED")
    if "SPI" in requested:
        module_macros.append("HAL_SPI_MODULE_ENABLED")
    if "USART" in requested:
        module_macros.append("HAL_UART_MODULE_ENABLED")
    if "DAC" in requested:
        module_macros.append("HAL_DAC_MODULE_ENABLED")
    if "CAN" in requested:
        module_macros.append(support.hal_can_module_macro)
    if "PCD" in requested:
        module_macros.append("HAL_PCD_MODULE_ENABLED")
    if "TIM" in requested:
        module_macros.append("HAL_TIM_MODULE_ENABLED")
    if "PWR" in requested:
        module_macros.append("HAL_PWR_MODULE_ENABLED")
    if "EXTI" in requested:
        module_macros.append("HAL_EXTI_MODULE_ENABLED")

    include_names = [f"{support.hal_prefix}_hal_rcc.h", f"{support.hal_prefix}_hal_cortex.h"]
    if "FLASH" in requested:
        include_names.extend([f"{support.hal_prefix}_hal_flash.h", f"{support.hal_prefix}_hal_flash_ex.h"])
    if "GPIO" in requested:
        include_names.append(f"{support.hal_prefix}_hal_gpio.h")
    if "DMA" in requested:
        include_names.append(f"{support.hal_prefix}_hal_dma.h")
    if "ADC" in requested:
        include_names.extend([f"{support.hal_prefix}_hal_adc.h", f"{support.hal_prefix}_hal_adc_ex.h"])
    if "I2C" in requested:
        include_names.append(f"{support.hal_prefix}_hal_i2c.h")
    if "SPI" in requested:
        include_names.append(f"{support.hal_prefix}_hal_spi.h")
    if "USART" in requested:
        include_names.append(f"{support.hal_prefix}_hal_uart.h")
    if "DAC" in requested:
        include_names.extend([f"{support.hal_prefix}_hal_dac.h", f"{support.hal_prefix}_hal_dac_ex.h"])
    if "CAN" in requested:
        include_names.append(support.hal_can_header)
    if "PCD" in requested:
        include_names.append(f"{support.hal_prefix}_hal_pcd.h")
    if "TIM" in requested:
        include_names.append(f"{support.hal_prefix}_hal_tim.h")
    if "PWR" in requested:
        include_names.append(f"{support.hal_prefix}_hal_pwr.h")
        include_names.extend(support.hal_pwr_extra_headers)
    if "EXTI" in requested:
        include_names.append(f"{support.hal_prefix}_hal_exti.h")

    include_body = "\n".join(f'#include "{name}"' for name in include_names)
    body = "\n".join(f"#define {macro}" for macro in module_macros)
    guard = support.hal_conf_header.replace(".", "_").upper()
    clock_plan = _clock_plan_values(plan)
    hse_value = f"{int(clock_plan.get('hse_value', support.default_hse_value))}U"
    hsi_value = f"{int(clock_plan.get('hsi_value', support.default_hsi_value))}U"
    lsi_value = f"{int(clock_plan.get('lsi_value', support.default_lsi_value))}U"
    lse_value = f"{int(clock_plan.get('lse_value', 32768))}U"
    external_clock_value = f"{int(clock_plan.get('external_clock_value', 48000))}U"

    return f"""#ifndef __{guard}
#define __{guard}

#ifdef __cplusplus
extern "C" {{
#endif

{body}

#if !defined(HSE_VALUE)
#define HSE_VALUE {hse_value}
#endif

#if !defined(HSI_VALUE)
#define HSI_VALUE {hsi_value}
#endif

#if !defined(HSI48_VALUE)
#define HSI48_VALUE 48000000U
#endif

#if !defined(HSE_STARTUP_TIMEOUT)
#define HSE_STARTUP_TIMEOUT 100U
#endif

#if !defined(LSI_VALUE)
#define LSI_VALUE {lsi_value}
#endif

#if !defined(LSE_VALUE)
#define LSE_VALUE {lse_value}
#endif

#if !defined(LSE_STARTUP_TIMEOUT)
#define LSE_STARTUP_TIMEOUT 5000U
#endif

#if !defined(EXTERNAL_CLOCK_VALUE)
#define EXTERNAL_CLOCK_VALUE {external_clock_value}
#endif

#define VDD_VALUE 3300U
#define TICK_INT_PRIORITY 0x0FU
#define USE_RTOS 0U

{include_body}

#ifdef USE_FULL_ASSERT
void assert_failed(unsigned char *file, unsigned int line);
#else
#define assert_param(expr) ((void)0U)
#endif

#ifdef __cplusplus
}}
#endif

#endif
"""


def _clock_plan_values(plan: PlanResult | None) -> Dict[str, object]:
    if plan is None:
        return {}
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    constraints = project_ir.get("constraints", {}) if isinstance(project_ir, dict) else {}
    clock_plan = constraints.get("clock_plan", {}) if isinstance(constraints, dict) else {}
    return clock_plan if isinstance(clock_plan, dict) else {}


def _render_build_ps1(project_name: str) -> str:
    return f"""param(
    [string]$Uv4 = $env:KEIL_UV4_PATH
)

if (-not $Uv4) {{
    $candidates = @(
        "D:\\Keil_v5\\UV4\\UV4.exe",
        "D:\\Keil_v5\\ARM\\UV4\\UV4.exe",
        "C:\\Keil_v5\\UV4\\UV4.exe",
        "C:\\Keil_v5\\ARM\\UV4\\UV4.exe",
        "C:\\Program Files\\Keil_v5\\UV4\\UV4.exe",
        "C:\\Program Files (x86)\\Keil_v5\\UV4\\UV4.exe"
    )
    foreach ($candidate in $candidates) {{
        if (Test-Path $candidate) {{
            $Uv4 = $candidate
            break
        }}
    }}
}}

if (-not $Uv4 -or -not (Test-Path $Uv4)) {{
    Write-Error "未找到 UV4.exe，请通过 -Uv4 指定，或设置环境变量 KEIL_UV4_PATH。"
    exit 2
}}

& $Uv4 -b ".\\{project_name}.uvprojx" -j0 -o ".\\build.log"
exit $LASTEXITCODE
"""


def _render_flash_ps1(project_name: str) -> str:
    return f"""param(
    [string]$Uv4 = $env:KEIL_UV4_PATH
)

if (-not $Uv4) {{
    $candidates = @(
        "D:\\Keil_v5\\UV4\\UV4.exe",
        "D:\\Keil_v5\\ARM\\UV4\\UV4.exe",
        "C:\\Keil_v5\\UV4\\UV4.exe",
        "C:\\Keil_v5\\ARM\\UV4\\UV4.exe",
        "C:\\Program Files\\Keil_v5\\UV4\\UV4.exe",
        "C:\\Program Files (x86)\\Keil_v5\\UV4\\UV4.exe"
    )
    foreach ($candidate in $candidates) {{
        if (Test-Path $candidate) {{
            $Uv4 = $candidate
            break
        }}
    }}
}}

if (-not $Uv4 -or -not (Test-Path $Uv4)) {{
    Write-Error "未找到 UV4.exe，请通过 -Uv4 指定，或设置环境变量 KEIL_UV4_PATH。"
    exit 2
}}

& $Uv4 -f ".\\{project_name}.uvprojx"
exit $LASTEXITCODE
"""












def _render_mx_nvic_init_body(irqs: List[str]) -> List[str]:
    lines = [
        "void MX_NVIC_Init(void)",
        "{",
    ]
    for irq in irqs:
        lines.append(f"    HAL_NVIC_SetPriority({irq}, 0, 0);")
        lines.append(f"    HAL_NVIC_EnableIRQ({irq});")
    lines.extend(
        [
            "}",
            "",
        ]
    )
    return lines


