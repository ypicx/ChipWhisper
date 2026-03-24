from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .catalog import ChipDefinition
from .family_support import get_family_support
from .planner import PlanResult


_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent / "templates")),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def render_generated_readme_v2(project_name: str, chip: ChipDefinition) -> str:
    support = get_family_support(chip.family)
    template = _TEMPLATE_ENV.get_template("keil_docs/README.generated.md.jinja")
    return template.render(project_name=project_name, chip=chip, support=support)


def render_drivers_readme_v2(chip: ChipDefinition) -> str:
    support = get_family_support(chip.family)
    template = _TEMPLATE_ENV.get_template("keil_docs/drivers.README.md.jinja")
    return template.render(chip=chip, support=support)


def render_project_report(plan: PlanResult, project_name: str, chip: ChipDefinition) -> str:
    support = get_family_support(chip.family)
    template = _TEMPLATE_ENV.get_template("keil_docs/REPORT.generated.md.jinja")
    return template.render(**_build_project_report_context(plan, project_name, chip, support))


def _build_project_report_context(
    plan: PlanResult,
    project_name: str,
    chip: ChipDefinition,
    support: object,
) -> Dict[str, object]:
    target = plan.project_ir.get("target", {}) if isinstance(plan.project_ir, dict) else {}
    modules = plan.project_ir.get("modules", []) if isinstance(plan.project_ir, dict) else []
    return {
        "project_name": project_name,
        "chip": chip,
        "support": support,
        "target_chip": target.get("chip", chip.name),
        "target_family": target.get("family", chip.family),
        "target_package": target.get("package", chip.package),
        "target_board": target.get("board", "chip_only"),
        "module_count": len(modules) if isinstance(modules, list) else 0,
        "assignment_count": len(plan.assignments),
        "board_capabilities": _normalize_board_capabilities(target.get("board_capabilities", [])),
        "board_notes": _normalize_string_list(target.get("board_notes", [])),
        "modules": _normalize_modules(modules),
        "module_details": _normalize_module_details(modules),
        "assignments": [
            {
                "module": item.module,
                "signal": item.signal,
                "pin": item.pin,
                "reason": item.reason,
            }
            for item in plan.assignments
        ],
        "buses": _normalize_buses(plan),
        "architecture_notes": _build_architecture_notes(plan, chip),
        "usage_tips": _render_usage_tips(plan, chip),
        "warnings": list(plan.warnings),
        "errors": list(plan.errors),
    }


def _normalize_board_capabilities(items: object) -> List[Dict[str, str]]:
    capabilities: List[Dict[str, str]] = []
    if not isinstance(items, list):
        return capabilities
    for item in items:
        if not isinstance(item, dict):
            continue
        display_name = str(item.get("display_name", "")).strip() or str(item.get("key", "")).strip()
        summary = str(item.get("summary", "")).strip()
        if not display_name:
            continue
        capabilities.append({"display_name": display_name, "summary": summary})
    return capabilities


def _normalize_string_list(items: object) -> List[str]:
    if not isinstance(items, list):
        return []
    values: List[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            values.append(text)
    return values


def _normalize_modules(items: object) -> List[Dict[str, str]]:
    modules: List[Dict[str, str]] = []
    if not isinstance(items, list):
        return modules
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        name = str(item.get("name", kind or "module")).strip() or "module"
        summary = str(item.get("summary", "")).strip()
        modules.append(
            {
                "kind": kind,
                "name": name,
                "summary": summary,
                "label": f"`{name}` (`{kind}`){' ' + summary if summary else ''}",
            }
        )
    return modules


def _normalize_buses(plan: PlanResult) -> List[Dict[str, str]]:
    buses: List[Dict[str, str]] = []
    for bus in plan.buses:
        pin_text = ", ".join(f"{signal.upper()}={pin}" for signal, pin in bus.pins.items())
        device_text = ", ".join(
            f"{device.get('module')}({device.get('address', '-')})" for device in bus.devices
        ) or "-"
        note_text = "; ".join(bus.notes) if bus.notes else "-"
        buses.append(
            {
                "bus": bus.bus,
                "kind": bus.kind,
                "pin_text": pin_text,
                "device_text": device_text,
                "note_text": note_text,
            }
        )
    return buses


def _render_usage_tips(plan: PlanResult, chip: ChipDefinition) -> List[str]:
    support = get_family_support(chip.family)
    tips = [
        f"Import the official {support.cube_package_label} drivers into Drivers/ before building.",
        "Treat the generated project as a hardware scaffold. Keep application behavior in App/Src/app_main.c.",
        "Confirm that external modules share ground and that their supply voltage is GPIO-level compatible.",
    ]

    target = plan.project_ir.get("target", {}) if isinstance(plan.project_ir, dict) else {}
    for note_text in _normalize_string_list(target.get("board_notes", [])):
        tips.append(f"Board note: {note_text}")

    for bus in plan.buses:
        if bus.kind == "i2c":
            tips.append(f"{bus.bus} is an I2C bus. Confirm that SCL and SDA have pull-up resistors.")

    signal_names = {item.signal.lower() for item in plan.assignments}
    has_uart_pair = any(name.endswith(".tx") or name == "tx" for name in signal_names) and any(
        name.endswith(".rx") or name == "rx" for name in signal_names
    )
    if has_uart_pair:
        tips.append("Cross UART wiring correctly: module TX -> MCU RX, and module RX -> MCU TX.")
    if any(name.endswith(".out") or name == "out" for name in signal_names):
        tips.append("Drive motors, buzzers, or servos through a proper driver stage instead of a raw MCU GPIO.")
    if any(name.endswith(".dq") or name == "dq" for name in signal_names):
        tips.append("Single-wire devices usually need an external pull-up resistor on the data line.")

    if _module_names(plan, "sg90_servo"):
        tips.append("Use a separate stable 5V supply for SG90 servos and share ground with the board.")
    if _module_names(plan, "dc_motor_pwm"):
        tips.append("DC motors need a MOSFET or dedicated driver and a proper flyback protection path.")
    if _module_names(plan, "uart_debug"):
        tips.append("If UART logs do not appear, check the baud rate, UART ownership, and TX/RX direction first.")

    return tips


def _module_names(plan: PlanResult, kind: str) -> List[str]:
    modules = plan.project_ir.get("modules", []) if isinstance(plan.project_ir, dict) else []
    return [
        str(module.get("name", "")).strip()
        for module in modules
        if isinstance(module, dict) and str(module.get("kind", "")).strip() == kind
    ]


def _normalize_module_details(items: object) -> List[Dict[str, str]]:
    """Build detailed module table entries with bus/address/notes info."""
    details: List[Dict[str, str]] = []
    if not isinstance(items, list):
        return details
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        name = str(item.get("name", kind or "module")).strip()
        bus_kind = str(item.get("bus_kind", "")).strip() or "-"
        options = item.get("options", {})
        address = "-"
        if isinstance(options, dict):
            addr_val = options.get("address", options.get("i2c_address", ""))
            if addr_val:
                address = str(addr_val).strip()
        notes_list = item.get("notes", [])
        notes_text = "; ".join(str(n).strip() for n in notes_list[:2] if str(n).strip()) if isinstance(notes_list, list) else "-"
        details.append({
            "name": name,
            "kind": kind,
            "bus": bus_kind,
            "address": address,
            "notes": notes_text or "-",
        })
    return details


def _build_architecture_notes(plan: PlanResult, chip: ChipDefinition) -> List[str]:
    """Generate software architecture description lines for the report."""
    notes: List[str] = []
    notes.append(f"The project targets the {chip.name} ({chip.family}) with {chip.flash_kb}KB Flash and {chip.ram_kb}KB RAM.")
    notes.append("The software architecture follows a layered design:")
    notes.append("- **HAL Layer**: STM32 HAL drivers handle peripheral initialization and low-level I/O.")
    notes.append("- **Module Layer**: Each peripheral module (sensor, display, actuator) is encapsulated in a dedicated driver file under `Modules/`.")
    notes.append("- **Application Layer**: Business logic resides in `App/Src/app_main.c` with clearly separated `AppInit()` and `AppLoop()` functions.")

    modules = plan.project_ir.get("modules", []) if isinstance(plan.project_ir, dict) else []
    if isinstance(modules, list):
        sensor_kinds = {"aht20_i2c", "dht11_singlewire", "bh1750_i2c", "mpu6050_i2c", "hc_sr04_gpio", "ds18b20_onewire"}
        display_kinds = {"ssd1306_i2c", "lcd1602_i2c", "ct117e_lcd_parallel"}
        actuator_kinds = {"led", "active_buzzer", "sg90_servo", "dc_motor_pwm"}
        algo_kinds = {"pid_controller", "moving_avg_filter", "ring_buffer"}

        sensors = [str(m.get("name", "")).strip() for m in modules if isinstance(m, dict) and str(m.get("kind", "")) in sensor_kinds]
        displays = [str(m.get("name", "")).strip() for m in modules if isinstance(m, dict) and str(m.get("kind", "")) in display_kinds]
        actuators = [str(m.get("name", "")).strip() for m in modules if isinstance(m, dict) and str(m.get("kind", "")) in actuator_kinds]
        algos = [str(m.get("name", "")).strip() for m in modules if isinstance(m, dict) and str(m.get("kind", "")) in algo_kinds]

        if sensors:
            notes.append(f"- **Sensor modules**: {', '.join(sensors)}")
        if displays:
            notes.append(f"- **Display modules**: {', '.join(displays)}")
        if actuators:
            notes.append(f"- **Actuator modules**: {', '.join(actuators)}")
        if algos:
            notes.append(f"- **Algorithm modules**: {', '.join(algos)}")

    if plan.buses:
        i2c_buses = [b for b in plan.buses if b.kind == "i2c"]
        if i2c_buses:
            for bus in i2c_buses:
                device_names = [str(d.get("module", "")) for d in bus.devices]
                notes.append(f"- **{bus.bus} I2C bus**: shared by {', '.join(device_names)}")

    return notes

