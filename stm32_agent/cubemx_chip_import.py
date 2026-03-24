from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .extension_packs import PACK_SCHEMA_VERSION, init_packs_dir
from .path_config import resolve_configured_path


PIN_NAME_RE = re.compile(r"^(P[A-Z])(\d+)")
I2C_SIGNAL_RE = re.compile(r"^(I2C\d+)_(SCL|SDA)$")
UART_SIGNAL_RE = re.compile(r"^((?:USART|UART|LPUART)\d+)_(TX|RX)$")
SPI_SIGNAL_RE = re.compile(r"^(SPI\d+)_(NSS|SCK|MISO|MOSI)$")
PWM_SIGNAL_RE = re.compile(r"^(TIM\d+_CH\d+)$")
ADC_SIGNAL_RE = re.compile(r"^(ADC\d+)_IN(\d+)$")
CAN_SIGNAL_RE = re.compile(r"^((?:FDCAN\d+|CAN(?:\d+)?))_(RX|TX)$")
USB_SIGNAL_RE = re.compile(r"^USB_(DM|DP)$")
DAC_SIGNAL_RE = re.compile(r"^(DAC\d+)_OUT(\d+)$")


@dataclass(frozen=True)
class CubeMxChipImportResult:
    reference: str
    xml_path: str
    mcu_db_dir: str
    chip_pack_file: str
    chip_name: str
    device_name: str
    family: str
    c_define: str
    interface_counts: Dict[str, int]
    warnings: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        return {
            "reference": self.reference,
            "xml_path": self.xml_path,
            "mcu_db_dir": self.mcu_db_dir,
            "chip_pack_file": self.chip_pack_file,
            "chip_name": self.chip_name,
            "device_name": self.device_name,
            "family": self.family,
            "c_define": self.c_define,
            "interface_counts": dict(self.interface_counts),
            "warnings": list(self.warnings),
        }


def import_cubemx_chip(
    reference: str,
    chip_name: str | None = None,
    packs_dir: str | Path | None = None,
    cubemx_install_path: str | Path | None = None,
) -> CubeMxChipImportResult:
    xml_path, mcu_db_dir = resolve_cubemx_chip_xml(reference, cubemx_install_path)
    manifest, warnings = build_chip_manifest_from_cubemx_xml(xml_path, chip_name)

    root = init_packs_dir(packs_dir)
    chip_file = root / "chips" / f"{str(manifest['name']).lower()}.json"
    chip_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    interface_counts = {
        kind: len(list(options))
        for kind, options in dict(manifest.get("interfaces", {})).items()
    }
    return CubeMxChipImportResult(
        reference=reference,
        xml_path=str(xml_path),
        mcu_db_dir=str(mcu_db_dir),
        chip_pack_file=str(chip_file),
        chip_name=str(manifest["name"]),
        device_name=str(manifest["device_name"]),
        family=str(manifest["family"]),
        c_define=str(manifest["c_define"]),
        interface_counts=interface_counts,
        warnings=tuple(warnings),
    )


def resolve_cubemx_chip_xml(
    reference: str,
    cubemx_install_path: str | Path | None = None,
) -> tuple[Path, Path]:
    raw = str(reference or "").strip()
    if not raw:
        raise ValueError("reference must not be empty")

    path = Path(raw).expanduser()
    if path.exists():
        xml_path = path.resolve()
        if xml_path.suffix.lower() != ".xml":
            raise ValueError(f"CubeMX MCU definition must be an XML file: {xml_path}")
        return xml_path, xml_path.parent

    mcu_db_dir = resolve_cubemx_mcu_db_dir(cubemx_install_path)
    identifier = raw.upper().removesuffix(".XML")

    exact_path = mcu_db_dir / f"{identifier}.xml"
    if exact_path.exists():
        return exact_path.resolve(), mcu_db_dir

    candidates: List[Path] = []
    for file_path in sorted(mcu_db_dir.glob("*.xml")):
        stem = file_path.stem.upper()
        if stem == identifier:
            return file_path.resolve(), mcu_db_dir
        if stem.startswith(identifier):
            candidates.append(file_path)

    if len(candidates) == 1:
        return candidates[0].resolve(), mcu_db_dir

    if candidates:
        sample = ", ".join(path.name for path in candidates[:5])
        raise FileNotFoundError(
            f"Multiple STM32CubeMX MCU XML files match {reference!r}: {sample}. "
            "Please pass the exact RefName or XML path."
        )

    raise FileNotFoundError(
        f"STM32CubeMX MCU XML was not found for {reference!r} under {mcu_db_dir}"
    )


def resolve_cubemx_mcu_db_dir(cubemx_install_path: str | Path | None = None) -> Path:
    configured = str(cubemx_install_path).strip() if cubemx_install_path is not None else ""
    if not configured:
        configured, _ = resolve_configured_path("stm32cubemx_install_path")
        configured = configured or ""

    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path(r"D:\STM32CubeMX"),
            Path.home() / "STM32CubeMX",
        ]
    )

    checked: List[Path] = []
    for candidate in candidates:
        if not candidate:
            continue
        resolved = candidate.expanduser().resolve()
        checked.append(resolved)
        if (resolved / "db" / "mcu").exists():
            return (resolved / "db" / "mcu").resolve()
        if resolved.exists() and resolved.name.lower() == "mcu":
            return resolved

    summary = ", ".join(str(path) for path in checked) or "<unset>"
    raise FileNotFoundError(
        "STM32CubeMX MCU database was not found. Checked: "
        f"{summary}. Configure 'stm32cubemx_install_path' first."
    )


def build_chip_manifest_from_cubemx_xml(
    xml_path: str | Path,
    chip_name: str | None = None,
) -> tuple[Dict[str, object], List[str]]:
    xml_file = Path(xml_path).expanduser().resolve()
    tree = ET.parse(xml_file)
    root = tree.getroot()
    namespace = _extract_namespace(root.tag)
    ns = {"m": namespace} if namespace else {}

    ref_name = str(root.attrib.get("RefName", xml_file.stem)).strip()
    ref_name_upper = ref_name.upper()
    device_name = _normalize_device_name(ref_name)
    inferred_chip_name = _infer_chip_name(device_name)
    final_chip_name = str(chip_name or inferred_chip_name).strip().upper()
    family = str(root.attrib.get("Family", "STM32")).strip()
    package = str(root.attrib.get("Package", "")).strip()
    db_version = str(root.attrib.get("DBVersion", "")).strip()
    core = _read_text(root, "Core", ns)
    flash_kb = _safe_int(_read_text(root, "Flash", ns), default=0)
    ram_kb = _safe_int(_read_text(root, "Ram", ns), default=0)

    warnings: List[str] = []
    if not chip_name and final_chip_name != device_name:
        warnings.append(
            f"Chip name was inferred from generic CubeMX RefName {ref_name!r} as {final_chip_name!r}. "
            "If you need the exact commercial ordering code, pass it explicitly."
        )

    c_define, define_warning = _infer_c_define(device_name, family, flash_kb)
    if define_warning:
        warnings.append(define_warning)

    gpio_pins: List[str] = []
    adc_pins: set[str] = set()
    adc_channels: Dict[str, List[Dict[str, str]]] = {}
    i2c_candidates: Dict[str, Dict[str, List[str]]] = {}
    uart_candidates: Dict[str, Dict[str, List[str]]] = {}
    spi_candidates: Dict[str, Dict[str, List[str]]] = {}
    can_candidates: Dict[str, Dict[str, List[str]]] = {}
    usb_candidates: Dict[str, Dict[str, List[str]]] = {}
    dac_options: List[Dict[str, object]] = []
    pwm_options: List[Dict[str, object]] = []
    timer_ic_options: List[Dict[str, object]] = []

    for pin_element in _find_all(root, "Pin", ns):
        normalized_pin = _normalize_pin_name(pin_element.attrib.get("Name", ""))
        if not normalized_pin:
            continue
        signals = [str(item.attrib.get("Name", "")).strip().upper() for item in _find_all(pin_element, "Signal", ns)]
        if not signals:
            continue

        if normalized_pin not in gpio_pins:
            gpio_pins.append(normalized_pin)

        for signal in signals:
            adc_match = ADC_SIGNAL_RE.match(signal)
            if adc_match:
                adc_pins.add(normalized_pin)
                channel_entry = {
                    "instance": adc_match.group(1),
                    "channel": f"ADC_CHANNEL_{adc_match.group(2)}",
                }
                adc_channels.setdefault(normalized_pin, [])
                if channel_entry not in adc_channels[normalized_pin]:
                    adc_channels[normalized_pin].append(channel_entry)
                continue

            i2c_match = I2C_SIGNAL_RE.match(signal)
            if i2c_match:
                _add_candidate(i2c_candidates, i2c_match.group(1), i2c_match.group(2).lower(), normalized_pin)
                continue

            uart_match = UART_SIGNAL_RE.match(signal)
            if uart_match:
                _add_candidate(uart_candidates, uart_match.group(1), uart_match.group(2).lower(), normalized_pin)
                continue

            spi_match = SPI_SIGNAL_RE.match(signal)
            if spi_match:
                _add_candidate(spi_candidates, spi_match.group(1), spi_match.group(2).lower(), normalized_pin)
                continue

            can_match = CAN_SIGNAL_RE.match(signal)
            if can_match:
                _add_candidate(
                    can_candidates,
                    _normalize_can_instance(can_match.group(1)),
                    can_match.group(2).lower(),
                    normalized_pin,
                )
                continue

            usb_match = USB_SIGNAL_RE.match(signal)
            if usb_match:
                _add_candidate(usb_candidates, "USB_FS", usb_match.group(1).lower(), normalized_pin)
                continue

            dac_match = DAC_SIGNAL_RE.match(signal)
            if dac_match:
                dac_option = {
                    "option_id": f"{dac_match.group(1)}_CH{dac_match.group(2)}_{normalized_pin}",
                    "kind": "dac",
                    "instance": f"{dac_match.group(1)}_CH{dac_match.group(2)}",
                    "signals": {"out": normalized_pin},
                }
                if dac_option not in dac_options:
                    dac_options.append(dac_option)
                continue

            pwm_match = PWM_SIGNAL_RE.match(signal)
            if pwm_match:
                option_id = f"{pwm_match.group(1)}_{normalized_pin}"
                pwm_option = {
                    "option_id": option_id,
                    "kind": "pwm",
                    "instance": pwm_match.group(1),
                    "signals": {"out": normalized_pin},
                }
                if pwm_option not in pwm_options:
                    pwm_options.append(pwm_option)
                timer_ic_option = {
                    "option_id": option_id,
                    "kind": "timer_ic",
                    "instance": pwm_match.group(1),
                    "signals": {"capture": normalized_pin},
                }
                if timer_ic_option not in timer_ic_options:
                    timer_ic_options.append(timer_ic_option)

    gpio_sorted = tuple(sorted(dict.fromkeys(gpio_pins), key=_pin_sort_key))
    reserved_pins = tuple(pin for pin in ("PA13", "PA14") if pin in gpio_sorted)
    gpio_preference = tuple(pin for pin in gpio_sorted if pin not in reserved_pins)

    i2c_options, i2c_warnings = _build_bus_options(
        i2c_candidates,
        roles=("scl", "sda"),
        kind="i2c",
        shareable=True,
    )
    warnings.extend(i2c_warnings)

    uart_options, uart_warnings = _build_bus_options(
        uart_candidates,
        roles=("tx", "rx"),
        kind="uart",
        shareable=False,
    )
    warnings.extend(uart_warnings)

    spi_options, spi_warnings = _build_bus_options(
        spi_candidates,
        roles=("nss", "sck", "miso", "mosi"),
        kind="spi",
        shareable=True,
    )
    warnings.extend(spi_warnings)

    can_options, can_warnings = _build_bus_options(
        can_candidates,
        roles=("rx", "tx"),
        kind="can",
        shareable=False,
    )
    warnings.extend(can_warnings)

    usb_options, usb_warnings = _build_bus_options(
        usb_candidates,
        roles=("dm", "dp"),
        kind="usb",
        shareable=False,
    )
    warnings.extend(usb_warnings)

    interfaces = {
        "i2c": i2c_options,
        "uart": uart_options,
        "spi": spi_options,
        "dac": sorted(dac_options, key=lambda item: str(item["option_id"])),
        "can": can_options,
        "usb": usb_options,
        "pwm": sorted(pwm_options, key=lambda item: str(item["option_id"])),
        "timer_ic": sorted(timer_ic_options, key=lambda item: str(item["option_id"])),
    }
    interfaces = {kind: options for kind, options in interfaces.items() if options}

    manifest = {
        "schema_version": PACK_SCHEMA_VERSION,
        "kind": "chip",
        "name": final_chip_name,
        "device_name": device_name,
        "vendor": "STMicroelectronics",
        "family": family,
        "cpu_type": core or "Unknown",
        "package": package or "Unknown",
        "flash_kb": flash_kb,
        "ram_kb": ram_kb,
        "irom_start": "0x08000000",
        "iram_start": "0x20000000",
        "c_define": c_define,
        "reserved_pins": list(reserved_pins),
        "gpio_preference": list(gpio_preference),
        "adc_pins": sorted(adc_pins, key=_pin_sort_key),
        "adc_channels": {
            pin: sorted(
                channels,
                key=lambda item: (str(item.get("instance", "")), str(item.get("channel", ""))),
            )
            for pin, channels in sorted(adc_channels.items(), key=lambda item: _pin_sort_key(item[0]))
        },
        "interfaces": interfaces,
        "sources": [
            f"STM32CubeMX MCU XML: {xml_file}",
            f"STM32CubeMX DBVersion={db_version or 'unknown'}, RefName={ref_name_upper}",
        ],
    }
    return manifest, warnings


def _build_bus_options(
    candidates: Dict[str, Dict[str, List[str]]],
    roles: Tuple[str, ...],
    kind: str,
    shareable: bool,
    max_options_per_instance: int = 32,
) -> tuple[List[Dict[str, object]], List[str]]:
    options: List[Dict[str, object]] = []
    warnings: List[str] = []
    for instance in sorted(candidates):
        role_map = candidates[instance]
        if any(not role_map.get(role) for role in roles):
            continue

        unique_by_role = {
            role: tuple(sorted(dict.fromkeys(role_map[role]), key=_pin_sort_key))
            for role in roles
        }

        emitted = 0
        seen: set[Tuple[str, ...]] = set()
        for combo in product(*(unique_by_role[role] for role in roles)):
            if len(set(combo)) != len(combo):
                continue
            if combo in seen:
                continue
            seen.add(combo)
            mapping = dict(zip(roles, combo))
            option_id = "_".join([instance, *combo])
            options.append(
                {
                    "option_id": option_id,
                    "kind": kind,
                    "instance": instance,
                    "signals": mapping,
                    "shareable": shareable,
                    "notes": (
                        "Generated from STM32CubeMX pin signal list; review alternate-function pairing on constrained boards.",
                    ),
                }
            )
            emitted += 1
            if emitted >= max_options_per_instance:
                warnings.append(
                    f"{instance} generated more than {max_options_per_instance} {kind} mappings; "
                    "the list was truncated and may require manual review."
                )
                break
    return options, warnings


def _normalize_can_instance(instance: str) -> str:
    normalized = str(instance).strip().upper()
    if normalized == "CAN":
        return "CAN1"
    return normalized


def _extract_namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _find_all(element: ET.Element, tag: str, ns: Dict[str, str]) -> List[ET.Element]:
    if ns:
        return list(element.findall(f"m:{tag}", ns))
    return list(element.findall(tag))


def _read_text(root: ET.Element, tag: str, ns: Dict[str, str]) -> str:
    if ns:
        node = root.find(f"m:{tag}", ns)
    else:
        node = root.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _normalize_pin_name(raw_name: str) -> str:
    raw = str(raw_name or "").strip().upper()
    match = PIN_NAME_RE.match(raw)
    if not match:
        return ""
    return f"{match.group(1)}{int(match.group(2))}"


def _normalize_device_name(ref_name: str) -> str:
    normalized = str(ref_name or "").strip()
    if normalized.endswith("Z") and len(normalized) >= 2 and normalized[-2] in {"x", "X"}:
        normalized = normalized[:-1]
    return normalized


def _infer_chip_name(device_name: str) -> str:
    normalized = str(device_name or "").strip()
    if normalized.endswith(("x", "X")) and len(normalized) >= 2:
        return (normalized[:-1] + "6").upper()
    return normalized.upper()


def _infer_c_define(device_name: str, family: str, flash_kb: int) -> tuple[str, str]:
    prefix_match = re.match(r"^(STM32[A-Z]\d{3,4})", str(device_name or "").upper())
    prefix = prefix_match.group(1) if prefix_match else str(device_name or "").upper()

    if str(family).upper() == "STM32F1":
        for base in ("STM32F103", "STM32F101", "STM32F102"):
            if prefix.startswith(base):
                if flash_kb <= 32:
                    return f"{base}x6", ""
                if flash_kb <= 128:
                    return f"{base}xB", ""
                if flash_kb <= 256:
                    return f"{base}xE", ""
                return f"{base}xG", "F1 c_define was inferred from flash size; review the density group manually."
        for base in ("STM32F105", "STM32F107"):
            if prefix.startswith(base):
                return f"{base}xC", ""

    if prefix:
        return f"{prefix}xx", "c_define was inferred heuristically from the STM32CubeMX RefName; review it before using the pack in production."
    return "STM32_DEVICE_DEFINE", "c_define could not be inferred from the STM32CubeMX XML and was left generic."


def _safe_int(raw: str, default: int) -> int:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return int(text, 10)
    except ValueError:
        return default


def _pin_sort_key(pin: str) -> tuple[str, int]:
    match = PIN_NAME_RE.match(str(pin or "").upper())
    if not match:
        return (str(pin or ""), -1)
    return (match.group(1), int(match.group(2)))


def _add_candidate(
    bucket: Dict[str, Dict[str, List[str]]],
    instance: str,
    signal: str,
    pin: str,
) -> None:
    instance_map = bucket.setdefault(instance, {})
    pins = instance_map.setdefault(signal, [])
    if pin not in pins:
        pins.append(pin)
