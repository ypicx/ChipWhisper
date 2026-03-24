from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .keil_generator_app import _macro_name
from .keil_generator_hal import _pin_parts
from .planner import PlanResult


_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent / "templates")),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def render_app_config_v2(plan: PlanResult) -> str:
    template = _TEMPLATE_ENV.get_template("keil_app_config/app_config.h.jinja")
    return template.render(groups=_build_app_config_groups(plan))


def _build_app_config_groups(plan: PlanResult) -> List[Dict[str, object]]:
    project_ir = plan.project_ir if isinstance(plan.project_ir, dict) else {}
    peripherals = project_ir.get("peripherals", {}) if isinstance(project_ir, dict) else {}
    groups: List[Dict[str, object]] = []

    for item in plan.assignments:
        macro = _macro_name(item.module, item.signal)
        port, pin = _pin_parts(item.pin)
        _append_define_group(
            groups,
            "模块引脚映射",
            [
                (f"{macro}_PORT", port),
                (f"{macro}_PIN", pin),
            ],
        )

    for bus in plan.buses:
        for device in bus.devices:
            prefix = _macro_name(str(device["module"]), bus.kind)
            defines = [(f"{prefix}_INSTANCE", bus.bus)]
            if "address" in device:
                defines.append((f"{prefix}_ADDRESS", str(device["address"])))
            _append_define_group(groups, "总线设备绑定", defines)

    for spi in peripherals.get("buses", []) if isinstance(peripherals, dict) else []:
        if not isinstance(spi, dict) or str(spi.get("kind", "")).strip().lower() != "spi":
            continue
        instance = str(spi.get("bus", "")).strip()
        for device in spi.get("devices", []):
            if not isinstance(device, dict):
                continue
            prefix = _macro_name(str(device.get("module", "")), "spi")
            if prefix and instance:
                _append_define_group(groups, "SPI 设备绑定", [(f"{prefix}_INSTANCE", instance)])

    for adc in peripherals.get("adc", []) if isinstance(peripherals, dict) else []:
        if not isinstance(adc, dict):
            continue
        for channel in adc.get("channels", []):
            if not isinstance(channel, dict):
                continue
            prefix = _macro_name(str(channel.get("module", "")), str(channel.get("signal", "")))
            instance = str(adc.get("instance", "")).strip()
            channel_macro = str(channel.get("channel", "")).strip()
            rank_macro = str(channel.get("rank_macro", "")).strip()
            if not prefix or not instance or not channel_macro:
                continue
            defines = [
                (f"{prefix}_ADC_INSTANCE", instance),
                (f"{prefix}_ADC_CHANNEL", channel_macro),
            ]
            if rank_macro:
                defines.append((f"{prefix}_ADC_RANK", rank_macro))
            _append_define_group(groups, "ADC 通道分配", defines)

    for timer in peripherals.get("timer_ic", []) if isinstance(peripherals, dict) else []:
        if not isinstance(timer, dict):
            continue
        timer_name = str(timer.get("timer", "")).strip()
        irq = str(timer.get("irq", "")).strip()
        for channel in timer.get("channels", []):
            if not isinstance(channel, dict):
                continue
            prefix = _macro_name(str(channel.get("module", "")), str(channel.get("signal", "")))
            channel_macro = str(channel.get("channel_macro", "")).strip()
            if not prefix or not timer_name or not channel_macro:
                continue
            defines = [
                (f"{prefix}_TIM_INSTANCE", timer_name),
                (f"{prefix}_TIM_CHANNEL", channel_macro),
            ]
            if irq:
                defines.append((f"{prefix}_IRQ", irq))
            _append_define_group(groups, "定时器输入捕获绑定", defines)

    for timer in peripherals.get("timer_oc", []) if isinstance(peripherals, dict) else []:
        if not isinstance(timer, dict):
            continue
        timer_name = str(timer.get("timer", "")).strip()
        for channel in timer.get("channels", []):
            if not isinstance(channel, dict):
                continue
            prefix = _macro_name(str(channel.get("module", "")), str(channel.get("signal", "")))
            channel_macro = str(channel.get("channel_macro", "")).strip()
            if prefix and timer_name and channel_macro:
                _append_define_group(
                    groups,
                    "定时器输出比较绑定",
                    [
                        (f"{prefix}_TIM_INSTANCE", timer_name),
                        (f"{prefix}_TIM_CHANNEL", channel_macro),
                    ],
                )

    for timer in peripherals.get("encoder", []) if isinstance(peripherals, dict) else []:
        if not isinstance(timer, dict):
            continue
        prefix = _macro_name(str(timer.get("module", "")), str(timer.get("signal", "")))
        timer_name = str(timer.get("timer", "")).strip()
        if prefix and timer_name:
            _append_define_group(
                groups,
                "编码器接口绑定",
                [
                    (f"{prefix}_TIM_INSTANCE", timer_name),
                    (f"{prefix}_TIM_CHANNEL_A", "TIM_CHANNEL_1"),
                    (f"{prefix}_TIM_CHANNEL_B", "TIM_CHANNEL_2"),
                ],
            )

    for dac in peripherals.get("dac", []) if isinstance(peripherals, dict) else []:
        if not isinstance(dac, dict):
            continue
        dac_name = str(dac.get("dac", "")).strip()
        for channel in dac.get("channels", []):
            if not isinstance(channel, dict):
                continue
            prefix = _macro_name(str(channel.get("module", "")), str(channel.get("signal", "")))
            channel_macro = str(channel.get("channel_macro", "")).strip()
            if prefix and dac_name and channel_macro:
                _append_define_group(
                    groups,
                    "DAC 通道绑定",
                    [
                        (f"{prefix}_DAC_INSTANCE", dac_name),
                        (f"{prefix}_DAC_CHANNEL", channel_macro),
                    ],
                )

    for can in peripherals.get("can", []) if isinstance(peripherals, dict) else []:
        if not isinstance(can, dict):
            continue
        prefix = _macro_name(str(can.get("module", "")), "can")
        instance = str(can.get("instance", "")).strip()
        if prefix and instance:
            _append_define_group(groups, "CAN 接口绑定", [(f"{prefix}_INSTANCE", instance)])

    for usb in peripherals.get("usb", []) if isinstance(peripherals, dict) else []:
        if not isinstance(usb, dict):
            continue
        prefix = _macro_name(str(usb.get("module", "")), "usb")
        instance = str(usb.get("instance", "")).strip()
        if prefix and instance:
            _append_define_group(groups, "USB 接口绑定", [(f"{prefix}_INSTANCE", instance)])

    return groups


def _append_define_group(groups: List[Dict[str, object]], title: str, defines: List[tuple[str, str]]) -> None:
    normalized = [
        {"name": str(name).strip(), "value": str(value).strip()}
        for name, value in defines
        if str(name).strip() and str(value).strip()
    ]
    if normalized:
        groups.append({"title": str(title).strip() or "自动生成宏", "defines": normalized})
