from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from .app_logic_ir import normalize_app_logic_ir, normalize_app_logic_ir_acceptance, render_app_logic_from_ir
from .catalog import BoardProfile, ChipDefinition, ClockProfile, InterfaceOption, ModuleSpec
from .extension_packs import load_catalog
from .generated_files import normalize_generated_files
from .pack_plugins import apply_module_plan_hook


@dataclass
class ModuleRequest:
    kind: str
    name: str
    options: Dict[str, object] = field(default_factory=dict)


@dataclass
class PinAssignment:
    module: str
    signal: str
    pin: str
    reason: str


@dataclass
class BusAssignment:
    bus: str
    kind: str
    option_id: str
    pins: Dict[str, str]
    devices: List[Dict[str, object]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedResourceRequest:
    kind: str
    signal: str
    optional: bool = False


@dataclass(frozen=True)
class ParsedDmaRequest:
    request: str
    optional: bool = False
    shared_scope: str = ""


@dataclass
class PlanResult:
    feasible: bool
    chip: str
    board: str
    summary: str
    warnings: List[str]
    errors: List[str]
    assignments: List[PinAssignment]
    buses: List[BusAssignment]
    hal_components: List[str]
    template_files: List[str]
    next_steps: List[str]
    project_ir: Dict[str, object]

    def to_dict(self) -> Dict[str, object]:
        return {
            "feasible": self.feasible,
            "chip": self.chip,
            "board": self.board,
            "summary": self.summary,
            "warnings": self.warnings,
            "errors": self.errors,
            "assignments": [
                {
                    "module": item.module,
                    "signal": item.signal,
                    "pin": item.pin,
                    "reason": item.reason,
                }
                for item in self.assignments
            ],
            "buses": [
                {
                    "bus": bus.bus,
                    "kind": bus.kind,
                    "option_id": bus.option_id,
                    "pins": bus.pins,
                    "devices": bus.devices,
                    "notes": bus.notes,
                }
                for bus in self.buses
            ],
            "hal_components": self.hal_components,
            "template_files": self.template_files,
            "next_steps": self.next_steps,
            "project_ir": self.project_ir,
        }


RESOURCE_DEFAULT_SIGNALS = {
    "gpio_out": "control",
    "gpio_in": "input",
    "onewire_gpio": "dq",
    "pwm_out": "out",
    "timer_ic": "capture",
    "timer_oc": "out",
    "adc_in": "in",
    "dac_out": "out",
    "uart_port": "port",
    "i2c_device": "bus",
    "spi_bus": "bus",
    "spi_device": "bus",
    "encoder": "encoder",
    "advanced_timer": "timer",
    "can_port": "port",
    "usb_device": "port",
}

BOARD_KEY_ALIASES = {
    "lanqiao_f103_training_board": "stm32f103rb_training_board",
    "lanqiao_g431_ct117e_m4": "ct117e_m4_g431",
}


class Planner:
    def __init__(
        self,
        chip: ChipDefinition,
        module_registry: Dict[str, ModuleSpec],
        board: str = "",
        board_profile: BoardProfile | None = None,
        keep_swd: bool = True,
        reserved_pins: Optional[Iterable[str]] = None,
        avoid_pins: Optional[Iterable[str]] = None,
        app_logic_goal: str = "",
        app_logic: Optional[Dict[str, object]] = None,
        app_logic_ir: Optional[Dict[str, object]] = None,
        generated_files: Optional[Dict[str, object]] = None,
    ):
        self.chip = chip
        self.module_registry = module_registry
        self.board = str(board or "").strip() or "auto"
        self.board_profile = board_profile
        self.keep_swd = keep_swd
        self.used_pins: Dict[str, str] = {}
        self.avoid_pins: Set[str] = {
            self._normalize_pin(pin)
            for pin in (
                *(board_profile.avoid_pins if board_profile is not None else ()),
                *(avoid_pins or ()),
            )
        }
        self.assignments: List[PinAssignment] = []
        self.buses: List[BusAssignment] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.hal_components: Set[str] = {"RCC", "FLASH"}
        self.template_files: Set[str] = {"Core/Src/main.c", "Core/Inc/app_config.h"}
        self.used_interface_options: Set[str] = set()
        self.module_specs: Dict[str, ModuleSpec] = {}
        self.module_resource_requests: Dict[str, List[ParsedResourceRequest]] = {}
        self.module_dma_requests: Dict[str, List[ParsedDmaRequest]] = {}
        self.module_interface_bindings: Dict[str, Dict[str, str]] = {}
        self.modules: List[ModuleRequest] = []
        self.app_logic_goal = str(app_logic_goal).strip()
        self.app_logic = _normalize_app_logic(app_logic)
        self.app_logic_ir = normalize_app_logic_ir(app_logic_ir)
        self.used_exti_lines: Dict[int, str] = {}
        self.exti_allocations: List[Dict[str, object]] = []
        self.timer_instance_roles: Dict[str, str] = {}
        self.timer_ic_allocations: List[Dict[str, object]] = []
        self.timer_oc_allocations: List[Dict[str, object]] = []
        self.encoder_allocations: List[Dict[str, object]] = []
        self.advanced_timer_allocations: List[Dict[str, object]] = []
        self.adc_allocations: List[Dict[str, object]] = []
        self.dac_allocations: List[Dict[str, object]] = []
        self.can_allocations: List[Dict[str, object]] = []
        self.usb_allocations: List[Dict[str, object]] = []
        self.used_dma_channels: Dict[str, str] = {}
        self.dma_allocations: List[Dict[str, object]] = []
        self.generated_files = normalize_generated_files(generated_files)
        self.template_files.update(self.generated_files.keys())

        if keep_swd:
            for pin in chip.reserved_pins:
                self.used_pins[pin] = "reserved for SWD"

        if board_profile is not None:
            for pin in board_profile.reserved_pins:
                normalized = self._normalize_pin(pin)
                self.used_pins[normalized] = "reserved by board profile"

        for pin in (reserved_pins or []):
            normalized = self._normalize_pin(pin)
            self.used_pins[normalized] = "reserved by board"

    def plan(self, modules: List[ModuleRequest]) -> PlanResult:
        self.modules = modules
        for req in modules:
            spec = self.module_registry.get(req.kind)
            if spec is None:
                self.errors.append(f"Unsupported module kind: {req.kind}")
                continue
            try:
                spec, plugin_generated_files, plugin_warnings = apply_module_plan_hook(
                    spec,
                    module_name=req.name,
                    module_options=req.options,
                    chip=self.chip,
                    board=self.board,
                )
            except Exception as exc:
                self.errors.append(f"Module plugin on_plan failed for {req.name}: {exc}")
                continue
            if plugin_generated_files:
                self.generated_files.update(plugin_generated_files)
                self.template_files.update(plugin_generated_files.keys())
            self.warnings.extend(plugin_warnings)
            self.module_specs[req.name] = spec
            self.module_resource_requests[req.name] = self._parse_resource_requests(spec)
            self.module_dma_requests[req.name] = self._parse_dma_requests(spec)
            self.hal_components.update(spec.hal_components)
            self.template_files.update(spec.template_files)

        self._validate_module_dependencies(modules)

        if self.errors:
            return self._finalize()

        self._allocate_shared_buses(self._ordered_modules_for_phase(modules, {"i2c_device", "spi_bus", "spi_device"}))
        self._allocate_dedicated_resources(
            self._ordered_modules_for_phase(
                modules,
                {"uart_port", "pwm_out", "timer_ic", "timer_oc", "encoder", "advanced_timer", "dac_out", "can_port", "usb_device"},
            )
        )
        self._allocate_adc_resources(self._ordered_modules_for_phase(modules, {"adc_in"}))
        self._allocate_gpio_resources(self._ordered_modules_for_phase(modules, {"gpio_out", "gpio_in", "onewire_gpio"}))
        self._allocate_dma_resources()

        return self._finalize()

    def _allocate_shared_buses(self, modules: List[ModuleRequest]) -> None:
        for req in modules:
            spec = self.module_specs[req.name]
            for resource in self.module_resource_requests[req.name]:
                if resource.optional and not self._is_optional_signal_enabled(req, resource.signal):
                    continue
                if resource.kind == "i2c_device":
                    self._attach_i2c_device(req, spec)
                if resource.kind in {"spi_bus", "spi_device"}:
                    self._attach_spi_bus(req, resource.kind)

    def _allocate_dedicated_resources(self, modules: List[ModuleRequest]) -> None:
        for req in modules:
            for resource in self.module_resource_requests[req.name]:
                if resource.optional and not self._is_optional_signal_enabled(req, resource.signal):
                    continue
                if resource.kind == "uart_port":
                    self._allocate_uart(req)
                if resource.kind == "pwm_out":
                    self._allocate_pwm(req, signal=resource.signal)
                if resource.kind == "timer_ic":
                    self._allocate_timer_ic(req, signal=resource.signal)
                if resource.kind == "timer_oc":
                    self._allocate_timer_oc(req, signal=resource.signal)
                if resource.kind == "encoder":
                    self._allocate_encoder(req, signal=resource.signal)
                if resource.kind == "advanced_timer":
                    self._allocate_advanced_timer(req)
                if resource.kind == "dac_out":
                    self._allocate_dac(req, signal=resource.signal)
                if resource.kind == "can_port":
                    self._allocate_can(req)
                if resource.kind == "usb_device":
                    self._allocate_usb(req)

    def _allocate_adc_resources(self, modules: List[ModuleRequest]) -> None:
        for req in modules:
            for resource in self.module_resource_requests[req.name]:
                if resource.kind != "adc_in":
                    continue
                if resource.optional and not self._is_optional_signal_enabled(req, resource.signal):
                    continue
                self._allocate_adc(req, signal=resource.signal)

    def _allocate_gpio_resources(self, modules: List[ModuleRequest]) -> None:
        for req in modules:
            for resource in self.module_resource_requests[req.name]:
                if resource.kind not in {"gpio_out", "gpio_in", "onewire_gpio"}:
                    continue
                if resource.optional and not self._is_optional_signal_enabled(req, resource.signal):
                    continue
                self._allocate_gpio(req, signal=resource.signal, resource_kind=resource.kind)

    def _attach_i2c_device(self, req: ModuleRequest, spec: ModuleSpec) -> None:
        preferred_address = req.options.get("address")
        address = self._normalize_address(preferred_address) if preferred_address is not None else None
        if address is not None and spec.address_options and address not in spec.address_options:
            self.errors.append(
                f"{req.name} requested address 0x{address:02X}, but {spec.display_name} does not support it"
            )
            return

        preferred_bus = str(req.options.get("bus", "")).upper()
        explicit_pins: Dict[str, str] = {}
        if self._is_chip_only_mode():
            scl_pin = self._require_chip_only_signal_pin(req, "scl", "i2c_device")
            sda_pin = self._require_chip_only_signal_pin(req, "sda", "i2c_device")
            if self.errors:
                return
            explicit_pins = {"scl": scl_pin, "sda": sda_pin}

        for bus in self._ordered_buses(preferred_bus):
            if bus.kind != "i2c":
                continue
            if explicit_pins and not self._match_option_to_explicit_pins(
                InterfaceOption(
                    kind=bus.kind,
                    instance=bus.bus,
                    option_id=bus.option_id,
                    signals=bus.pins,
                ),
                explicit_pins,
            ):
                continue
            chosen = self._pick_i2c_address(spec, bus, address)
            if chosen is not None:
                bus.devices.append(
                    {
                        "module": req.name,
                        "kind": req.kind,
                        "address": f"0x{chosen:02X}",
                    }
                )
                self._record_module_interface(req.name, "i2c", bus.bus)
                return

        options = list(self.chip.interfaces.get("i2c", ()))
        preferred_scl_pins = set(self._preferred_board_pins(req.kind, "scl", resource_kind="i2c_device"))
        preferred_sda_pins = set(self._preferred_board_pins(req.kind, "sda", resource_kind="i2c_device"))
        if preferred_bus:
            options.sort(key=lambda item: 0 if item.instance == preferred_bus else 1)
        elif preferred_scl_pins or preferred_sda_pins:
            options.sort(
                key=lambda item: (
                    0
                    if self._i2c_option_matches_preference(item, preferred_scl_pins, preferred_sda_pins)
                    else 1
                )
            )

        for option in options:
            if explicit_pins and not self._match_option_to_explicit_pins(option, explicit_pins):
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._pins_available(option.signals.values()):
                continue

            chosen = self._pick_i2c_address(spec, None, address)
            if chosen is None:
                continue

            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} bus allocation",
            )
            self.buses.append(
                BusAssignment(
                    bus=option.instance,
                    kind="i2c",
                    option_id=option.option_id,
                    pins=dict(option.signals),
                    devices=[
                        {
                            "module": req.name,
                            "kind": req.kind,
                            "address": f"0x{chosen:02X}",
                        }
                    ],
                    notes=["I2C bus requires external pull-up resistors."],
                )
            )
            self._record_module_interface(req.name, "i2c", option.instance)
            return

        if self._is_chip_only_mode():
            pin_text = ", ".join(f"{signal}={pin}" for signal, pin in explicit_pins.items())
            self.errors.append(f"{req.name} could not match any I2C bus to the explicit chip_only wiring ({pin_text})")
        else:
            self.errors.append(f"{req.name} could not be assigned an I2C bus")

    def _attach_spi_bus(self, req: ModuleRequest, resource_kind: str) -> None:
        preferred_bus = self._preferred_instance(req, "bus", "instance")
        explicit_pins: Dict[str, str] = {}
        if self._is_chip_only_mode():
            sck_pin = self._require_chip_only_signal_pin(req, "sck", resource_kind)
            miso_pin = self._require_chip_only_signal_pin(req, "miso", resource_kind)
            mosi_pin = self._require_chip_only_signal_pin(req, "mosi", resource_kind)
            if self.errors:
                return
            explicit_pins = {"sck": sck_pin, "miso": miso_pin, "mosi": mosi_pin}
            nss_pin = self._normalize_pin(self._find_preferred_signal_pin(req, "nss"))
            if nss_pin:
                explicit_pins["nss"] = nss_pin

        for bus in self._ordered_buses(preferred_bus):
            if bus.kind != "spi":
                continue
            if preferred_bus and bus.bus != preferred_bus:
                continue
            if explicit_pins and not self._match_option_to_explicit_pins(
                InterfaceOption(
                    kind=bus.kind,
                    instance=bus.bus,
                    option_id=bus.option_id,
                    signals=bus.pins,
                ),
                explicit_pins,
            ):
                continue
            bus.devices.append(
                {
                    "module": req.name,
                    "kind": req.kind,
                    "resource_kind": resource_kind,
                }
            )
            self._record_module_interface(req.name, "spi", bus.bus)
            self.hal_components.update({"GPIO", "SPI"})
            return

        options = list(self.chip.interfaces.get("spi", ()))
        preferred_sck_pins = set(self._preferred_board_pins(req.kind, "sck", resource_kind=resource_kind))
        preferred_miso_pins = set(self._preferred_board_pins(req.kind, "miso", resource_kind=resource_kind))
        preferred_mosi_pins = set(self._preferred_board_pins(req.kind, "mosi", resource_kind=resource_kind))
        preferred_nss_pins = set(self._preferred_board_pins(req.kind, "nss", resource_kind=resource_kind))
        if preferred_bus:
            options.sort(key=lambda item: 0 if item.instance == preferred_bus else 1)
        elif preferred_sck_pins or preferred_miso_pins or preferred_mosi_pins or preferred_nss_pins:
            options.sort(
                key=lambda item: (
                    0
                    if self._spi_option_matches_preference(
                        item,
                        preferred_sck_pins,
                        preferred_miso_pins,
                        preferred_mosi_pins,
                        preferred_nss_pins,
                    )
                    else 1
                )
            )

        for option in options:
            if explicit_pins and not self._match_option_to_explicit_pins(option, explicit_pins):
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._pins_available(option.signals.values()):
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} SPI allocation",
            )
            self.buses.append(
                BusAssignment(
                    bus=option.instance,
                    kind="spi",
                    option_id=option.option_id,
                    pins=dict(option.signals),
                    devices=[
                        {
                            "module": req.name,
                            "kind": req.kind,
                            "resource_kind": resource_kind,
                        }
                    ],
                    notes=["SPI bus devices usually need per-device chip-select handling."],
                )
            )
            self._record_module_interface(req.name, "spi", option.instance)
            self.hal_components.update({"GPIO", "SPI"})
            return

        if self._is_chip_only_mode():
            pin_text = ", ".join(f"{signal}={pin}" for signal, pin in explicit_pins.items())
            self.errors.append(f"{req.name} could not match any SPI bus to the explicit chip_only wiring ({pin_text})")
        elif preferred_bus:
            self.errors.append(f"{req.name} could not be assigned requested SPI bus {preferred_bus}")
        else:
            self.errors.append(f"{req.name} could not be assigned an SPI bus")

    def _allocate_uart(self, req: ModuleRequest) -> None:
        preferred_instance = str(req.options.get("instance", "")).upper()
        options = list(self.chip.interfaces.get("uart", ()))
        explicit_pins: Dict[str, str] = {}
        if self._is_chip_only_mode():
            tx_pin = self._require_chip_only_signal_pin(req, "tx", "uart_port")
            rx_pin = self._require_chip_only_signal_pin(req, "rx", "uart_port")
            if self.errors:
                return
            explicit_pins = {"tx": tx_pin, "rx": rx_pin}
        preferred_tx_pins = set(self._preferred_board_pins(req.kind, "tx", resource_kind="uart_port"))
        preferred_rx_pins = set(self._preferred_board_pins(req.kind, "rx", resource_kind="uart_port"))
        if preferred_instance:
            options.sort(key=lambda item: 0 if item.instance == preferred_instance else 1)
        elif preferred_tx_pins or preferred_rx_pins:
            options.sort(
                key=lambda item: (
                    0
                    if (
                        (not preferred_tx_pins or self._normalize_pin(item.signals.get("tx", "")) in preferred_tx_pins)
                        and (not preferred_rx_pins or self._normalize_pin(item.signals.get("rx", "")) in preferred_rx_pins)
                    )
                    else 1
                )
            )

        for option in options:
            if explicit_pins and not self._match_option_to_explicit_pins(option, explicit_pins):
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._pins_available(option.signals.values()):
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} UART allocation",
            )
            return

        if self._is_chip_only_mode():
            pin_text = ", ".join(f"{signal}={pin}" for signal, pin in explicit_pins.items())
            self.errors.append(f"{req.name} could not match any UART resource to the explicit chip_only wiring ({pin_text})")
        else:
            self.errors.append(f"{req.name} could not be assigned a UART resource")

    def _allocate_pwm(self, req: ModuleRequest, signal: str) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        if self._is_chip_only_mode() and not preferred_pin_normalized:
            self.errors.append(
                f"{req.name} uses board=chip_only, so signal {signal} for pwm_out must specify an exact pin in module options"
            )
            return
        explicit_preference = bool(preferred_instance or preferred_pin_normalized)

        for option in self.chip.interfaces.get("pwm", ()):
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_normalized and preferred_pin_normalized not in {
                self._normalize_pin(pin) for pin in option.signals.values()
            }:
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._timer_role_available(option.instance, "pwm"):
                continue
            if not self._pins_available(option.signals.values()):
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} PWM allocation",
            )
            self._claim_timer_role(option.instance, "pwm", req.name)
            self.hal_components.update({"GPIO", "TIM"})
            return

        if explicit_preference:
            requested = preferred_instance or preferred_pin_normalized
            self.errors.append(f"{req.name} could not be assigned requested PWM resource {requested}")
        else:
            self.errors.append(f"{req.name} could not be assigned a PWM channel")

    def _allocate_timer_ic(self, req: ModuleRequest, signal: str) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        if self._is_chip_only_mode() and not preferred_pin_normalized:
            self.errors.append(
                f"{req.name} uses board=chip_only, so signal {signal} for timer_ic must specify an exact pin in module options"
            )
            return
        explicit_preference = bool(preferred_instance or preferred_pin_normalized)

        for option in self._iter_matching_timer_ic_options(req, signal):
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_normalized and preferred_pin_normalized not in {
                self._normalize_pin(pin) for pin in option.signals.values()
            }:
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._timer_role_available(option.instance, "timer_ic"):
                continue
            if not self._pins_available(option.signals.values()):
                continue
            pin = next(iter(option.signals.values()))
            timer_name, channel_name = self._split_timer_instance(option.instance)
            if not timer_name or not channel_name:
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} timer input capture allocation",
            )
            self._claim_timer_role(option.instance, "timer_ic", req.name)
            self.timer_ic_allocations.append(
                {
                    "module": req.name,
                    "signal": signal,
                    "pin": self._normalize_pin(pin),
                    "instance": option.instance,
                    "timer": timer_name,
                    "channel_name": channel_name,
                    "channel_macro": f"TIM_CHANNEL_{channel_name.replace('CH', '')}",
                    "irq": self._timer_capture_irq(timer_name),
                }
            )
            self.hal_components.update({"GPIO", "TIM"})
            return

        if explicit_preference:
            requested = preferred_instance or preferred_pin_normalized
            self.errors.append(f"{req.name} could not be assigned requested timer input capture resource {requested}")
        else:
            self.errors.append(f"{req.name} could not be assigned a timer input capture channel")

    def _allocate_timer_oc(self, req: ModuleRequest, signal: str) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        if self._is_chip_only_mode() and not preferred_pin_normalized:
            self.errors.append(
                f"{req.name} uses board=chip_only, so signal {signal} for timer_oc must specify an exact pin in module options"
            )
            return
        explicit_preference = bool(preferred_instance or preferred_pin_normalized)

        for option in self._iter_matching_timer_oc_options(req, signal):
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_normalized and preferred_pin_normalized not in {
                self._normalize_pin(pin) for pin in option.signals.values()
            }:
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._timer_role_available(option.instance, "timer_oc"):
                continue
            if not self._pins_available(option.signals.values()):
                continue
            pin = next(iter(option.signals.values()))
            timer_name, channel_name = self._split_timer_instance(option.instance)
            if not timer_name or not channel_name:
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} timer output compare allocation",
            )
            self._claim_timer_role(option.instance, "timer_oc", req.name)
            self.timer_oc_allocations.append(
                {
                    "module": req.name,
                    "signal": signal,
                    "pin": self._normalize_pin(pin),
                    "instance": option.instance,
                    "timer": timer_name,
                    "channel_name": channel_name,
                    "channel_macro": f"TIM_CHANNEL_{channel_name.replace('CH', '')}",
                }
            )
            self.hal_components.update({"GPIO", "TIM"})
            return

        if explicit_preference:
            requested = preferred_instance or preferred_pin_normalized
            self.errors.append(f"{req.name} could not be assigned requested timer output compare resource {requested}")
        else:
            self.errors.append(f"{req.name} could not be assigned a timer output compare channel")

    def _allocate_encoder(self, req: ModuleRequest, signal: str) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin_a = self._normalize_pin(
            (req.options.get("pins", {}) or {}).get("a")
            or req.options.get("pin_a")
            or req.options.get("phase_a_pin")
            or req.options.get("a")
            or ""
        )
        preferred_pin_b = self._normalize_pin(
            (req.options.get("pins", {}) or {}).get("b")
            or req.options.get("pin_b")
            or req.options.get("phase_b_pin")
            or req.options.get("b")
            or ""
        )
        if self._is_chip_only_mode() and (not preferred_pin_a or not preferred_pin_b):
            self.errors.append(
                f"{req.name} uses board=chip_only, so encoder signals a and b must specify exact pins in module options"
            )
            return
        explicit_preference = bool(preferred_instance or preferred_pin_a or preferred_pin_b)

        for option in self._iter_matching_encoder_options(req):
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            option_pin_a = self._normalize_pin(option.signals.get("a", ""))
            option_pin_b = self._normalize_pin(option.signals.get("b", ""))
            if preferred_pin_a and preferred_pin_a != option_pin_a:
                continue
            if preferred_pin_b and preferred_pin_b != option_pin_b:
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._timer_role_available(option.instance, "encoder"):
                continue
            if not self._pins_available(option.signals.values()):
                continue
            timer_name, _channel_name = self._split_timer_instance(option.instance)
            if not timer_name:
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=timer_name,
                option=option,
                reason=f"{timer_name} encoder allocation",
            )
            self._claim_timer_role(timer_name, "encoder", req.name)
            self.encoder_allocations.append(
                {
                    "module": req.name,
                    "signal": signal,
                    "instance": timer_name,
                    "timer": timer_name,
                    "pins": {
                        "a": option_pin_a,
                        "b": option_pin_b,
                    },
                    "channel_a_name": "CH1",
                    "channel_b_name": "CH2",
                    "channel_a_macro": "TIM_CHANNEL_1",
                    "channel_b_macro": "TIM_CHANNEL_2",
                }
            )
            self.hal_components.update({"GPIO", "TIM"})
            return

        if explicit_preference:
            requested = preferred_instance or preferred_pin_a or preferred_pin_b
            self.errors.append(f"{req.name} could not be assigned requested encoder resource {requested}")
        else:
            self.errors.append(f"{req.name} could not be assigned an encoder timer")

    def _allocate_advanced_timer(self, req: ModuleRequest) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        explicit_preference = bool(preferred_instance)

        for option in self._iter_matching_advanced_timer_options(req):
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._timer_role_available(option.instance, "advanced_timer"):
                continue
            if option.signals and not self._pins_available(option.signals.values()):
                continue
            timer_name, _channel_name = self._split_timer_instance(option.instance)
            if not timer_name:
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=timer_name,
                option=option,
                reason=f"{timer_name} advanced timer allocation",
            )
            self._claim_timer_role(timer_name, "advanced_timer", req.name)
            self.advanced_timer_allocations.append(
                {
                    "module": req.name,
                    "signal": "timer",
                    "instance": timer_name,
                    "timer": timer_name,
                    "pins": {key: self._normalize_pin(pin) for key, pin in option.signals.items()},
                }
            )
            self.hal_components.add("TIM")
            if option.signals:
                self.hal_components.add("GPIO")
            return

        if explicit_preference:
            self.errors.append(f"{req.name} could not be assigned requested advanced timer {preferred_instance}")
        else:
            self.errors.append(f"{req.name} could not be assigned an advanced timer")

    def _allocate_adc(self, req: ModuleRequest, signal: str) -> None:
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        if self._is_chip_only_mode() and not preferred_pin:
            self.errors.append(
                f"{req.name} uses board=chip_only, so signal {signal} for adc_in must specify an exact pin in module options"
            )
            return

        if preferred_pin:
            selection = self._select_adc_channel(self._normalize_pin(preferred_pin), preferred_instance)
            if selection is not None:
                pin, descriptor = selection
                if self._pin_available(pin):
                    self._claim_pin(req.name, signal, pin, "user-selected ADC pin", resource_kind="adc_in")
                    self._record_module_interface(req.name, "adc", str(descriptor.get("instance", "")))
                    self.adc_allocations.append(
                        {
                            "module": req.name,
                            "signal": signal,
                            "pin": pin,
                            "instance": str(descriptor.get("instance", "")).strip().upper(),
                            "channel": str(descriptor.get("channel", "")).strip().upper(),
                        }
                    )
                    self.hal_components.update({"GPIO", "ADC"})
                    return
                self.errors.append(f"{req.name} requested pin {pin}, but it is not available")
                return
            requested = preferred_instance or self._normalize_pin(preferred_pin)
            self.errors.append(f"{req.name} requested ADC resource {requested}, but no matching analog channel exists")
            return

        for pin in self._preferred_board_pins(req.kind, signal):
            selection = self._select_adc_channel(pin, preferred_instance)
            if selection is None:
                continue
            chosen_pin, descriptor = selection
            if not self._pin_available(chosen_pin, allow_board_reserved=True):
                continue
            self._claim_pin(req.name, signal, chosen_pin, f"{self.board} board profile ADC preference", resource_kind="adc_in")
            self._record_module_interface(req.name, "adc", str(descriptor.get("instance", "")))
            self.adc_allocations.append(
                {
                    "module": req.name,
                    "signal": signal,
                    "pin": chosen_pin,
                    "instance": str(descriptor.get("instance", "")).strip().upper(),
                    "channel": str(descriptor.get("channel", "")).strip().upper(),
                }
            )
            self.hal_components.update({"GPIO", "ADC"})
            return

        for pin in self._ordered_adc_pins():
            selection = self._select_adc_channel(pin, preferred_instance)
            if selection is None:
                continue
            chosen_pin, descriptor = selection
            if not self._pin_available(chosen_pin):
                continue
            self._claim_pin(req.name, signal, chosen_pin, "adc_in allocation", resource_kind="adc_in")
            self._record_module_interface(req.name, "adc", str(descriptor.get("instance", "")))
            self.adc_allocations.append(
                {
                    "module": req.name,
                    "signal": signal,
                    "pin": chosen_pin,
                    "instance": str(descriptor.get("instance", "")).strip().upper(),
                    "channel": str(descriptor.get("channel", "")).strip().upper(),
                }
            )
            self.hal_components.update({"GPIO", "ADC"})
            return

        if preferred_instance:
            self.errors.append(f"{req.name} could not be assigned an ADC channel on {preferred_instance}")
        else:
            self.errors.append(f"{req.name} could not be assigned an ADC input")

    def _allocate_dac(self, req: ModuleRequest, signal: str) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        if self._is_chip_only_mode() and not preferred_pin_normalized:
            self.errors.append(
                f"{req.name} uses board=chip_only, so signal {signal} for dac_out must specify an exact pin in module options"
            )
            return
        explicit_preference = bool(preferred_instance or preferred_pin_normalized)

        preferred_board_pins = self._preferred_board_pins(req.kind, signal, resource_kind="dac_out")
        options = list(self._iter_matching_dac_options(req, signal))
        if not preferred_instance and not preferred_pin_normalized and preferred_board_pins:
            options.sort(
                key=lambda item: (
                    0
                    if any(
                        self._normalize_pin(pin) in preferred_board_pins
                        for pin in item.signals.values()
                    )
                    else 1
                )
            )

        for option in options:
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_normalized and preferred_pin_normalized not in {
                self._normalize_pin(pin) for pin in option.signals.values()
            }:
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._pins_available(option.signals.values()):
                continue
            pin = next(iter(option.signals.values()), "")
            if not pin:
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} DAC allocation",
            )
            dac_instance, channel_name = self._split_dac_instance(option.instance)
            self._record_module_interface(req.name, "dac", dac_instance)
            self.dac_allocations.append(
                {
                    "module": req.name,
                    "signal": signal,
                    "pin": self._normalize_pin(pin),
                    "instance": option.instance,
                    "dac": dac_instance,
                    "channel_name": channel_name,
                    "channel_macro": self._dac_channel_macro(channel_name),
                }
            )
            self.hal_components.update({"GPIO", "DAC"})
            return

        if explicit_preference:
            requested = preferred_instance or preferred_pin_normalized
            self.errors.append(f"{req.name} could not be assigned requested DAC resource {requested}")
        else:
            self.errors.append(f"{req.name} could not be assigned a DAC output")

    def _allocate_can(self, req: ModuleRequest) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        options = list(self._can_options())
        explicit_pins: Dict[str, str] = {}
        if self._is_chip_only_mode():
            tx_pin = self._require_chip_only_signal_pin(req, "tx", "can_port")
            rx_pin = self._require_chip_only_signal_pin(req, "rx", "can_port")
            if self.errors:
                return
            explicit_pins = {"tx": tx_pin, "rx": rx_pin}
        preferred_tx_pins = set(self._preferred_board_pins(req.kind, "tx", resource_kind="can_port"))
        preferred_rx_pins = set(self._preferred_board_pins(req.kind, "rx", resource_kind="can_port"))
        if preferred_instance:
            options.sort(key=lambda item: 0 if item.instance == preferred_instance else 1)
        elif preferred_tx_pins or preferred_rx_pins:
            options.sort(
                key=lambda item: (
                    0
                    if (
                        (not preferred_tx_pins or self._normalize_pin(item.signals.get("tx", "")) in preferred_tx_pins)
                        and (not preferred_rx_pins or self._normalize_pin(item.signals.get("rx", "")) in preferred_rx_pins)
                    )
                    else 1
                )
            )

        for option in options:
            if explicit_pins and not self._match_option_to_explicit_pins(option, explicit_pins):
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._pins_available(option.signals.values()):
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} CAN allocation",
            )
            self.can_allocations.append(
                {
                    "module": req.name,
                    "instance": option.instance,
                    "pins": {key: self._normalize_pin(pin) for key, pin in option.signals.items()},
                }
            )
            self.hal_components.update({"GPIO", "CAN"})
            return

        if self._is_chip_only_mode():
            pin_text = ", ".join(f"{signal}={pin}" for signal, pin in explicit_pins.items())
            self.errors.append(f"{req.name} could not match any CAN resource to the explicit chip_only wiring ({pin_text})")
        elif preferred_instance:
            self.errors.append(f"{req.name} could not be assigned requested CAN resource {preferred_instance}")
        else:
            self.errors.append(f"{req.name} could not be assigned a CAN peripheral")

    def _allocate_usb(self, req: ModuleRequest) -> None:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        options = list(self._usb_options())
        explicit_pins: Dict[str, str] = {}
        if self._is_chip_only_mode():
            dm_pin = self._require_chip_only_signal_pin(req, "dm", "usb_device")
            dp_pin = self._require_chip_only_signal_pin(req, "dp", "usb_device")
            if self.errors:
                return
            explicit_pins = {"dm": dm_pin, "dp": dp_pin}
        preferred_dm_pins = set(self._preferred_board_pins(req.kind, "dm", resource_kind="usb_device"))
        preferred_dp_pins = set(self._preferred_board_pins(req.kind, "dp", resource_kind="usb_device"))
        if preferred_instance:
            options.sort(key=lambda item: 0 if item.instance == preferred_instance else 1)
        elif preferred_dm_pins or preferred_dp_pins:
            options.sort(
                key=lambda item: (
                    0
                    if (
                        (not preferred_dm_pins or self._normalize_pin(item.signals.get("dm", "")) in preferred_dm_pins)
                        and (not preferred_dp_pins or self._normalize_pin(item.signals.get("dp", "")) in preferred_dp_pins)
                    )
                    else 1
                )
            )

        for option in options:
            if explicit_pins and not self._match_option_to_explicit_pins(option, explicit_pins):
                continue
            if option.option_id in self.used_interface_options:
                continue
            if not self._pins_available(option.signals.values()):
                continue
            self._claim_interface_option(
                module_name=req.name,
                signal_prefix=option.instance,
                option=option,
                reason=f"{option.instance} USB device allocation",
            )
            self.usb_allocations.append(
                {
                    "module": req.name,
                    "instance": option.instance,
                    "pins": {key: self._normalize_pin(pin) for key, pin in option.signals.items()},
                }
            )
            self.hal_components.update({"GPIO", "PCD"})
            return

        if self._is_chip_only_mode():
            pin_text = ", ".join(f"{signal}={pin}" for signal, pin in explicit_pins.items())
            self.errors.append(
                f"{req.name} could not match any USB device resource to the explicit chip_only wiring ({pin_text})"
            )
        elif preferred_instance:
            self.errors.append(f"{req.name} could not be assigned requested USB device resource {preferred_instance}")
        else:
            self.errors.append(f"{req.name} could not be assigned a USB device peripheral")

    def _allocate_gpio(self, req: ModuleRequest, signal: str, resource_kind: str) -> None:
        requires_exti = self._is_exti_signal(signal)
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        if self._is_chip_only_mode() and not preferred_pin:
            self.errors.append(
                f"{req.name} uses board=chip_only, so signal {signal} for {resource_kind} must specify an exact pin in module options"
            )
            return
        if preferred_pin:
            pin = self._normalize_pin(preferred_pin)
            if self._gpio_candidate_available(pin, requires_exti=requires_exti):
                self._claim_pin(req.name, signal, pin, "user-selected pin", resource_kind=resource_kind)
                return
            if not self._pin_available(pin):
                self.errors.append(f"{req.name} requested pin {pin}, but it is not available")
            else:
                line = self._exti_line_for_pin(pin)
                owner = self.used_exti_lines.get(line if line is not None else -1, "")
                self.errors.append(
                    f"{req.name} requested pin {pin}, but EXTI line {line} is already used by {owner or 'another signal'}"
                )
            return

        for board_pin in self._preferred_board_pins(req.kind, signal, resource_kind=resource_kind):
            pin = self._normalize_pin(board_pin)
            if self._gpio_candidate_available(pin, requires_exti=requires_exti, allow_board_reserved=True):
                self._claim_pin(
                    req.name,
                    signal,
                    pin,
                    f"{self.board} board profile preference",
                    resource_kind=resource_kind,
                )
                return

        for pin in self.chip.gpio_preference:
            if self._gpio_candidate_available(pin, requires_exti=requires_exti):
                self._claim_pin(req.name, signal, pin, f"{resource_kind} allocation", resource_kind=resource_kind)
                return

        if requires_exti:
            self.errors.append(f"{req.name} could not be assigned a GPIO pin with a free EXTI line for signal {signal}")
        else:
            self.errors.append(f"{req.name} could not be assigned a GPIO pin for signal {signal}")

    def _ordered_buses(self, preferred_bus: str) -> List[BusAssignment]:
        if not preferred_bus:
            return list(self.buses)
        return sorted(self.buses, key=lambda item: 0 if item.bus == preferred_bus else 1)

    def _ordered_modules_for_phase(self, modules: List[ModuleRequest], resource_kinds: Set[str]) -> List[ModuleRequest]:
        relevant = [req for req in modules if self._active_phase_requests(req, resource_kinds)]
        return sorted(
            relevant,
            key=lambda req: (
                self._phase_candidate_count(req, resource_kinds),
                -len(self._active_phase_requests(req, resource_kinds)),
                req.name,
            ),
        )

    def _active_phase_requests(self, req: ModuleRequest, resource_kinds: Set[str]) -> List[ParsedResourceRequest]:
        resources: List[ParsedResourceRequest] = []
        for resource in self.module_resource_requests.get(req.name, []):
            if resource.kind not in resource_kinds:
                continue
            if resource.optional and not self._is_optional_signal_enabled(req, resource.signal):
                continue
            resources.append(resource)
        return resources

    def _phase_candidate_count(self, req: ModuleRequest, resource_kinds: Set[str]) -> int:
        requests = self._active_phase_requests(req, resource_kinds)
        if not requests:
            return 10_000
        return max(1, sum(self._resource_candidate_count(req, resource) for resource in requests))

    def _resource_candidate_count(self, req: ModuleRequest, resource: ParsedResourceRequest) -> int:
        if resource.kind == "i2c_device":
            spec = self.module_specs.get(req.name)
            preferred_address = req.options.get("address")
            address = self._normalize_address(preferred_address) if preferred_address is not None else None
            reusable = sum(
                1
                for bus in self.buses
                if bus.kind == "i2c" and spec is not None and self._pick_i2c_address(spec, bus, address) is not None
            )
            fresh = sum(
                1
                for option in self.chip.interfaces.get("i2c", ())
                if option.option_id not in self.used_interface_options and self._pins_available(option.signals.values())
            )
            return reusable + fresh
        if resource.kind in {"spi_bus", "spi_device"}:
            reusable = sum(1 for bus in self.buses if bus.kind == "spi")
            fresh = sum(
                1
                for option in self._iter_matching_spi_options(req)
                if self._pins_available(option.signals.values())
            )
            return reusable + fresh
        if resource.kind == "uart_port":
            return sum(1 for option in self._iter_matching_uart_options(req) if self._pins_available(option.signals.values()))
        if resource.kind == "pwm_out":
            return sum(
                1
                for option in self._iter_matching_pwm_options(req, resource.signal)
                if self._timer_role_available(option.instance, "pwm") and self._pins_available(option.signals.values())
            )
        if resource.kind == "timer_ic":
            return sum(
                1
                for option in self._iter_matching_timer_ic_options(req, resource.signal)
                if self._timer_role_available(option.instance, "timer_ic") and self._pins_available(option.signals.values())
            )
        if resource.kind == "timer_oc":
            return sum(
                1
                for option in self._iter_matching_timer_oc_options(req, resource.signal)
                if self._timer_role_available(option.instance, "timer_oc") and self._pins_available(option.signals.values())
            )
        if resource.kind == "encoder":
            return sum(
                1
                for option in self._iter_matching_encoder_options(req)
                if self._timer_role_available(option.instance, "encoder") and self._pins_available(option.signals.values())
            )
        if resource.kind == "advanced_timer":
            return sum(
                1
                for option in self._iter_matching_advanced_timer_options(req)
                if self._timer_role_available(option.instance, "advanced_timer")
                and (not option.signals or self._pins_available(option.signals.values()))
            )
        if resource.kind == "adc_in":
            return self._count_adc_candidates(req, resource.signal, resource_kind=resource.kind)
        if resource.kind == "dac_out":
            return sum(
                1
                for option in self._iter_matching_dac_options(req, resource.signal)
                if self._pins_available(option.signals.values())
            )
        if resource.kind == "can_port":
            return sum(1 for option in self._iter_matching_can_options(req) if self._pins_available(option.signals.values()))
        if resource.kind == "usb_device":
            return sum(1 for option in self._iter_matching_usb_options(req) if self._pins_available(option.signals.values()))
        if resource.kind in {"gpio_out", "gpio_in", "onewire_gpio"}:
            return self._count_gpio_candidates(
                req,
                resource.signal,
                requires_exti=self._is_exti_signal(resource.signal),
                resource_kind=resource.kind,
            )
        return 1

    def _iter_matching_spi_options(self, req: ModuleRequest) -> List[InterfaceOption]:
        preferred_bus = self._preferred_instance(req, "bus", "instance")
        options = list(self.chip.interfaces.get("spi", ()))
        if preferred_bus:
            options = [item for item in options if item.instance == preferred_bus]
        return [item for item in options if item.option_id not in self.used_interface_options]

    def _iter_matching_uart_options(self, req: ModuleRequest) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).upper()
        options = list(self.chip.interfaces.get("uart", ()))
        if preferred_instance:
            options = [item for item in options if item.instance == preferred_instance]
        return [item for item in options if item.option_id not in self.used_interface_options]

    def _iter_matching_pwm_options(self, req: ModuleRequest, signal: str) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        options: List[InterfaceOption] = []
        for option in self.chip.interfaces.get("pwm", ()):
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_normalized and preferred_pin_normalized not in {
                self._normalize_pin(pin) for pin in option.signals.values()
            }:
                continue
            if option.option_id in self.used_interface_options:
                continue
            options.append(option)
        return options

    def _iter_matching_timer_ic_options(self, req: ModuleRequest, signal: str) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        options: List[InterfaceOption] = []
        for option in self._timer_ic_options():
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_normalized and preferred_pin_normalized not in {
                self._normalize_pin(pin) for pin in option.signals.values()
            }:
                continue
            if option.option_id in self.used_interface_options:
                continue
            options.append(option)
        return options

    def _iter_matching_timer_oc_options(self, req: ModuleRequest, signal: str) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        options: List[InterfaceOption] = []
        for option in self._timer_oc_options():
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_normalized and preferred_pin_normalized not in {
                self._normalize_pin(pin) for pin in option.signals.values()
            }:
                continue
            if option.option_id in self.used_interface_options:
                continue
            options.append(option)
        return options

    def _iter_matching_encoder_options(self, req: ModuleRequest) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin_a = self._normalize_pin(
            req.options.get("pin_a")
            or req.options.get("phase_a_pin")
            or req.options.get("a")
            or ""
        )
        preferred_pin_b = self._normalize_pin(
            req.options.get("pin_b")
            or req.options.get("phase_b_pin")
            or req.options.get("b")
            or ""
        )
        options: List[InterfaceOption] = []
        for option in self._encoder_options():
            if preferred_instance and option.instance != preferred_instance and option.option_id != preferred_instance:
                continue
            if preferred_pin_a and self._normalize_pin(option.signals.get("a", "")) != preferred_pin_a:
                continue
            if preferred_pin_b and self._normalize_pin(option.signals.get("b", "")) != preferred_pin_b:
                continue
            if option.option_id in self.used_interface_options:
                continue
            options.append(option)
        return options

    def _iter_matching_advanced_timer_options(self, req: ModuleRequest) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        options = list(self._advanced_timer_options())
        if preferred_instance:
            options = [item for item in options if item.instance == preferred_instance or item.option_id == preferred_instance]
        return [item for item in options if item.option_id not in self.used_interface_options]

    def _iter_matching_dac_options(self, req: ModuleRequest, signal: str) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_pin_normalized = self._normalize_pin(preferred_pin) if preferred_pin else ""
        options = list(self._dac_options())
        if preferred_instance:
            options = [item for item in options if item.instance == preferred_instance or item.option_id == preferred_instance]
        if preferred_pin_normalized:
            options = [
                item
                for item in options
                if preferred_pin_normalized in {self._normalize_pin(pin) for pin in item.signals.values()}
            ]
        return [item for item in options if item.option_id not in self.used_interface_options]

    def _iter_matching_can_options(self, req: ModuleRequest) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        options = list(self._can_options())
        if preferred_instance:
            options = [item for item in options if item.instance == preferred_instance]
        return [item for item in options if item.option_id not in self.used_interface_options]

    def _iter_matching_usb_options(self, req: ModuleRequest) -> List[InterfaceOption]:
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        options = list(self._usb_options())
        if preferred_instance:
            options = [item for item in options if item.instance == preferred_instance]
        return [item for item in options if item.option_id not in self.used_interface_options]

    def _count_adc_candidates(self, req: ModuleRequest, signal: str, resource_kind: str = "adc_in") -> int:
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        preferred_instance = str(req.options.get("instance", "")).strip().upper()
        if preferred_pin:
            selection = self._select_adc_channel(self._normalize_pin(preferred_pin), preferred_instance)
            if selection is None:
                return 0
            pin, _descriptor = selection
            return 1 if self._pin_available(pin) else 0

        board_pins = []
        for pin in self._preferred_board_pins(req.kind, signal, resource_kind=resource_kind):
            selection = self._select_adc_channel(pin, preferred_instance)
            if selection is None:
                continue
            chosen_pin, _descriptor = selection
            if self._pin_available(chosen_pin, allow_board_reserved=True):
                board_pins.append(chosen_pin)
        if board_pins:
            return len(board_pins)

        return sum(
            1
            for pin in self._ordered_adc_pins()
            if (selection := self._select_adc_channel(pin, preferred_instance)) is not None
            and self._pin_available(selection[0])
        )

    def _count_gpio_candidates(
        self,
        req: ModuleRequest,
        signal: str,
        requires_exti: bool = False,
        resource_kind: str = "",
    ) -> int:
        preferred_pin = self._find_preferred_signal_pin(req, signal)
        if preferred_pin:
            return 1 if self._gpio_candidate_available(self._normalize_pin(preferred_pin), requires_exti=requires_exti) else 0

        board_pins = [
            pin
            for pin in self._preferred_board_pins(req.kind, signal, resource_kind=resource_kind)
            if self._gpio_candidate_available(pin, requires_exti=requires_exti, allow_board_reserved=True)
        ]
        if board_pins:
            return len(board_pins)

        return sum(
            1
            for pin in self.chip.gpio_preference
            if self._gpio_candidate_available(pin, requires_exti=requires_exti)
        )

    def _ordered_adc_pins(self) -> List[str]:
        ordered: List[str] = []
        known_adc_pins = {self._normalize_pin(pin) for pin in self.chip.adc_pins}
        known_adc_pins.update(self._normalize_pin(pin) for pin in self.chip.adc_channels)
        for pin in self.chip.gpio_preference:
            normalized = self._normalize_pin(pin)
            if normalized in known_adc_pins and normalized not in ordered:
                ordered.append(normalized)
        for pin in sorted(known_adc_pins, key=self._pin_sort_key):
            if pin not in ordered:
                ordered.append(pin)
        return ordered

    def _select_adc_channel(self, pin: str, preferred_instance: str = "") -> tuple[str, Dict[str, str]] | None:
        normalized_pin = self._normalize_pin(pin)
        if normalized_pin not in self._adc_capable_pins():
            return None
        for descriptor in self._adc_channels_for_pin(normalized_pin):
            instance = str(descriptor.get("instance", "")).strip().upper()
            if preferred_instance and instance != preferred_instance:
                continue
            channel = str(descriptor.get("channel", "")).strip().upper()
            if not instance or not channel:
                continue
            return normalized_pin, {"instance": instance, "channel": channel}
        return None

    def _adc_capable_pins(self) -> Set[str]:
        pins = {self._normalize_pin(pin) for pin in self.chip.adc_pins}
        pins.update(self._normalize_pin(pin) for pin in self.chip.adc_channels)
        return pins

    def _adc_channels_for_pin(self, pin: str) -> List[Dict[str, str]]:
        normalized = self._normalize_pin(pin)
        channels = self.chip.adc_channels.get(normalized)
        if channels:
            return [dict(item) for item in channels]
        inferred = self._infer_adc_channels_for_pin(normalized)
        return [inferred] if inferred is not None else []

    def _infer_adc_channels_for_pin(self, pin: str) -> Dict[str, str] | None:
        if self.chip.family != "STM32F1":
            return None
        if len(pin) < 3:
            return None
        port = pin[1]
        try:
            number = int(pin[2:])
        except ValueError:
            return None
        channel_number: int | None = None
        if port == "A" and 0 <= number <= 7:
            channel_number = number
        elif port == "B" and number in {0, 1}:
            channel_number = 8 + number
        elif port == "C" and 0 <= number <= 5:
            channel_number = 10 + number
        if channel_number is None:
            return None
        return {
            "instance": "ADC1",
            "channel": f"ADC_CHANNEL_{channel_number}",
        }

    def _pick_i2c_address(
        self,
        spec: ModuleSpec,
        bus: Optional[BusAssignment],
        preferred: Optional[int],
    ) -> Optional[int]:
        taken = set()
        if bus is not None:
            for device in bus.devices:
                taken.add(int(str(device["address"]), 16))

        if preferred is not None:
            return None if preferred in taken else preferred

        for address in spec.address_options:
            if address not in taken:
                return address
        return None if spec.address_options else 0x00

    def _claim_interface_option(
        self,
        module_name: str,
        signal_prefix: str,
        option: InterfaceOption,
        reason: str,
    ) -> None:
        self.used_interface_options.add(option.option_id)
        self._record_module_interface(module_name, option.kind, option.instance)
        for signal, pin in option.signals.items():
            self.used_pins[pin] = f"{module_name}:{signal_prefix}.{signal}"
            self.assignments.append(
                PinAssignment(
                    module=module_name,
                    signal=f"{signal_prefix.lower()}.{signal}",
                    pin=pin,
                    reason=reason,
                )
            )
            if pin in self.chip.reserved_pins:
                self.warnings.append(f"{module_name} uses reserved debug pin {pin}")
            if pin in self.avoid_pins:
                self.warnings.append(f"{module_name} uses avoided pin {pin}")

    def _timer_oc_options(self) -> List[InterfaceOption]:
        configured = list(self.chip.interfaces.get("timer_oc", ()))
        if configured:
            return configured
        return [
            InterfaceOption(
                option_id=option.option_id,
                kind="timer_oc",
                instance=option.instance,
                signals={"out": next(iter(option.signals.values()))},
                shareable=False,
                notes=tuple(option.notes),
            )
            for option in self.chip.interfaces.get("pwm", ())
            if option.signals
        ]

    def _timer_ic_options(self) -> List[InterfaceOption]:
        configured = list(self.chip.interfaces.get("timer_ic", ()))
        if configured:
            return configured
        return [
            InterfaceOption(
                option_id=option.option_id,
                kind="timer_ic",
                instance=option.instance,
                signals={"capture": next(iter(option.signals.values()))},
                shareable=False,
                notes=tuple(option.notes),
            )
            for option in self.chip.interfaces.get("pwm", ())
            if option.signals
        ]

    def _encoder_options(self) -> List[InterfaceOption]:
        configured = list(self.chip.interfaces.get("encoder", ()))
        if configured:
            return configured

        grouped: Dict[str, Dict[str, str]] = {}
        for option in self.chip.interfaces.get("pwm", ()):
            timer_name, channel_name = self._split_timer_instance(option.instance)
            if channel_name not in {"CH1", "CH2"} or not option.signals:
                continue
            grouped.setdefault(timer_name, {})
            grouped[timer_name][channel_name] = self._normalize_pin(next(iter(option.signals.values())))

        inferred: List[InterfaceOption] = []
        for timer_name, channels in sorted(grouped.items()):
            if "CH1" not in channels or "CH2" not in channels:
                continue
            inferred.append(
                InterfaceOption(
                    option_id=f"{timer_name}_ENCODER",
                    kind="encoder",
                    instance=timer_name,
                    signals={"a": channels["CH1"], "b": channels["CH2"]},
                    shareable=False,
                    notes=("Inferred encoder mode from timer CH1/CH2 pin pair.",),
                )
            )
        return inferred

    def _advanced_timer_options(self) -> List[InterfaceOption]:
        configured = list(self.chip.interfaces.get("advanced_timer", ()))
        if configured:
            return configured

        advanced_timer_names = {"TIM1", "TIM8", "TIM20"}
        inferred_names: Set[str] = set()
        for kind in ("pwm", "timer_ic", "timer_oc", "encoder"):
            for option in self.chip.interfaces.get(kind, ()):
                timer_name, _channel_name = self._split_timer_instance(option.instance)
                if timer_name in advanced_timer_names:
                    inferred_names.add(timer_name)
        return [
            InterfaceOption(
                option_id=f"{timer_name}_ADVANCED",
                kind="advanced_timer",
                instance=timer_name,
                signals={},
                shareable=False,
                notes=("Inferred advanced timer instance from timer peripheral catalog.",),
            )
            for timer_name in sorted(inferred_names)
        ]

    def _dac_options(self) -> List[InterfaceOption]:
        configured = list(self.chip.interfaces.get("dac", ()))
        if configured:
            return configured
        return list(self.chip.interfaces.get("dac_out", ()))

    def _can_options(self) -> List[InterfaceOption]:
        configured = list(self.chip.interfaces.get("can", ()))
        if configured:
            return configured
        return list(self.chip.interfaces.get("can_port", ()))

    def _usb_options(self) -> List[InterfaceOption]:
        configured = list(self.chip.interfaces.get("usb", ()))
        if configured:
            return configured
        return list(self.chip.interfaces.get("usb_device", ()))

    def _timer_role_available(self, instance: str, role: str) -> bool:
        timer_name, _channel_name = self._split_timer_instance(instance)
        if not timer_name:
            return True
        existing = self.timer_instance_roles.get(timer_name)
        return existing in {None, role}

    def _claim_timer_role(self, instance: str, role: str, module_name: str) -> None:
        timer_name, _channel_name = self._split_timer_instance(instance)
        if not timer_name:
            return
        existing = self.timer_instance_roles.get(timer_name)
        if existing is None:
            self.timer_instance_roles[timer_name] = role
            return
        if existing != role:
            self.errors.append(
                f"{module_name} requested {role} on {timer_name}, but that timer is already reserved for {existing}."
            )

    def _split_timer_instance(self, instance: str) -> tuple[str, str]:
        normalized = str(instance).strip().upper()
        if "_" not in normalized:
            return normalized, ""
        timer_name, channel_name = normalized.split("_", 1)
        return timer_name, channel_name

    def _split_dac_instance(self, instance: str) -> tuple[str, str]:
        normalized = str(instance).strip().upper()
        if "_CH" in normalized:
            dac_name, channel_name = normalized.split("_", 1)
            return dac_name, channel_name
        if normalized.endswith("1") or normalized.endswith("2"):
            return normalized[:-1] or normalized, f"CH{normalized[-1]}"
        return normalized, ""

    def _dac_channel_macro(self, channel_name: str) -> str:
        normalized = str(channel_name).strip().upper()
        if normalized.startswith("CH") and normalized[2:].isdigit():
            return f"DAC_CHANNEL_{normalized[2:]}"
        return normalized

    def _timer_capture_irq(self, timer_name: str) -> str:
        mapping = {
            "TIM1": "TIM1_CC_IRQn",
            "TIM2": "TIM2_IRQn",
            "TIM3": "TIM3_IRQn",
            "TIM4": "TIM4_IRQn",
        }
        return mapping.get(str(timer_name).strip().upper(), f"{str(timer_name).strip().upper()}_IRQn")

    def _pin_sort_key(self, pin: str) -> tuple[str, int]:
        normalized = self._normalize_pin(pin)
        if len(normalized) < 3:
            return normalized, 0
        try:
            number = int(normalized[2:])
        except ValueError:
            number = 0
        return normalized[:2], number

    def _claim_pin(
        self,
        module_name: str,
        signal: str,
        pin: str,
        reason: str,
        resource_kind: str = "",
    ) -> None:
        self.used_pins[pin] = f"{module_name}:{signal}"
        self.assignments.append(PinAssignment(module=module_name, signal=signal, pin=pin, reason=reason))
        if self._is_exti_signal(signal):
            self._claim_exti_line(module_name, signal, pin, reason)
        if pin in {"PC13", "PC14", "PC15"}:
            self.warnings.append(f"{module_name} is assigned to {pin}, which is better for low-speed GPIO use")
        if pin in self.avoid_pins:
            self.warnings.append(f"{module_name} uses avoided pin {pin}")

    def _gpio_candidate_available(
        self,
        pin: str,
        requires_exti: bool = False,
        allow_board_reserved: bool = False,
    ) -> bool:
        if not self._pin_available(pin, allow_board_reserved=allow_board_reserved):
            return False
        if requires_exti and not self._exti_available_for_pin(pin):
            return False
        return True

    def _pins_available(self, pins: Iterable[str], allow_board_reserved: bool = False) -> bool:
        return all(self._pin_available(pin, allow_board_reserved=allow_board_reserved) for pin in pins)

    def _pin_available(self, pin: str, allow_board_reserved: bool = False) -> bool:
        normalized = self._normalize_pin(pin)
        if normalized in self.avoid_pins:
            return False
        reason = self.used_pins.get(normalized)
        if reason is None:
            return True
        return allow_board_reserved and reason == "reserved by board profile"

    def _normalize_pin(self, pin: object) -> str:
        return str(pin).strip().upper()

    def _normalize_address(self, value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value, 16) if value.lower().startswith("0x") else int(value)
        raise ValueError(f"Unsupported address format: {value!r}")

    def _find_preferred_signal_pin(self, req: ModuleRequest, signal: str) -> object:
        signal_aliases = self._signal_aliases(signal)
        nested_pins = req.options.get("pins", {})
        if isinstance(nested_pins, dict):
            for key in signal_aliases:
                if key in nested_pins and nested_pins[key]:
                    return nested_pins[key]
        for key in signal_aliases:
            if key in req.options and req.options[key]:
                return req.options[key]
        if signal in {"control", "input", "dq", "out", "capture", "in"} and req.options.get("pin"):
            return req.options["pin"]
        return None

    def _is_optional_signal_enabled(self, req: ModuleRequest, signal: str) -> bool:
        signal_aliases = self._signal_aliases(signal)
        for alias in signal_aliases:
            if alias in req.options and req.options[alias]:
                return True
            for option_name in (f"use_{alias}", f"use_{alias}_pin", f"enable_{alias}"):
                if option_name in req.options and bool(req.options[option_name]):
                    return True
        return False

    def _signal_aliases(self, signal: str) -> List[str]:
        aliases = [signal]
        if signal == "int":
            aliases.append("interrupt")
        return aliases

    def _preferred_instance(self, req: ModuleRequest, *option_names: str) -> str:
        for option_name in option_names:
            value = str(req.options.get(option_name, "")).strip().upper()
            if value:
                return value
        return ""

    def _is_chip_only_mode(self) -> bool:
        return self.board_profile is None and self.board == "chip_only"

    def _require_chip_only_signal_pin(self, req: ModuleRequest, signal: str, resource_kind: str) -> str:
        pin = self._normalize_pin(self._find_preferred_signal_pin(req, signal))
        if pin:
            return pin
        self.errors.append(
            f"{req.name} uses board=chip_only, so signal {signal} for {resource_kind} must specify an exact pin in module options"
        )
        return ""

    def _match_option_to_explicit_pins(self, option: InterfaceOption, explicit_pins: Dict[str, str]) -> bool:
        for signal, pin in explicit_pins.items():
            if self._normalize_pin(option.signals.get(signal, "")) != self._normalize_pin(pin):
                return False
        return True

    def _record_module_interface(self, module_name: str, kind: str, instance: str) -> None:
        normalized_kind = str(kind).strip().lower()
        normalized_instance = str(instance).strip().upper()
        if not normalized_kind or not normalized_instance:
            return
        self.module_interface_bindings.setdefault(module_name, {})
        self.module_interface_bindings[module_name][normalized_kind] = normalized_instance

    def _module_interface_instance(self, module_name: str, kind: str) -> str:
        return self.module_interface_bindings.get(module_name, {}).get(str(kind).strip().lower(), "")

    def _is_exti_signal(self, signal: str) -> bool:
        return str(signal).strip().lower() in {"int", "interrupt"}

    def _exti_line_for_pin(self, pin: str) -> int | None:
        normalized = self._normalize_pin(pin)
        if len(normalized) < 3 or not normalized[2:].isdigit():
            return None
        return int(normalized[2:])

    def _exti_irq_for_line(self, line: int) -> str:
        if 0 <= line <= 4:
            return f"EXTI{line}_IRQn"
        if 5 <= line <= 9:
            return "EXTI9_5_IRQn"
        return "EXTI15_10_IRQn"

    def _exti_available_for_pin(self, pin: str) -> bool:
        line = self._exti_line_for_pin(pin)
        if line is None:
            return False
        return line not in self.used_exti_lines

    def _claim_exti_line(self, module_name: str, signal: str, pin: str, reason: str) -> None:
        line = self._exti_line_for_pin(pin)
        if line is None:
            self.errors.append(f"{module_name} signal {signal} uses invalid EXTI-capable pin name {pin}")
            return
        owner = self.used_exti_lines.get(line)
        if owner is not None:
            self.errors.append(
                f"{module_name} signal {signal} on {pin} conflicts with EXTI line {line} already used by {owner}"
            )
            return
        irq = self._exti_irq_for_line(line)
        self.used_exti_lines[line] = f"{module_name}.{signal}"
        self.exti_allocations.append(
            {
                "module": module_name,
                "signal": signal,
                "pin": pin,
                "line": line,
                "irq": irq,
                "reason": reason,
            }
        )
        self.hal_components.add("GPIO")

    def _parse_dma_requests(self, spec: ModuleSpec) -> List[ParsedDmaRequest]:
        parsed: List[ParsedDmaRequest] = []
        tokens = list(spec.dma_requests)
        if not tokens:
            tokens = self._default_dma_request_tokens(spec)
        for token in tokens:
            parsed.append(self._parse_dma_request_token(token))
        return parsed

    def _parse_dma_request_token(self, token: str) -> ParsedDmaRequest:
        text = str(token).strip()
        if not text:
            raise ValueError("Empty DMA request token")
        optional = False
        shared_scope = ""
        if text.endswith("?"):
            text = text[:-1].strip()
            optional = True
        parts = [part.strip() for part in text.split(":") if part.strip()]
        if not parts:
            raise ValueError("Empty DMA request token")
        request = parts[0]
        if len(parts) >= 2:
            flags = {part.lower() for part in parts[1:]}
            optional = "optional" in flags or optional
            if "shared_bus" in flags or "shared" in flags:
                shared_scope = "bus"
        if not shared_scope and request.lower().startswith("i2c_"):
            shared_scope = "bus"
        return ParsedDmaRequest(request=request, optional=optional, shared_scope=shared_scope)

    def _default_dma_request_tokens(self, spec: ModuleSpec) -> List[str]:
        requests = self._parse_resource_requests(spec)
        if (
            str(spec.bus_kind).strip().lower() == "i2c"
            and "DMA" in {str(component).strip().upper() for component in spec.hal_components}
            and any(item.kind == "i2c_device" for item in requests)
        ):
            return ["i2c_rx:optional:shared_bus", "i2c_tx:optional:shared_bus"]
        return []

    def _allocate_dma_resources(self) -> None:
        pending: List[Dict[str, object]] = []
        for req in self.modules:
            for dma_request in self.module_dma_requests.get(req.name, []):
                resolved = self._resolve_dma_request_candidates(req, dma_request)
                if resolved is None:
                    continue
                pending.append(resolved)

        grouped_pending = self._group_dma_requests(pending)
        grouped_pending.sort(
            key=lambda item: (
                1 if bool(item.get("optional", False)) else 0,
                len(item.get("channels", [])),
                str(item.get("request", "")),
                ",".join(item.get("modules", [])),
            )
        )

        for item in grouped_pending:
            channels = [str(channel).strip() for channel in item.get("channels", []) if str(channel).strip()]
            chosen = next((channel for channel in channels if channel not in self.used_dma_channels), "")
            if chosen:
                owners = list(item.get("modules", []))
                owner_label = (
                    f"{item['request']} shared by {', '.join(owners)}"
                    if len(owners) > 1
                    else f"{owners[0]}.{item['request']}"
                )
                self.used_dma_channels[chosen] = owner_label
                self.dma_allocations.append(
                    {
                        "module": owners[0] if owners else "",
                        "modules": owners,
                        "request": item["request"],
                        "channel": chosen,
                        "source": item["source"],
                        "shared_scope": item.get("shared_scope", ""),
                        "instance": item.get("instance", ""),
                        "peripheral_kind": item.get("peripheral_kind", ""),
                    }
                )
                self.hal_components.add("DMA")
                continue
            if item.get("optional"):
                self.warnings.append(
                    f"Optional DMA request {item['request']} for {', '.join(item.get('modules', []))} could not be assigned a free channel."
                )
                continue
            if channels:
                owners = ", ".join(f"{channel} ({self.used_dma_channels.get(channel, 'used')})" for channel in channels)
                self.errors.append(
                    f"{', '.join(item.get('modules', []))} requires DMA request {item['request']}, but all candidate channels are busy: {owners}"
                )
            else:
                self.errors.append(
                    f"{', '.join(item.get('modules', []))} requires DMA request {item['request']}, but chip {self.chip.name} has no matching DMA mapping."
                )

    def _group_dma_requests(self, pending: List[Dict[str, object]]) -> List[Dict[str, object]]:
        grouped: Dict[str, Dict[str, object]] = {}
        for item in pending:
            modules = [str(item.get("module", "")).strip()] if str(item.get("module", "")).strip() else []
            share_key = str(item.get("share_key", "")).strip()
            unique_key = (
                share_key
                if share_key
                else f"module:{','.join(modules)}|request:{item.get('request', '')}|instance:{item.get('instance', '')}"
            )
            entry = grouped.setdefault(
                unique_key,
                {
                    "modules": [],
                    "request": str(item.get("request", "")).strip(),
                    "channels": list(item.get("channels", [])),
                    "optional": bool(item.get("optional", False)),
                    "source": str(item.get("source", "")).strip(),
                    "shared_scope": str(item.get("shared_scope", "")).strip(),
                    "instance": str(item.get("instance", "")).strip(),
                    "peripheral_kind": str(item.get("peripheral_kind", "")).strip(),
                },
            )
            for module in modules:
                if module and module not in entry["modules"]:
                    entry["modules"].append(module)
            entry["optional"] = bool(entry["optional"]) and bool(item.get("optional", False))
            if not entry["channels"]:
                entry["channels"] = list(item.get("channels", []))
            elif item.get("channels"):
                current = [str(channel).strip() for channel in entry["channels"] if str(channel).strip()]
                new = [str(channel).strip() for channel in item.get("channels", []) if str(channel).strip()]
                if current != new:
                    intersection = [channel for channel in current if channel in new]
                    entry["channels"] = intersection if intersection else current
        return list(grouped.values())

    def _resolve_dma_request_candidates(
        self,
        req: ModuleRequest,
        dma_request: ParsedDmaRequest,
    ) -> Dict[str, object] | None:
        raw_request = str(dma_request.request).strip()
        if not raw_request:
            return None
        request_key = raw_request.upper()
        source = "chip_request_map"
        channels: List[str] = []
        recognized_request = False
        peripheral_kind = ""
        instance = ""
        share_key = ""

        if request_key in self.chip.dma_request_map:
            channels = list(self.chip.dma_request_map[request_key])
            recognized_request = True
            peripheral_kind, instance = self._infer_dma_request_owner(request_key)
        elif request_key in {channel.upper() for channel in self.chip.dma_channels}:
            channels = [channel for channel in self.chip.dma_channels if channel.upper() == request_key]
            source = "direct_channel"
            recognized_request = True
        else:
            normalized = raw_request.lower()
            if normalized in {"uart_rx", "uart_tx"}:
                instance = self._module_interface_instance(req.name, "uart")
                suffix = "RX" if normalized.endswith("rx") else "TX"
                peripheral_kind = "uart"
                if not instance:
                    message = f"{req.name} declares DMA request {raw_request}, but no UART instance was assigned."
                    if dma_request.optional:
                        self.warnings.append(message)
                        return None
                    self.errors.append(message)
                    return None
                request_key = f"{instance}_{suffix}"
                recognized_request = True
            elif normalized in {"i2c_rx", "i2c_tx"}:
                instance = self._module_interface_instance(req.name, "i2c")
                suffix = "RX" if normalized.endswith("rx") else "TX"
                peripheral_kind = "i2c"
                if not instance:
                    message = f"{req.name} declares DMA request {raw_request}, but no I2C instance was assigned."
                    if dma_request.optional:
                        self.warnings.append(message)
                        return None
                    self.errors.append(message)
                    return None
                request_key = f"{instance}_{suffix}"
                recognized_request = True
            elif "_" in request_key:
                recognized_request = True
                peripheral_kind, instance = self._infer_dma_request_owner(request_key)

            if request_key in self.chip.dma_request_map:
                channels = list(self.chip.dma_request_map[request_key])
                source = "chip_request_map"
            elif recognized_request and self.chip.dma_channels:
                channels = list(self.chip.dma_channels)
                source = "generic_dma_pool"

        if not peripheral_kind or not instance:
            peripheral_kind, instance = self._infer_dma_request_owner(request_key)
        if dma_request.shared_scope == "bus" and peripheral_kind == "i2c" and instance:
            share_key = f"bus:{instance}:{request_key}"

        return {
            "module": req.name,
            "request": request_key,
            "channels": channels,
            "optional": dma_request.optional,
            "source": source,
            "shared_scope": dma_request.shared_scope,
            "share_key": share_key,
            "instance": instance,
            "peripheral_kind": peripheral_kind,
        }

    def _infer_dma_request_owner(self, request_key: str) -> tuple[str, str]:
        normalized = str(request_key).strip().upper()
        if "_" not in normalized:
            return "", ""
        instance, _direction = normalized.rsplit("_", 1)
        if instance.startswith("I2C"):
            return "i2c", instance
        if instance.startswith(("USART", "UART", "LPUART")):
            return "uart", instance
        return "", instance

    def _preferred_board_pins(self, module_kind: str, signal: str, resource_kind: str = "") -> List[str]:
        if self.board_profile is None or not self.board_profile.preferred_signals:
            return []
        candidates: List[str] = []
        keys = [
            f"{module_kind}.{signal}",
            f"{module_kind}.*",
        ]
        normalized_resource_kind = str(resource_kind).strip()
        if normalized_resource_kind:
            keys.extend(
                [
                    f"{normalized_resource_kind}.{signal}",
                    f"{normalized_resource_kind}.*",
                ]
            )
        keys.append(f"*.{signal}")
        for key in keys:
            for pin in self.board_profile.preferred_signals.get(key, ()):
                normalized = self._normalize_pin(pin)
                if normalized not in candidates:
                    candidates.append(normalized)
        return candidates

    def _i2c_option_matches_preference(
        self,
        option: InterfaceOption,
        preferred_scl_pins: Set[str],
        preferred_sda_pins: Set[str],
    ) -> bool:
        scl_pin = self._normalize_pin(option.signals.get("scl", ""))
        sda_pin = self._normalize_pin(option.signals.get("sda", ""))
        return (
            (not preferred_scl_pins or scl_pin in preferred_scl_pins)
            and (not preferred_sda_pins or sda_pin in preferred_sda_pins)
        )

    def _spi_option_matches_preference(
        self,
        option: InterfaceOption,
        preferred_sck_pins: Set[str],
        preferred_miso_pins: Set[str],
        preferred_mosi_pins: Set[str],
        preferred_nss_pins: Set[str],
    ) -> bool:
        sck_pin = self._normalize_pin(option.signals.get("sck", ""))
        miso_pin = self._normalize_pin(option.signals.get("miso", ""))
        mosi_pin = self._normalize_pin(option.signals.get("mosi", ""))
        nss_pin = self._normalize_pin(option.signals.get("nss", ""))
        return (
            (not preferred_sck_pins or sck_pin in preferred_sck_pins)
            and (not preferred_miso_pins or miso_pin in preferred_miso_pins)
            and (not preferred_mosi_pins or mosi_pin in preferred_mosi_pins)
            and (not preferred_nss_pins or nss_pin in preferred_nss_pins)
        )

    def _parse_resource_requests(self, spec: ModuleSpec) -> List[ParsedResourceRequest]:
        parsed: List[ParsedResourceRequest] = []
        for token in spec.resource_requests:
            parsed.append(self._parse_resource_request_token(token))
        return parsed

    def _parse_resource_request_token(self, token: str) -> ParsedResourceRequest:
        parts = [part.strip() for part in str(token).split(":") if part.strip()]
        if not parts:
            raise ValueError("Empty resource request token")

        kind = parts[0]
        signal = RESOURCE_DEFAULT_SIGNALS.get(kind, kind)
        optional = False

        if len(parts) >= 2:
            signal = parts[1]
        if len(parts) >= 3:
            optional = parts[2].lower() == "optional"
        if signal.endswith("?"):
            signal = signal[:-1]
            optional = True

        return ParsedResourceRequest(kind=kind, signal=signal, optional=optional)

    def _finalize(self) -> PlanResult:
        feasible = not self.errors
        summary = (
            f"Planning succeeded and assigned {len(self.assignments)} signals."
            if feasible
            else f"Planning failed with {len(self.errors)} blocking issues."
        )
        next_steps = [
            "Generate HAL initialization code from project_ir.",
            "Generate the Keil5 project from hal_components and template_files.",
            "Fill in any module templates that are still placeholders.",
        ]
        return PlanResult(
            feasible=feasible,
            chip=self.chip.name,
            board=self.board,
            summary=summary,
            warnings=self.warnings,
            errors=self.errors,
            assignments=self.assignments,
            buses=self.buses,
            hal_components=sorted(self.hal_components),
            template_files=sorted(self.template_files),
            next_steps=next_steps,
            project_ir=self._build_project_ir(feasible),
        )

    def _validate_module_dependencies(self, modules: List[ModuleRequest]) -> None:
        available_kinds = {req.kind for req in modules}
        available_names = {req.name for req in modules}
        for req in modules:
            spec = self.module_specs.get(req.name)
            if spec is None:
                continue
            missing = [
                dependency
                for dependency in spec.depends_on
                if dependency not in available_kinds and dependency not in available_names
            ]
            if missing:
                self.errors.append(
                    f"{req.name} requires dependent modules {', '.join(missing)}, but they were not requested"
                )

    def _build_project_ir(self, feasible: bool) -> Dict[str, object]:
        clock_plan = self._resolve_clock_plan()
        resolved_app_logic = render_app_logic_from_ir(self.app_logic, self.app_logic_ir)
        runtime_expectations = normalize_app_logic_ir_acceptance(self.app_logic_ir.get("acceptance", {}))
        return {
            "schema_version": "0.2",
            "target": {
                "chip": self.chip.name,
                "family": self.chip.family,
                "package": self.chip.package,
                "flash_kb": self.chip.flash_kb,
                "ram_kb": self.chip.ram_kb,
                "board": self.board,
                "board_display_name": self.board_profile.display_name if self.board_profile is not None else self.board,
                "board_definition_path": self.board_profile.definition_path if self.board_profile is not None else "",
                "board_capabilities": [dict(item) for item in self.board_profile.capabilities]
                if self.board_profile is not None
                else [],
                "board_notes": list(self.board_profile.notes) if self.board_profile is not None else [],
                "keep_swd": self.keep_swd,
                "chip_definition_path": self.chip.definition_path,
            },
            "constraints": {
                "reserved_pins": sorted(
                    pin for pin, reason in self.used_pins.items() if "reserved" in reason
                ),
                "avoid_pins": sorted(self.avoid_pins),
                "used_exti_lines": [
                    {
                        "line": line,
                        "owner": owner,
                        "irq": self._exti_irq_for_line(line),
                    }
                    for line, owner in sorted(self.used_exti_lines.items())
                ],
                "used_dma_channels": [
                    {
                        "channel": channel,
                        "owner": owner,
                    }
                    for channel, owner in sorted(self.used_dma_channels.items())
                ],
                "clock_plan": clock_plan,
            },
            "modules": [
                {
                    "name": req.name,
                    "kind": req.kind,
                    "options": req.options,
                    "summary": self.module_specs[req.name].summary if req.name in self.module_specs else "",
                    "definition_path": self.module_specs[req.name].definition_path if req.name in self.module_specs else "",
                    "template_root": self.module_specs[req.name].template_root if req.name in self.module_specs else "",
                    "plugin_path": self.module_specs[req.name].plugin_path if req.name in self.module_specs else "",
                    "template_files": list(self.module_specs[req.name].template_files) if req.name in self.module_specs else [],
                    "resource_requests": list(self.module_specs[req.name].resource_requests) if req.name in self.module_specs else [],
                    "depends_on": list(self.module_specs[req.name].depends_on) if req.name in self.module_specs else [],
                    "init_priority": self.module_specs[req.name].init_priority if req.name in self.module_specs else 0,
                    "loop_priority": self.module_specs[req.name].loop_priority if req.name in self.module_specs else 0,
                    "c_top_template": list(self.module_specs[req.name].c_top_template) if req.name in self.module_specs else [],
                    "c_init_template": list(self.module_specs[req.name].c_init_template) if req.name in self.module_specs else [],
                    "c_loop_template": list(self.module_specs[req.name].c_loop_template) if req.name in self.module_specs else [],
                    "c_callbacks_template": list(self.module_specs[req.name].c_callbacks_template) if req.name in self.module_specs else [],
                    "irqs": list(self.module_specs[req.name].irqs) if req.name in self.module_specs else [],
                    "simulation": (
                        json.loads(json.dumps(self.module_specs[req.name].simulation, ensure_ascii=False))
                        if req.name in self.module_specs
                        else {}
                    ),
                    "dma_requests": [
                        (
                            item.request
                            + ("?" if item.optional else "")
                            + (":shared_bus" if item.shared_scope == "bus" else "")
                        )
                        for item in self.module_dma_requests.get(req.name, [])
                    ],
                    "interfaces": dict(self.module_interface_bindings.get(req.name, {})),
                }
                for req in self.modules
            ],
            "peripherals": {
                "buses": [
                    {
                        "bus": bus.bus,
                        "kind": bus.kind,
                        "pins": bus.pins,
                        "devices": bus.devices,
                        "dma": [
                            dict(item)
                            for item in self.dma_allocations
                            if str(item.get("instance", "")).strip().upper() == str(bus.bus).strip().upper()
                            and str(item.get("peripheral_kind", "")).strip().lower() == str(bus.kind).strip().lower()
                        ],
                    }
                    for bus in self.buses
                ],
                "pwm": self._build_pwm_peripherals(),
                "adc": self._build_adc_peripherals(),
                "timer_ic": self._build_timer_ic_peripherals(),
                "timer_oc": self._build_timer_oc_peripherals(),
                "encoder": self._build_encoder_peripherals(),
                "advanced_timer": self._build_advanced_timer_peripherals(),
                "dac": self._build_dac_peripherals(),
                "can": self._build_can_peripherals(),
                "usb": self._build_usb_peripherals(),
                "signals": [
                    {
                        "module": item.module,
                        "signal": item.signal,
                        "pin": item.pin,
                    }
                    for item in self.assignments
                ],
                "exti": list(self.exti_allocations),
                "dma": list(self.dma_allocations),
            },
            "build": {
                "toolchain": "Keil5+HAL (planned)",
                "app_template": "",
                "app_logic_goal": self.app_logic_goal,
                "app_logic": dict(resolved_app_logic),
                "app_logic_ir": dict(self.app_logic_ir),
                "runtime_expectations": dict(runtime_expectations),
                "generated_files": dict(self.generated_files),
                "hal_components": sorted(self.hal_components),
                "template_files": sorted(self.template_files),
                "source_groups": {
                    "Core": [path for path in sorted(self.template_files) if path.startswith("Core/")],
                    "App": [path for path in sorted(self.template_files) if path.startswith("app/")],
                    "Modules": [path for path in sorted(self.template_files) if path.startswith("modules/")],
                },
            },
            "status": {
                "feasible": feasible,
                "warnings": list(self.warnings),
                "errors": list(self.errors),
            },
        }

    def _build_pwm_peripherals(self) -> List[Dict[str, object]]:
        module_kinds = {
            req.name: req.kind
            for req in self.modules
        }
        grouped: Dict[str, Dict[str, object]] = {}
        for item in self.assignments:
            if "." not in item.signal:
                continue
            prefix, signal = item.signal.split(".", 1)
            timer_signal = prefix.upper()
            if not timer_signal.startswith("TIM"):
                continue
            timer_name, channel_name = self._split_timer_instance(timer_signal)
            if self.timer_instance_roles.get(timer_name) != "pwm" or not channel_name.startswith("CH"):
                continue
            grouped.setdefault(
                timer_name,
                {
                    "timer": timer_name,
                    "handle": f"h{timer_name.lower()}",
                    "channels": [],
                    "pwm_profile": "default",
                },
            )
            module_kind = module_kinds.get(item.module, "")
            grouped[timer_name]["channels"].append(
                {
                    "channel_name": channel_name,
                    "channel_macro": f"TIM_CHANNEL_{channel_name.replace('CH', '')}",
                    "pin": item.pin,
                    "signal": signal,
                    "module": item.module,
                    "module_kind": module_kind,
                }
            )
            if module_kind == "sg90_servo":
                grouped[timer_name]["pwm_profile"] = "servo_50hz"
            elif module_kind == "dc_motor_pwm" and grouped[timer_name]["pwm_profile"] != "servo_50hz":
                grouped[timer_name]["pwm_profile"] = "motor_pwm"

        timers = list(grouped.values())
        for timer in timers:
            timer["channels"] = sorted(timer["channels"], key=lambda item: str(item["channel_name"]))
        return sorted(timers, key=lambda item: str(item["timer"]))

    def _build_adc_peripherals(self) -> List[Dict[str, object]]:
        grouped: Dict[str, Dict[str, object]] = {}
        for allocation in self.adc_allocations:
            instance = str(allocation.get("instance", "")).strip().upper()
            if not instance:
                continue
            grouped.setdefault(
                instance,
                {
                    "instance": instance,
                    "handle": f"h{instance.lower()}",
                    "channels": [],
                },
            )
            grouped[instance]["channels"].append(
                {
                    "module": str(allocation.get("module", "")).strip(),
                    "signal": str(allocation.get("signal", "")).strip(),
                    "pin": str(allocation.get("pin", "")).strip().upper(),
                    "channel": str(allocation.get("channel", "")).strip().upper(),
                }
            )

        adc_units = list(grouped.values())
        for unit in adc_units:
            channels = sorted(
                unit["channels"],
                key=lambda item: (
                    self._pin_sort_key(str(item.get("pin", ""))),
                    str(item.get("module", "")),
                    str(item.get("signal", "")),
                ),
            )
            for index, channel in enumerate(channels, start=1):
                channel["rank"] = index
                channel["rank_macro"] = f"ADC_REGULAR_RANK_{index}"
            unit["channels"] = channels
        return sorted(adc_units, key=lambda item: str(item["instance"]))

    def _build_timer_ic_peripherals(self) -> List[Dict[str, object]]:
        grouped: Dict[str, Dict[str, object]] = {}
        for allocation in self.timer_ic_allocations:
            timer = str(allocation.get("timer", "")).strip().upper()
            if not timer:
                continue
            grouped.setdefault(
                timer,
                {
                    "timer": timer,
                    "handle": f"h{timer.lower()}",
                    "irq": str(allocation.get("irq", "")).strip(),
                    "channels": [],
                },
            )
            grouped[timer]["channels"].append(
                {
                    "module": str(allocation.get("module", "")).strip(),
                    "signal": str(allocation.get("signal", "")).strip(),
                    "pin": str(allocation.get("pin", "")).strip().upper(),
                    "channel_name": str(allocation.get("channel_name", "")).strip().upper(),
                    "channel_macro": str(allocation.get("channel_macro", "")).strip(),
                }
            )
        timers = list(grouped.values())
        for timer in timers:
            timer["channels"] = sorted(timer["channels"], key=lambda item: str(item["channel_name"]))
        return sorted(timers, key=lambda item: str(item["timer"]))

    def _build_timer_oc_peripherals(self) -> List[Dict[str, object]]:
        grouped: Dict[str, Dict[str, object]] = {}
        for allocation in self.timer_oc_allocations:
            timer = str(allocation.get("timer", "")).strip().upper()
            if not timer:
                continue
            grouped.setdefault(
                timer,
                {
                    "timer": timer,
                    "handle": f"h{timer.lower()}",
                    "channels": [],
                },
            )
            grouped[timer]["channels"].append(
                {
                    "module": str(allocation.get("module", "")).strip(),
                    "signal": str(allocation.get("signal", "")).strip(),
                    "pin": str(allocation.get("pin", "")).strip().upper(),
                    "channel_name": str(allocation.get("channel_name", "")).strip().upper(),
                    "channel_macro": str(allocation.get("channel_macro", "")).strip(),
                }
            )
        timers = list(grouped.values())
        for timer in timers:
            timer["channels"] = sorted(timer["channels"], key=lambda item: str(item["channel_name"]))
        return sorted(timers, key=lambda item: str(item["timer"]))

    def _build_encoder_peripherals(self) -> List[Dict[str, object]]:
        encoders: List[Dict[str, object]] = []
        for allocation in self.encoder_allocations:
            timer = str(allocation.get("timer", "")).strip().upper()
            if not timer:
                continue
            encoders.append(
                {
                    "timer": timer,
                    "handle": f"h{timer.lower()}",
                    "module": str(allocation.get("module", "")).strip(),
                    "signal": str(allocation.get("signal", "")).strip(),
                    "pins": dict(allocation.get("pins", {})),
                    "channel_a_name": str(allocation.get("channel_a_name", "")).strip().upper(),
                    "channel_b_name": str(allocation.get("channel_b_name", "")).strip().upper(),
                    "channel_a_macro": str(allocation.get("channel_a_macro", "")).strip(),
                    "channel_b_macro": str(allocation.get("channel_b_macro", "")).strip(),
                }
            )
        return sorted(encoders, key=lambda item: str(item["timer"]))

    def _build_advanced_timer_peripherals(self) -> List[Dict[str, object]]:
        timers: List[Dict[str, object]] = []
        for allocation in self.advanced_timer_allocations:
            timer = str(allocation.get("timer", "")).strip().upper()
            if not timer:
                continue
            timers.append(
                {
                    "timer": timer,
                    "handle": f"h{timer.lower()}",
                    "module": str(allocation.get("module", "")).strip(),
                    "signal": str(allocation.get("signal", "")).strip(),
                    "pins": dict(allocation.get("pins", {})),
                }
            )
        return sorted(timers, key=lambda item: str(item["timer"]))

    def _build_dac_peripherals(self) -> List[Dict[str, object]]:
        grouped: Dict[str, Dict[str, object]] = {}
        for allocation in self.dac_allocations:
            dac_name = str(allocation.get("dac", "")).strip().upper()
            if not dac_name:
                continue
            grouped.setdefault(
                dac_name,
                {
                    "dac": dac_name,
                    "handle": f"h{dac_name.lower()}",
                    "channels": [],
                },
            )
            grouped[dac_name]["channels"].append(
                {
                    "module": str(allocation.get("module", "")).strip(),
                    "signal": str(allocation.get("signal", "")).strip(),
                    "pin": str(allocation.get("pin", "")).strip().upper(),
                    "instance": str(allocation.get("instance", "")).strip().upper(),
                    "channel_name": str(allocation.get("channel_name", "")).strip().upper(),
                    "channel_macro": str(allocation.get("channel_macro", "")).strip(),
                }
            )
        peripherals = list(grouped.values())
        for dac in peripherals:
            dac["channels"] = sorted(dac["channels"], key=lambda item: str(item["channel_name"]))
        return sorted(peripherals, key=lambda item: str(item["dac"]))

    def _build_can_peripherals(self) -> List[Dict[str, object]]:
        peripherals: List[Dict[str, object]] = []
        for allocation in self.can_allocations:
            instance = str(allocation.get("instance", "")).strip().upper()
            if not instance:
                continue
            peripherals.append(
                {
                    "instance": instance,
                    "handle": f"h{instance.lower()}",
                    "module": str(allocation.get("module", "")).strip(),
                    "pins": dict(allocation.get("pins", {})),
                }
            )
        return sorted(peripherals, key=lambda item: str(item["instance"]))

    def _build_usb_peripherals(self) -> List[Dict[str, object]]:
        peripherals: List[Dict[str, object]] = []
        for allocation in self.usb_allocations:
            instance = str(allocation.get("instance", "")).strip().upper()
            if not instance:
                continue
            handle = "hpcd_usb_fs" if instance in {"USB", "USB_FS", "USB_OTG_FS"} else f"h{instance.lower()}"
            peripherals.append(
                {
                    "instance": instance,
                    "handle": handle,
                    "module": str(allocation.get("module", "")).strip(),
                    "pins": dict(allocation.get("pins", {})),
                }
            )
        return sorted(peripherals, key=lambda item: str(item["instance"]))

    def _resolve_clock_plan(self) -> Dict[str, object]:
        source = "family_default"
        profile = _default_clock_profile_for_chip(self.chip)
        if self.chip.clock_profile is not None:
            source = "chip"
            profile = self.chip.clock_profile
        if self.board_profile is not None and self.board_profile.clock_profile is not None:
            source = "board"
            profile = self.board_profile.clock_profile
        return {
            "status": "configured" if profile.system_clock_config else "unset",
            "source": source,
            "summary": profile.summary,
            "cpu_clock_hz": profile.cpu_clock_hz,
            "hse_value": profile.hse_value,
            "hsi_value": profile.hsi_value,
            "lsi_value": profile.lsi_value,
            "lse_value": profile.lse_value,
            "external_clock_value": profile.external_clock_value,
            "system_clock_config": list(profile.system_clock_config),
            "notes": list(profile.notes),
        }

def plan_request(payload: Dict[str, object], packs_dir: str | Path | None = None) -> PlanResult:
    registry = load_catalog(packs_dir)
    board_name = str(payload.get("board", "")).strip().lower()
    alias_warning = ""
    if board_name in BOARD_KEY_ALIASES:
        alias_warning = (
            f"Board key {board_name} is deprecated; automatically using {BOARD_KEY_ALIASES[board_name]}."
        )
        board_name = BOARD_KEY_ALIASES[board_name]
    board_profile = None
    if board_name and board_name != "chip_only":
        board_profile = registry.boards.get(board_name)
        if board_profile is None:
            errors = [f"Unsupported board: {board_name}"]
            warning_items = [*registry.warnings, *registry.errors]
            if alias_warning:
                warning_items.append(alias_warning)
            return PlanResult(
                feasible=False,
                chip=str(payload.get("chip", "")).upper() or "(unknown)",
                board=board_name or "auto",
                summary="Planning failed because the board is not supported.",
                warnings=warning_items,
                errors=errors,
                assignments=[],
                buses=[],
                hal_components=[],
                template_files=[],
                next_steps=["Add a real board profile before generating a project."],
                project_ir={
                    "schema_version": "0.2",
                    "status": {
                        "feasible": False,
                        "errors": errors,
                        "catalog_warnings": [*registry.warnings, *registry.errors],
                    },
                },
            )

    chip_name = str(payload.get("chip", "")).upper().strip()
    if not chip_name and board_profile is not None:
        chip_name = board_profile.chip
    chip = registry.chips.get(chip_name)
    if chip is None:
        errors = [f"Unsupported chip: {chip_name or '(empty)'}"]
        return PlanResult(
            feasible=False,
            chip=chip_name or "(unknown)",
            board=board_name or "auto",
            summary="Planning failed because the chip is not supported.",
            warnings=[*registry.warnings, *registry.errors],
            errors=errors,
            assignments=[],
            buses=[],
            hal_components=[],
            template_files=[],
            next_steps=["Add a real chip definition pack before generating a project."],
            project_ir={
                "schema_version": "0.2",
                "status": {
                    "feasible": False,
                    "errors": errors,
                    "catalog_warnings": [*registry.warnings, *registry.errors],
                },
            },
        )

    if board_profile is not None and board_profile.chip != chip.name:
        errors = [f"Board {board_profile.key} targets {board_profile.chip}, but request selected {chip.name}"]
        return PlanResult(
            feasible=False,
            chip=chip.name,
            board=board_name or "auto",
            summary="Planning failed because the board and chip do not match.",
            warnings=[*registry.warnings, *registry.errors],
            errors=errors,
            assignments=[],
            buses=[],
            hal_components=[],
            template_files=[],
            next_steps=["Use the chip declared by the board profile, or switch to board=chip_only."],
            project_ir={
                "schema_version": "0.2",
                "status": {
                    "feasible": False,
                    "errors": errors,
                    "catalog_warnings": [*registry.warnings, *registry.errors],
                },
            },
        )

    modules: List[ModuleRequest] = []
    for raw in payload.get("modules", []):
        if not isinstance(raw, dict):
            raise ValueError("Each item in modules must be an object")
        kind = str(raw.get("kind", "")).strip()
        name = str(raw.get("name", kind or "unnamed")).strip()
        options = raw.get("options", {})
        if options is None:
            options = {}
        if not isinstance(options, dict):
            raise ValueError("module.options must be an object")
        modules.append(ModuleRequest(kind=kind, name=name, options=options))

    planner = Planner(
        chip=chip,
        module_registry=registry.modules,
        board=board_name,
        board_profile=board_profile,
        keep_swd=bool(payload.get("keep_swd", True)),
        reserved_pins=payload.get("reserved_pins", []),
        avoid_pins=payload.get("avoid_pins", []),
        app_logic_goal=str(payload.get("app_logic_goal", "")).strip(),
        app_logic=payload.get("app_logic"),
        app_logic_ir=payload.get("app_logic_ir"),
        generated_files=payload.get("generated_files"),
    )
    planner.warnings.extend([*registry.warnings, *registry.errors])
    if alias_warning:
        planner.warnings.append(alias_warning)
    return planner.plan(modules)


def plan_request_file(path: str | Path, packs_dir: str | Path | None = None) -> PlanResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return plan_request(payload, packs_dir=packs_dir)


def _normalize_app_logic(value: Optional[Dict[str, object]]) -> Dict[str, str]:
    sections = {
        "AppTop": "",
        "AppInit": "",
        "AppLoop": "",
        "AppCallbacks": "",
    }
    if not isinstance(value, dict):
        return sections
    for key in sections:
        raw = value.get(key, "")
        if raw is None:
            continue
        sections[key] = str(raw).strip()
    return sections


def _default_clock_profile_for_chip(chip: ChipDefinition) -> ClockProfile:
    if str(chip.family).strip().upper() == "STM32G4":
        return ClockProfile(
            summary="Fallback family clock profile using the internal HSI and PLL.",
            cpu_clock_hz=80_000_000,
            hse_value=24_000_000,
            hsi_value=16_000_000,
            lsi_value=32_000,
            lse_value=32_768,
            external_clock_value=48_000,
            system_clock_config=(
                "    RCC_OscInitTypeDef RCC_OscInitStruct = {0};",
                "    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};",
                "",
                "    if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) {",
                "        Error_Handler();",
                "    }",
                "",
                "    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;",
                "    RCC_OscInitStruct.HSIState = RCC_HSI_ON;",
                "    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;",
                "    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;",
                "    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;",
                "    RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV2;",
                "    RCC_OscInitStruct.PLL.PLLN = 20;",
                "    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;",
                "    RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;",
                "    RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;",
                "    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {",
                "        Error_Handler();",
                "    }",
                "",
                "    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1;",
                "    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;",
                "    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;",
                "    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;",
                "    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_3) != HAL_OK) {",
                "        Error_Handler();",
                "    }",
            ),
            notes=("Fallback clock settings should be overridden by a real board profile when possible.",),
        )
    return ClockProfile(
        summary="Fallback family clock profile using the internal HSI without PLL.",
        cpu_clock_hz=8_000_000,
        hse_value=8_000_000,
        hsi_value=8_000_000,
        lsi_value=40_000,
        lse_value=32_768,
        external_clock_value=48_000,
        system_clock_config=(
            "    RCC_OscInitTypeDef RCC_OscInitStruct = {0};",
            "    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};",
            "",
            "    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;",
            "    RCC_OscInitStruct.HSIState = RCC_HSI_ON;",
            "    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;",
            "    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;",
            "    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {",
            "        Error_Handler();",
            "    }",
            "",
            "    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK",
            "                                 | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;",
            "    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;",
            "    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;",
            "    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;",
            "    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;",
            "    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK) {",
            "        Error_Handler();",
            "    }",
        ),
        notes=("Fallback clock settings should be overridden by a real board profile when possible.",),
    )
