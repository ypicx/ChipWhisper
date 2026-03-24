from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .catalog import ChipDefinition
from .family_support import F1_SUPPORT, collect_hal_sources, get_family_support
from .generated_files import generated_file_include_path, generated_file_source_path, is_generated_header_path
from .keil_generator_app import _macro_name
from .keil_generator_hal import _pin_number, _pin_parts, _port_sort_key, _uart_handle_name
from .planner import PlanResult

GPIO_SIGNAL_MODE = {
    "control": ("GPIO_MODE_OUTPUT_PP", "GPIO_NOPULL", "GPIO_SPEED_FREQ_LOW"),
    "reset": ("GPIO_MODE_OUTPUT_PP", "GPIO_NOPULL", "GPIO_SPEED_FREQ_LOW"),
    "input": ("GPIO_MODE_INPUT", "GPIO_NOPULL", None),
    "int": ("GPIO_MODE_IT_RISING_FALLING", "GPIO_NOPULL", None),
    "interrupt": ("GPIO_MODE_IT_RISING_FALLING", "GPIO_NOPULL", None),
    "dq": ("GPIO_MODE_OUTPUT_OD", "GPIO_NOPULL", "GPIO_SPEED_FREQ_LOW"),
}


@dataclass(frozen=True)
class CodegenContext:
    chip: ChipDefinition | None
    support: object
    hal_sources: List[str]
    app_headers: List[str]
    app_sources: List[str]
    module_headers: List[str]
    module_sources: List[str]
    i2c_buses: List[Dict[str, object]]
    spi_buses: List[Dict[str, object]]
    uart_ports: List[Dict[str, object]]
    adc_inputs: List[Dict[str, object]]
    dac_units: List[Dict[str, object]]
    can_ports: List[Dict[str, object]]
    usb_devices: List[Dict[str, object]]
    pwm_timers: List[Dict[str, object]]
    timer_oc_timers: List[Dict[str, object]]
    timer_ic_timers: List[Dict[str, object]]
    encoder_timers: List[Dict[str, object]]
    dma_allocations: List[Dict[str, object]]
    irqs: List[str]
    direct_gpios: List[Dict[str, str]]


def _plan_target_family(plan: PlanResult) -> str:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    target = project_ir.get("target", {}) if isinstance(project_ir, dict) else {}
    family = str(target.get("family", "")).strip()
    return family or "STM32F1"


def _collect_generated_units(template_files: Iterable[str]) -> Tuple[List[str], List[str], List[str], List[str]]:
    app_headers: List[str] = []
    app_sources: List[str] = []
    module_headers: List[str] = []
    module_sources: List[str] = []
    for item in template_files:
        normalized = item.replace("\\", "/")
        if normalized.startswith("app/"):
            relative = generated_file_include_path(normalized) if is_generated_header_path(normalized) else generated_file_source_path(normalized)
            if relative:
                (app_headers if is_generated_header_path(normalized) else app_sources).append(relative)
        if normalized.startswith("modules/"):
            relative = generated_file_include_path(normalized) if is_generated_header_path(normalized) else generated_file_source_path(normalized)
            if relative:
                (module_headers if is_generated_header_path(normalized) else module_sources).append(relative)
    return (
        sorted(set(app_headers)),
        sorted(set(app_sources)),
        sorted(set(module_headers)),
        sorted(set(module_sources)),
    )


def _build_codegen_context(plan: PlanResult, chip: ChipDefinition | None = None) -> CodegenContext:
    family = chip.family if chip is not None else _plan_target_family(plan)
    support = get_family_support(family)
    app_headers, app_sources, module_headers, module_sources = _collect_generated_units(plan.template_files)
    return CodegenContext(
        chip=chip,
        support=support,
        hal_sources=collect_hal_sources(plan.hal_components, chip.family) if chip is not None else [],
        app_headers=app_headers,
        app_sources=app_sources,
        module_headers=module_headers,
        module_sources=module_sources,
        i2c_buses=_used_i2c_buses(plan),
        spi_buses=_used_spi_buses(plan),
        uart_ports=_used_uart_ports(plan, chip),
        adc_inputs=_used_adc_inputs(plan),
        dac_units=_used_dac_units(plan),
        can_ports=_used_can_ports(plan, chip),
        usb_devices=_used_usb_devices(plan),
        pwm_timers=_used_pwm_timers(plan),
        timer_oc_timers=_used_timer_oc_timers(plan),
        timer_ic_timers=_used_timer_ic_timers(plan),
        encoder_timers=_used_encoder_timers(plan),
        dma_allocations=_used_dma_allocations(plan),
        irqs=_used_nvic_irqs(plan),
        direct_gpios=_direct_gpio_assignments(plan),
    )


def _used_i2c_buses(plan: PlanResult) -> List[Dict[str, object]]:
    buses = []
    for bus in plan.buses:
        if bus.kind != "i2c":
            continue
        buses.append(
            {
                "instance": bus.bus,
                "handle": f"h{bus.bus.lower()}",
                "option_id": bus.option_id,
                "pins": dict(bus.pins),
                "devices": list(bus.devices),
            }
        )
    return sorted(buses, key=lambda item: str(item["instance"]))


def _used_spi_buses(plan: PlanResult) -> List[Dict[str, object]]:
    buses = []
    for bus in plan.buses:
        if bus.kind != "spi":
            continue
        buses.append(
            {
                "instance": bus.bus,
                "handle": f"h{bus.bus.lower()}",
                "option_id": bus.option_id,
                "pins": dict(bus.pins),
                "devices": list(bus.devices),
            }
        )
    return sorted(buses, key=lambda item: str(item["instance"]))


def _used_uart_ports(plan: PlanResult, chip: ChipDefinition | None = None) -> List[Dict[str, object]]:
    grouped: Dict[str, Dict[str, str]] = {}
    for item in plan.assignments:
        if "." not in item.signal:
            continue
        prefix, signal = item.signal.split(".", 1)
        instance = prefix.upper()
        if not instance.startswith("USART"):
            continue
        grouped.setdefault(instance, {})[signal] = item.pin

    ports = []
    for instance, pins in grouped.items():
        option_id = instance
        if chip is not None:
            for option in chip.interfaces["uart"]:
                if option.instance == instance and dict(option.signals) == pins:
                    option_id = option.option_id
                    break
        ports.append(
            {
                "instance": instance,
                "handle": _uart_handle_name(instance),
                "option_id": option_id,
                "pins": pins,
            }
        )
    return sorted(ports, key=lambda item: str(item["instance"]))


def _used_nvic_irqs(plan: PlanResult) -> List[str]:
    irqs: List[str] = []
    for dma in _used_dma_allocations(plan):
        irq = str(dma.get("irq", "")).strip()
        if irq and irq not in irqs:
            irqs.append(irq)
    for exti in _used_exti_allocations(plan):
        irq = str(exti.get("irq", "")).strip()
        if irq and irq not in irqs:
            irqs.append(irq)
    for uart in _used_uart_ports(plan):
        irq = f"{uart['instance']}_IRQn"
        if irq not in irqs:
            irqs.append(irq)
    for usb in _used_usb_devices(plan):
        irq = str(usb.get("irq", "")).strip()
        if irq and irq not in irqs:
            irqs.append(irq)
    for timer in _used_timer_ic_timers(plan):
        irq = str(timer.get("irq", "")).strip()
        if irq and irq not in irqs:
            irqs.append(irq)
    for module in plan.project_ir.get("modules", []):
        if not isinstance(module, dict):
            continue
        for irq in module.get("irqs", []):
            text = str(irq).strip()
            if text and text not in irqs:
                irqs.append(text)
    return irqs


def _used_adc_inputs(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    adc_items = peripherals.get("adc", []) if isinstance(peripherals, dict) else []
    adc_units: List[Dict[str, object]] = []
    if not isinstance(adc_items, list):
        return adc_units
    for item in adc_items:
        if not isinstance(item, dict):
            continue
        instance = str(item.get("instance", "")).strip().upper()
        handle = str(item.get("handle", "")).strip() or f"h{instance.lower()}"
        channels = item.get("channels", [])
        if not instance or not isinstance(channels, list) or not channels:
            continue
        adc_units.append(
            {
                "instance": instance,
                "handle": handle,
                "channels": [dict(channel) for channel in channels if isinstance(channel, dict)],
            }
        )
    return sorted(adc_units, key=lambda item: str(item["instance"]))


def _used_dac_units(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    dac_items = peripherals.get("dac", []) if isinstance(peripherals, dict) else []
    dac_units: List[Dict[str, object]] = []
    if not isinstance(dac_items, list):
        return dac_units
    for item in dac_items:
        if not isinstance(item, dict):
            continue
        dac_name = str(item.get("dac", "")).strip().upper()
        handle = str(item.get("handle", "")).strip() or f"h{dac_name.lower()}"
        channels = item.get("channels", [])
        if not dac_name or not isinstance(channels, list) or not channels:
            continue
        dac_units.append(
            {
                "dac": dac_name,
                "handle": handle,
                "channels": [dict(channel) for channel in channels if isinstance(channel, dict)],
            }
        )
    return sorted(dac_units, key=lambda item: str(item["dac"]))


def _used_pwm_timers(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    pwm_items = peripherals.get("pwm", []) if isinstance(peripherals, dict) else []
    timers: List[Dict[str, object]] = []
    if not isinstance(pwm_items, list):
        return timers
    for item in pwm_items:
        if not isinstance(item, dict):
            continue
        timer_name = str(item.get("timer", "")).strip().upper()
        handle = str(item.get("handle", "")).strip() or f"h{timer_name.lower()}"
        channels = item.get("channels", [])
        if not timer_name or not isinstance(channels, list) or not channels:
            continue
        timers.append(
            {
                "timer": timer_name,
                "handle": handle,
                "channels": [dict(channel) for channel in channels if isinstance(channel, dict)],
                "pwm_profile": str(item.get("pwm_profile", "default")),
            }
        )
    return sorted(timers, key=lambda item: str(item["timer"]))


def _used_timer_oc_timers(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    timer_oc_items = peripherals.get("timer_oc", []) if isinstance(peripherals, dict) else []
    timers: List[Dict[str, object]] = []
    if not isinstance(timer_oc_items, list):
        return timers
    for item in timer_oc_items:
        if not isinstance(item, dict):
            continue
        timer_name = str(item.get("timer", "")).strip().upper()
        handle = str(item.get("handle", "")).strip() or f"h{timer_name.lower()}"
        channels = item.get("channels", [])
        if not timer_name or not isinstance(channels, list) or not channels:
            continue
        timers.append(
            {
                "timer": timer_name,
                "handle": handle,
                "channels": [dict(channel) for channel in channels if isinstance(channel, dict)],
            }
        )
    return sorted(timers, key=lambda item: str(item["timer"]))


def _used_timer_ic_timers(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    timer_ic_items = peripherals.get("timer_ic", []) if isinstance(peripherals, dict) else []
    timers: List[Dict[str, object]] = []
    if not isinstance(timer_ic_items, list):
        return timers
    for item in timer_ic_items:
        if not isinstance(item, dict):
            continue
        timer_name = str(item.get("timer", "")).strip().upper()
        handle = str(item.get("handle", "")).strip() or f"h{timer_name.lower()}"
        irq = str(item.get("irq", "")).strip()
        channels = item.get("channels", [])
        if not timer_name or not irq or not isinstance(channels, list) or not channels:
            continue
        timers.append(
            {
                "timer": timer_name,
                "handle": handle,
                "irq": irq,
                "channels": [dict(channel) for channel in channels if isinstance(channel, dict)],
            }
        )
    return sorted(timers, key=lambda item: str(item["timer"]))


def _used_encoder_timers(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    encoder_items = peripherals.get("encoder", []) if isinstance(peripherals, dict) else []
    timers: List[Dict[str, object]] = []
    if not isinstance(encoder_items, list):
        return timers
    for item in encoder_items:
        if not isinstance(item, dict):
            continue
        timer_name = str(item.get("timer", "")).strip().upper()
        handle = str(item.get("handle", "")).strip() or f"h{timer_name.lower()}"
        pins = item.get("pins", {})
        if not timer_name or not isinstance(pins, dict) or not pins:
            continue
        timers.append(
            {
                "timer": timer_name,
                "handle": handle,
                "pins": {str(key): str(value).strip().upper() for key, value in pins.items()},
                "module": str(item.get("module", "")).strip(),
                "signal": str(item.get("signal", "")).strip(),
            }
        )
    return sorted(timers, key=lambda item: str(item["timer"]))


def _used_can_ports(plan: PlanResult, chip: ChipDefinition | None = None) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    can_items = peripherals.get("can", []) if isinstance(peripherals, dict) else []
    can_ports: List[Dict[str, object]] = []
    if not isinstance(can_items, list):
        return can_ports
    for item in can_items:
        if not isinstance(item, dict):
            continue
        instance = str(item.get("instance", "")).strip().upper()
        handle = str(item.get("handle", "")).strip()
        if not handle:
            if chip is not None:
                support = get_family_support(chip.family)
            else:
                target = project_ir.get("target", {}) if isinstance(project_ir, dict) else {}
                family = str(target.get("family", "")).strip() or F1_SUPPORT.family
                support = get_family_support(family)
            handle = support.build_can_handle_name(instance)
        pins = item.get("pins", {})
        if not instance or not isinstance(pins, dict) or not pins:
            continue
        can_ports.append(
            {
                "instance": instance,
                "handle": handle,
                "pins": {str(key): str(value).strip().upper() for key, value in pins.items()},
            }
        )
    return sorted(can_ports, key=lambda item: str(item["instance"]))


def _used_usb_devices(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    target = project_ir.get("target", {}) if isinstance(project_ir, dict) else {}
    family = str(target.get("family", "")).strip().upper()
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    usb_items = peripherals.get("usb", []) if isinstance(peripherals, dict) else []
    usb_devices: List[Dict[str, object]] = []
    if not isinstance(usb_items, list):
        return usb_devices
    for item in usb_items:
        if not isinstance(item, dict):
            continue
        instance = str(item.get("instance", "")).strip().upper()
        handle = str(item.get("handle", "")).strip() or (
            "hpcd_usb_fs" if instance in {"USB", "USB_FS", "USB_OTG_FS"} else f"hpcd_{instance.lower()}"
        )
        pins = item.get("pins", {})
        if not instance or not isinstance(pins, dict) or not pins:
            continue
        irq = _usb_irq_for_instance(instance, family)
        usb_devices.append(
            {
                "instance": instance,
                "handle": handle,
                "pins": {str(key): str(value).strip().upper() for key, value in pins.items()},
                "irq": irq,
                "irq_handler": irq.replace("_IRQn", "_IRQHandler") if irq else "",
            }
        )
    return sorted(usb_devices, key=lambda item: str(item["instance"]))


def _used_exti_allocations(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    exti_items = peripherals.get("exti", []) if isinstance(peripherals, dict) else []
    allocations: List[Dict[str, object]] = []
    if not isinstance(exti_items, list):
        return allocations
    for item in exti_items:
        if not isinstance(item, dict):
            continue
        module = str(item.get("module", "")).strip()
        signal = str(item.get("signal", "")).strip()
        pin = str(item.get("pin", "")).strip().upper()
        irq = str(item.get("irq", "")).strip()
        line = item.get("line")
        if not module or not signal or not pin or not irq:
            continue
        try:
            line_number = int(line)
        except (TypeError, ValueError):
            line_number = _pin_number(pin)
        allocations.append(
            {
                "module": module,
                "signal": signal,
                "pin": pin,
                "irq": irq,
                "line": line_number,
                "pin_macro": f"{_macro_name(module, signal)}_PIN",
            }
        )
    return sorted(allocations, key=lambda item: (str(item["irq"]), int(item["line"]), str(item["module"])))


def _used_dma_allocations(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    dma_items = peripherals.get("dma", []) if isinstance(peripherals, dict) else []
    allocations: List[Dict[str, object]] = []
    if not isinstance(dma_items, list):
        return allocations

    for item in dma_items:
        if not isinstance(item, dict):
            continue
        request = str(item.get("request", "")).strip().upper()
        channel = str(item.get("channel", "")).strip()
        if not request or not channel or "_" not in request:
            continue
        instance, direction_text = request.rsplit("_", 1)
        direction = direction_text.strip().lower()
        if direction not in {"rx", "tx"}:
            continue
        peripheral_kind = _dma_peripheral_kind(instance)
        if not peripheral_kind:
            continue
        handle_name = f"hdma_{instance.lower()}_{direction}"
        allocations.append(
            {
                "module": str(item.get("module", "")).strip(),
                "request": request,
                "instance": instance,
                "peripheral_kind": peripheral_kind,
                "direction": direction,
                "link_field": f"hdma{direction}",
                "handle": handle_name,
                "channel": channel,
                "request_macro": f"DMA_REQUEST_{request}",
                "irq": f"{channel}_IRQn",
                "irq_handler": f"{channel}_IRQHandler",
                "source": str(item.get("source", "")).strip(),
            }
        )

    allocations.sort(
        key=lambda item: (
            str(item["instance"]),
            0 if str(item["direction"]) == "rx" else 1,
            str(item["channel"]),
        )
    )
    return allocations


def _dma_peripheral_kind(instance: str) -> str:
    normalized = str(instance).strip().upper()
    if normalized.startswith(("USART", "UART", "LPUART")):
        return "uart"
    if normalized.startswith("I2C"):
        return "i2c"
    return ""


def _can_handle_type(plan: PlanResult, _can: Dict[str, object]) -> str:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    target = project_ir.get("target", {}) if isinstance(project_ir, dict) else {}
    family = str(target.get("family", "")).strip().upper()
    return get_family_support(family).can_handle_type


def _usb_irq_for_instance(instance: str, family: str) -> str:
    return get_family_support(family).resolve_usb_irq(instance)


def _group_exti_irqs(plan: PlanResult) -> List[Dict[str, object]]:
    grouped: Dict[str, Dict[str, object]] = {}
    for allocation in _used_exti_allocations(plan):
        irq = str(allocation["irq"])
        entry = grouped.setdefault(
            irq,
            {
                "irq": irq,
                "irq_handler": irq.replace("_IRQn", "_IRQHandler"),
                "pin_macros": [],
                "lines": [],
            },
        )
        pin_macro = str(allocation["pin_macro"])
        if pin_macro not in entry["pin_macros"]:
            entry["pin_macros"].append(pin_macro)
        entry["lines"].append(int(allocation["line"]))

    groups = list(grouped.values())
    for group in groups:
        group["lines"] = sorted(set(group["lines"]))
    return sorted(groups, key=lambda item: (min(item["lines"]) if item["lines"] else 99, str(item["irq"])))


def _direct_gpio_assignments(plan: PlanResult) -> List[Dict[str, str]]:
    adc_pins = {
        str(channel.get("pin", "")).strip().upper()
        for adc in _used_adc_inputs(plan)
        for channel in adc.get("channels", [])
        if isinstance(channel, dict)
    }
    signals = []
    for item in plan.assignments:
        if "." in item.signal:
            continue
        if item.pin.strip().upper() in adc_pins:
            continue
        mode, pull, speed = GPIO_SIGNAL_MODE.get(
            item.signal,
            ("GPIO_MODE_OUTPUT_PP", "GPIO_NOPULL", "GPIO_SPEED_FREQ_LOW"),
        )
        port, pin_macro = _pin_parts(item.pin)
        signals.append(
            {
                "module": item.module,
                "signal": item.signal,
                "pin": item.pin,
                "port": port,
                "pin_macro": pin_macro,
                "mode": mode,
                "pull": pull,
                "speed": speed or "",
            }
        )
    return sorted(signals, key=lambda item: (_port_sort_key(item["port"]), _pin_number(item["pin"])))
