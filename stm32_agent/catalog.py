from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class InterfaceOption:
    option_id: str
    kind: str
    instance: str
    signals: Dict[str, str]
    shareable: bool = False
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ClockProfile:
    summary: str = ""
    cpu_clock_hz: int = 0
    hse_value: int = 0
    hsi_value: int = 0
    lsi_value: int = 0
    lse_value: int = 32768
    external_clock_value: int = 48000
    system_clock_config: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ChipDefinition:
    name: str
    device_name: str
    vendor: str
    family: str
    cpu_type: str
    package: str
    flash_kb: int
    ram_kb: int
    irom_start: int
    iram_start: int
    c_define: str
    reserved_pins: Tuple[str, ...]
    gpio_preference: Tuple[str, ...]
    adc_pins: Tuple[str, ...]
    interfaces: Dict[str, Tuple[InterfaceOption, ...]]
    adc_channels: Dict[str, Tuple[Dict[str, str], ...]] = field(default_factory=dict)
    clock_profile: ClockProfile | None = None
    dma_channels: Tuple[str, ...] = ()
    dma_request_map: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    sources: Tuple[str, ...] = ()
    definition_path: str = ""


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    display_name: str
    summary: str
    hal_components: Tuple[str, ...]
    template_files: Tuple[str, ...]
    resource_requests: Tuple[str, ...]
    depends_on: Tuple[str, ...] = ()
    init_priority: int = 0
    loop_priority: int = 0
    c_top_template: Tuple[str, ...] = ()
    c_init_template: Tuple[str, ...] = ()
    c_loop_template: Tuple[str, ...] = ()
    c_callbacks_template: Tuple[str, ...] = ()
    irqs: Tuple[str, ...] = ()
    dma_requests: Tuple[str, ...] = ()
    address_options: Tuple[int, ...] = ()
    bus_kind: str = ""
    optional_signals: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    sources: Tuple[str, ...] = ()
    definition_path: str = ""
    template_root: str = ""
    plugin_path: str = ""
    simulation: Dict[str, object] = field(default_factory=dict)
    app_logic_snippets: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BoardProfile:
    key: str
    display_name: str
    summary: str
    chip: str
    reserved_pins: Tuple[str, ...] = ()
    avoid_pins: Tuple[str, ...] = ()
    preferred_signals: Dict[str, Tuple[str, ...]] | None = None
    clock_profile: ClockProfile | None = None
    capabilities: Tuple[Dict[str, object], ...] = ()
    notes: Tuple[str, ...] = ()
    sources: Tuple[str, ...] = ()
    definition_path: str = ""


STM32F103C8T6 = ChipDefinition(
    name="STM32F103C8T6",
    device_name="STM32F103C8",
    vendor="STMicroelectronics",
    family="STM32F1",
    cpu_type="Cortex-M3",
    package="LQFP48",
    flash_kb=64,
    ram_kb=20,
    irom_start=0x08000000,
    iram_start=0x20000000,
    c_define="STM32F103xB",
    reserved_pins=("PA13", "PA14"),
    gpio_preference=(
        "PC13",
        "PB12",
        "PB13",
        "PB14",
        "PB15",
        "PA0",
        "PA1",
        "PA4",
        "PB0",
        "PB1",
        "PA8",
        "PA11",
        "PA12",
        "PB8",
        "PB9",
        "PA15",
        "PB3",
        "PB4",
        "PB5",
        "PA6",
        "PA7",
        "PA5",
        "PA2",
        "PA3",
        "PB10",
        "PB11",
        "PB6",
        "PB7",
        "PA9",
        "PA10",
    ),
    adc_pins=("PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1"),
    interfaces={
        "i2c": (
            InterfaceOption(
                option_id="I2C1_DEFAULT",
                kind="i2c",
                instance="I2C1",
                signals={"scl": "PB6", "sda": "PB7"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="I2C1_REMAP",
                kind="i2c",
                instance="I2C1",
                signals={"scl": "PB8", "sda": "PB9"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 remap mapping",),
            ),
            InterfaceOption(
                option_id="I2C2_DEFAULT",
                kind="i2c",
                instance="I2C2",
                signals={"scl": "PB10", "sda": "PB11"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
        ),
        "uart": (
            InterfaceOption(
                option_id="USART1_DEFAULT",
                kind="uart",
                instance="USART1",
                signals={"tx": "PA9", "rx": "PA10"},
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="USART1_REMAP",
                kind="uart",
                instance="USART1",
                signals={"tx": "PB6", "rx": "PB7"},
                notes=("STM32F103x8/xB datasheet, Table 5 remap mapping",),
            ),
            InterfaceOption(
                option_id="USART2_DEFAULT",
                kind="uart",
                instance="USART2",
                signals={"tx": "PA2", "rx": "PA3"},
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="USART3_DEFAULT",
                kind="uart",
                instance="USART3",
                signals={"tx": "PB10", "rx": "PB11"},
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
        ),
        "spi": (
            InterfaceOption(
                option_id="SPI1_DEFAULT",
                kind="spi",
                instance="SPI1",
                signals={"nss": "PA4", "sck": "PA5", "miso": "PA6", "mosi": "PA7"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="SPI2_DEFAULT",
                kind="spi",
                instance="SPI2",
                signals={"nss": "PB12", "sck": "PB13", "miso": "PB14", "mosi": "PB15"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
        ),
        "can": (
            InterfaceOption(
                option_id="CAN1_DEFAULT",
                kind="can",
                instance="CAN1",
                signals={"rx": "PA11", "tx": "PA12"},
                notes=("STM32CubeMX MCU XML STM32F103C(8-B)Tx.xml: CAN_RX/CAN_TX on PA11/PA12.",),
            ),
            InterfaceOption(
                option_id="CAN1_REMAP",
                kind="can",
                instance="CAN1",
                signals={"rx": "PB8", "tx": "PB9"},
                notes=("STM32CubeMX MCU XML STM32F103C(8-B)Tx.xml: CAN_RX/CAN_TX remap on PB8/PB9.",),
            ),
        ),
        "usb": (
            InterfaceOption(
                option_id="USB_FS_DEFAULT",
                kind="usb",
                instance="USB_FS",
                signals={"dm": "PA11", "dp": "PA12"},
                notes=("STM32CubeMX MCU XML STM32F103C(8-B)Tx.xml: USB_DM/USB_DP on PA11/PA12.",),
            ),
        ),
        "pwm": (
            InterfaceOption("TIM2_CH1_PA0", "pwm", "TIM2_CH1", {"out": "PA0"}),
            InterfaceOption("TIM2_CH2_PA1", "pwm", "TIM2_CH2", {"out": "PA1"}),
            InterfaceOption("TIM2_CH3_PA2", "pwm", "TIM2_CH3", {"out": "PA2"}),
            InterfaceOption("TIM2_CH4_PA3", "pwm", "TIM2_CH4", {"out": "PA3"}),
            InterfaceOption("TIM3_CH1_PA6", "pwm", "TIM3_CH1", {"out": "PA6"}),
            InterfaceOption("TIM3_CH2_PA7", "pwm", "TIM3_CH2", {"out": "PA7"}),
            InterfaceOption("TIM3_CH3_PB0", "pwm", "TIM3_CH3", {"out": "PB0"}),
            InterfaceOption("TIM3_CH4_PB1", "pwm", "TIM3_CH4", {"out": "PB1"}),
            InterfaceOption("TIM1_CH1_PA8", "pwm", "TIM1_CH1", {"out": "PA8"}),
            InterfaceOption("TIM1_CH2_PA9", "pwm", "TIM1_CH2", {"out": "PA9"}),
            InterfaceOption("TIM1_CH3_PA10", "pwm", "TIM1_CH3", {"out": "PA10"}),
            InterfaceOption("TIM1_CH4_PA11", "pwm", "TIM1_CH4", {"out": "PA11"}),
        ),
    },
    sources=(
        "ST STM32F103x8/xB datasheet DS5319 Rev 20",
        "Keil uVision command line documentation",
    ),
    definition_path="builtin:chip:STM32F103C8T6",
)


STM32F103RBT6 = ChipDefinition(
    name="STM32F103RBT6",
    device_name="STM32F103RB",
    vendor="STMicroelectronics",
    family="STM32F1",
    cpu_type="Cortex-M3",
    package="LQFP64",
    flash_kb=128,
    ram_kb=20,
    irom_start=0x08000000,
    iram_start=0x20000000,
    c_define="STM32F103xB",
    reserved_pins=("PA13", "PA14"),
    gpio_preference=(
        "PA5",
        "PC13",
        "PB12",
        "PB13",
        "PB14",
        "PB15",
        "PA0",
        "PA1",
        "PA4",
        "PB0",
        "PB1",
        "PA8",
        "PA11",
        "PA12",
        "PB8",
        "PB9",
        "PA15",
        "PB3",
        "PB4",
        "PB5",
        "PA6",
        "PA7",
        "PA2",
        "PA3",
        "PB10",
        "PB11",
        "PB6",
        "PB7",
        "PA9",
        "PA10",
        "PC10",
        "PC11",
        "PC12",
        "PC0",
        "PC1",
        "PC2",
        "PC3",
        "PC4",
        "PC5",
    ),
    adc_pins=("PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1", "PC0", "PC1", "PC2", "PC3", "PC4", "PC5"),
    interfaces={
        "i2c": (
            InterfaceOption(
                option_id="I2C1_DEFAULT",
                kind="i2c",
                instance="I2C1",
                signals={"scl": "PB6", "sda": "PB7"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="I2C1_REMAP",
                kind="i2c",
                instance="I2C1",
                signals={"scl": "PB8", "sda": "PB9"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 remap mapping",),
            ),
            InterfaceOption(
                option_id="I2C2_DEFAULT",
                kind="i2c",
                instance="I2C2",
                signals={"scl": "PB10", "sda": "PB11"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
        ),
        "uart": (
            InterfaceOption(
                option_id="USART1_DEFAULT",
                kind="uart",
                instance="USART1",
                signals={"tx": "PA9", "rx": "PA10"},
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="USART1_REMAP",
                kind="uart",
                instance="USART1",
                signals={"tx": "PB6", "rx": "PB7"},
                notes=("STM32F103x8/xB datasheet, Table 5 remap mapping",),
            ),
            InterfaceOption(
                option_id="USART2_DEFAULT",
                kind="uart",
                instance="USART2",
                signals={"tx": "PA2", "rx": "PA3"},
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="USART3_DEFAULT",
                kind="uart",
                instance="USART3",
                signals={"tx": "PB10", "rx": "PB11"},
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="USART3_REMAP",
                kind="uart",
                instance="USART3",
                signals={"tx": "PC10", "rx": "PC11"},
                notes=("STM32F103x8/xB datasheet, Table 5 full remap mapping",),
            ),
        ),
        "spi": (
            InterfaceOption(
                option_id="SPI1_DEFAULT",
                kind="spi",
                instance="SPI1",
                signals={"nss": "PA4", "sck": "PA5", "miso": "PA6", "mosi": "PA7"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
            InterfaceOption(
                option_id="SPI1_REMAP",
                kind="spi",
                instance="SPI1",
                signals={"nss": "PA15", "sck": "PB3", "miso": "PB4", "mosi": "PB5"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 remap mapping",),
            ),
            InterfaceOption(
                option_id="SPI2_DEFAULT",
                kind="spi",
                instance="SPI2",
                signals={"nss": "PB12", "sck": "PB13", "miso": "PB14", "mosi": "PB15"},
                shareable=True,
                notes=("STM32F103x8/xB datasheet, Table 5 default mapping",),
            ),
        ),
        "can": (
            InterfaceOption(
                option_id="CAN1_DEFAULT",
                kind="can",
                instance="CAN1",
                signals={"rx": "PA11", "tx": "PA12"},
                notes=("STM32CubeMX MCU XML STM32F103R(8-B)Tx.xml: CAN_RX/CAN_TX on PA11/PA12.",),
            ),
            InterfaceOption(
                option_id="CAN1_REMAP",
                kind="can",
                instance="CAN1",
                signals={"rx": "PB8", "tx": "PB9"},
                notes=("STM32CubeMX MCU XML STM32F103R(8-B)Tx.xml: CAN_RX/CAN_TX remap on PB8/PB9.",),
            ),
        ),
        "usb": (
            InterfaceOption(
                option_id="USB_FS_DEFAULT",
                kind="usb",
                instance="USB_FS",
                signals={"dm": "PA11", "dp": "PA12"},
                notes=("STM32CubeMX MCU XML STM32F103R(8-B)Tx.xml: USB_DM/USB_DP on PA11/PA12.",),
            ),
        ),
        "pwm": (
            InterfaceOption("TIM2_CH1_PA0", "pwm", "TIM2_CH1", {"out": "PA0"}),
            InterfaceOption("TIM2_CH2_PA1", "pwm", "TIM2_CH2", {"out": "PA1"}),
            InterfaceOption("TIM2_CH3_PA2", "pwm", "TIM2_CH3", {"out": "PA2"}),
            InterfaceOption("TIM2_CH4_PA3", "pwm", "TIM2_CH4", {"out": "PA3"}),
            InterfaceOption("TIM3_CH1_PA6", "pwm", "TIM3_CH1", {"out": "PA6"}),
            InterfaceOption("TIM3_CH2_PA7", "pwm", "TIM3_CH2", {"out": "PA7"}),
            InterfaceOption("TIM3_CH3_PB0", "pwm", "TIM3_CH3", {"out": "PB0"}),
            InterfaceOption("TIM3_CH4_PB1", "pwm", "TIM3_CH4", {"out": "PB1"}),
            InterfaceOption("TIM1_CH1_PA8", "pwm", "TIM1_CH1", {"out": "PA8"}),
            InterfaceOption("TIM1_CH2_PA9", "pwm", "TIM1_CH2", {"out": "PA9"}),
            InterfaceOption("TIM1_CH3_PA10", "pwm", "TIM1_CH3", {"out": "PA10"}),
            InterfaceOption("TIM1_CH4_PA11", "pwm", "TIM1_CH4", {"out": "PA11"}),
            InterfaceOption("TIM4_CH1_PB6", "pwm", "TIM4_CH1", {"out": "PB6"}),
            InterfaceOption("TIM4_CH2_PB7", "pwm", "TIM4_CH2", {"out": "PB7"}),
            InterfaceOption("TIM4_CH3_PB8", "pwm", "TIM4_CH3", {"out": "PB8"}),
            InterfaceOption("TIM4_CH4_PB9", "pwm", "TIM4_CH4", {"out": "PB9"}),
        ),
    },
    sources=(
        "ST STM32F103x8/xB datasheet DS5319 Rev 20",
        "ST RM0008 reference manual",
    ),
    definition_path="builtin:chip:STM32F103RBT6",
)


STM32G431RBT6 = ChipDefinition(
    name="STM32G431RBT6",
    device_name="STM32G431RBTx",
    vendor="STMicroelectronics",
    family="STM32G4",
    cpu_type="Cortex-M4",
    package="LQFP64",
    flash_kb=128,
    ram_kb=32,
    irom_start=0x08000000,
    iram_start=0x20000000,
    c_define="STM32G431xx",
    reserved_pins=("PA13", "PA14"),
    gpio_preference=(
        "PB12",
        "PB13",
        "PB14",
        "PB15",
        "PA0",
        "PA1",
        "PA4",
        "PA6",
        "PA7",
        "PB0",
        "PB1",
        "PB5",
        "PB10",
        "PB11",
        "PA2",
        "PA3",
        "PA5",
        "PA8",
        "PA11",
        "PA12",
        "PA9",
        "PA10",
        "PB8",
        "PB9",
        "PC13",
        "PC14",
        "PC15",
        "PC0",
        "PC1",
        "PC2",
        "PC3",
        "PC4",
        "PC5",
        "PC6",
        "PC7",
        "PC8",
        "PC9",
        "PC10",
        "PC11",
        "PC12",
    ),
    adc_pins=(
        "PA0",
        "PA1",
        "PA2",
        "PA3",
        "PA4",
        "PA5",
        "PA6",
        "PA7",
        "PB0",
        "PB1",
        "PC0",
        "PC1",
        "PC2",
        "PC3",
        "PC4",
        "PC5",
    ),
    interfaces={
        "i2c": (
            InterfaceOption(
                option_id="I2C1_PB8_PB9",
                kind="i2c",
                instance="I2C1",
                signals={"scl": "PB8", "sda": "PB9"},
                shareable=True,
                notes=("ST STM32G431 datasheet alternate-function mapping: I2C1 on PB8/PB9.",),
            ),
            InterfaceOption(
                option_id="I2C1_PB6_PB7",
                kind="i2c",
                instance="I2C1",
                signals={"scl": "PB6", "sda": "PB7"},
                shareable=True,
                notes=(
                    "ST STM32G431 alternate-function templates in STM32CubeMX list I2C1 on PB6/PB7.",
                    "Official CT117E-M4 bit-banged I2C reference also uses PB6/PB7 for board I2C resources.",
                ),
            ),
        ),
        "uart": (
            InterfaceOption(
                option_id="USART2_PA2_PA3",
                kind="uart",
                instance="USART2",
                signals={"tx": "PA2", "rx": "PA3"},
                notes=("ST STM32G431 datasheet alternate-function mapping: USART2 on PA2/PA3.",),
            ),
            InterfaceOption(
                option_id="USART1_PA9_PA10",
                kind="uart",
                instance="USART1",
                signals={"tx": "PA9", "rx": "PA10"},
                notes=("ST STM32G431 datasheet alternate-function mapping: USART1 on PA9/PA10.",),
            ),
            InterfaceOption(
                option_id="USART1_PB6_PB7",
                kind="uart",
                instance="USART1",
                signals={"tx": "PB6", "rx": "PB7"},
                notes=("ST STM32G431 datasheet alternate-function mapping: USART1 on PB6/PB7.",),
            ),
            InterfaceOption(
                option_id="USART3_PB10_PB11",
                kind="uart",
                instance="USART3",
                signals={"tx": "PB10", "rx": "PB11"},
                notes=("ST STM32G431 datasheet alternate-function mapping: USART3 on PB10/PB11.",),
            ),
        ),
        "spi": (
            InterfaceOption(
                option_id="SPI1_PA4_PA5_PA6_PA7",
                kind="spi",
                instance="SPI1",
                signals={"nss": "PA4", "sck": "PA5", "miso": "PA6", "mosi": "PA7"},
                shareable=True,
                notes=("ST STM32G431 datasheet alternate-function mapping: SPI1 on PA4/PA5/PA6/PA7.",),
            ),
        ),
        "dac": (
            InterfaceOption(
                option_id="DAC1_CH1_PA4",
                kind="dac",
                instance="DAC1_CH1",
                signals={"out": "PA4"},
                notes=("STM32CubeMX MCU XML STM32G431R(6-8-B)Tx.xml: DAC1_OUT1 on PA4.",),
            ),
            InterfaceOption(
                option_id="DAC1_CH2_PA5",
                kind="dac",
                instance="DAC1_CH2",
                signals={"out": "PA5"},
                notes=("STM32CubeMX MCU XML STM32G431R(6-8-B)Tx.xml: DAC1_OUT2 on PA5.",),
            ),
        ),
        "can": (
            InterfaceOption(
                option_id="FDCAN1_DEFAULT",
                kind="can",
                instance="FDCAN1",
                signals={"rx": "PA11", "tx": "PA12"},
                notes=("STM32CubeMX MCU XML STM32G431R(6-8-B)Tx.xml: FDCAN1_RX/FDCAN1_TX on PA11/PA12.",),
            ),
            InterfaceOption(
                option_id="FDCAN1_PB8_PB9",
                kind="can",
                instance="FDCAN1",
                signals={"rx": "PB8", "tx": "PB9"},
                notes=("STM32CubeMX MCU XML STM32G431R(6-8-B)Tx.xml: FDCAN1_RX/FDCAN1_TX on PB8/PB9.",),
            ),
        ),
        "usb": (
            InterfaceOption(
                option_id="USB_FS_DEFAULT",
                kind="usb",
                instance="USB_FS",
                signals={"dm": "PA11", "dp": "PA12"},
                notes=("STM32CubeMX MCU XML STM32G431R(6-8-B)Tx.xml: USB_DM/USB_DP on PA11/PA12.",),
            ),
        ),
        "pwm": (
            InterfaceOption("TIM2_CH1_PA0", "pwm", "TIM2_CH1", {"out": "PA0"}),
            InterfaceOption("TIM2_CH2_PA1", "pwm", "TIM2_CH2", {"out": "PA1"}),
            InterfaceOption("TIM2_CH3_PA2", "pwm", "TIM2_CH3", {"out": "PA2"}),
            InterfaceOption("TIM2_CH4_PA3", "pwm", "TIM2_CH4", {"out": "PA3"}),
            InterfaceOption("TIM3_CH1_PA6", "pwm", "TIM3_CH1", {"out": "PA6"}),
            InterfaceOption("TIM3_CH2_PA7", "pwm", "TIM3_CH2", {"out": "PA7"}),
        ),
    },
    sources=(
        "ST STM32G431RB datasheet",
        "Local CT117E-M4 HAL sample project (HAL_06_LCD.ioc / MDK5_LCD_HAL)",
    ),
    definition_path="builtin:chip:STM32G431RBT6",
)


# Runtime chip loading is pack-first via packs/chips/*.json.
# The legacy chip constants above are kept only as local reference data.
CHIPS: Dict[str, ChipDefinition] = {}


BOARDS: Dict[str, BoardProfile] = {}


MODULES: Dict[str, ModuleSpec] = {
    "led": ModuleSpec(
        key="led",
        display_name="LED",
        summary="Single status LED driven by one GPIO output.",
        hal_components=("GPIO",),
        template_files=("app/led.c", "app/led.h"),
        resource_requests=("gpio_out",),
        c_init_template=("    LED_InitPin([[control_port_macro]], [[control_pin_macro]]);",),
        notes=("Default planner prefers low-risk GPIO pins.",),
        definition_path="builtin:module:led",
        simulation={
            "renode": {
                "attach": [
                    {
                        "kind": "led",
                        "signal": "control",
                        "name": "status_led",
                    }
                ]
            }
        },
        app_logic_snippets={
            "blink": {
                "description": "Toggle LED periodically",
                "init": ["LED_InitPin([[control_port_macro]], [[control_pin_macro]]);"],
                "periodic_task": {"every_ms": 500, "run": ["LED_Toggle([[control_port_macro]], [[control_pin_macro]]);"]},
                "key_apis": ["LED_InitPin", "LED_Write", "LED_Toggle"],
            }
        },
    ),
    "button": ModuleSpec(
        key="button",
        display_name="Button",
        summary="Single push button using one GPIO input.",
        hal_components=("GPIO",),
        template_files=("app/button.c", "app/button.h"),
        resource_requests=("gpio_in",),
        c_init_template=("    Button_InitPin([[input_port_macro]], [[input_pin_macro]]);",),
        definition_path="builtin:module:button",
        simulation={
            "renode": {
                "attach": [
                    {
                        "kind": "button",
                        "signal": "input",
                        "name": "user_button",
                        "actions": [
                            {
                                "at": 1.0,
                                "action": "press_and_release",
                            }
                        ],
                    }
                ]
            }
        },
        app_logic_snippets={
            "poll_and_debounce": {
                "description": "Poll button state with simple debounce",
                "periodic_task": {"every_ms": 50, "run": [
                    "if (Button_Read([[input_port_macro]], [[input_pin_macro]]) == GPIO_PIN_RESET) {",
                    "    HAL_Delay(20);  /* debounce */",
                    "    if (Button_Read([[input_port_macro]], [[input_pin_macro]]) == GPIO_PIN_RESET) {",
                    "        /* button pressed action */",
                    "    }",
                    "}",
                ]},
                "key_apis": ["Button_InitPin", "Button_Read"],
            }
        },
    ),
    "active_buzzer": ModuleSpec(
        key="active_buzzer",
        display_name="Active Buzzer",
        summary="Active buzzer driven by one GPIO output.",
        hal_components=("GPIO",),
        template_files=("app/active_buzzer.c", "app/active_buzzer.h"),
        resource_requests=("gpio_out",),
        c_init_template=("    ActiveBuzzer_InitPin([[control_port_macro]], [[control_pin_macro]]);",),
        definition_path="builtin:module:active_buzzer",
    ),
    "passive_buzzer": ModuleSpec(
        key="passive_buzzer",
        display_name="Passive Buzzer",
        summary="Passive buzzer driven by one PWM output.",
        hal_components=("GPIO", "TIM"),
        template_files=("app/passive_buzzer.c", "app/passive_buzzer.h"),
        resource_requests=("pwm_out",),
        c_init_template=("    PassiveBuzzer_Init(&[[pwm_handle]], [[pwm_channel]]);",),
        definition_path="builtin:module:passive_buzzer",
    ),
    "uart_debug": ModuleSpec(
        key="uart_debug",
        display_name="UART Debug",
        summary="Debug UART using one USART TX/RX pair.",
        hal_components=("GPIO", "USART", "DMA"),
        template_files=("app/debug_uart.c", "app/debug_uart.h"),
        resource_requests=("uart_port",),
        dma_requests=("uart_rx", "uart_tx"),
        c_init_template=("    DebugUart_Init(&[[uart_handle]]);",),
        definition_path="builtin:module:uart_debug",
        app_logic_snippets={
            "log_message": {
                "description": "Send formatted debug log via UART",
                "init": ["DebugUart_Init(&[[uart_handle]]);", "DebugUart_WriteLine(&[[uart_handle]], \"System boot OK\", 100);"],
                "periodic_task": {"every_ms": 1000, "run": [
                    "char buf[64];",
                    "snprintf(buf, sizeof(buf), \"tick=%lu\", (unsigned long)HAL_GetTick());",
                    "DebugUart_WriteLine(&[[uart_handle]], buf, 100);",
                ]},
                "key_apis": ["DebugUart_Init", "DebugUart_Write", "DebugUart_WriteLine"],
            }
        },
    ),
    "ssd1306_i2c": ModuleSpec(
        key="ssd1306_i2c",
        display_name="SSD1306 I2C OLED",
        summary="SSD1306 OLED over I2C, usually address 0x3C or 0x3D.",
        hal_components=("GPIO", "I2C", "DMA"),
        template_files=("modules/ssd1306.c", "modules/ssd1306.h"),
        resource_requests=("i2c_device", "gpio_out:reset:optional"),
        address_options=(0x3C, 0x3D),
        bus_kind="i2c",
        optional_signals=("reset",),
        c_init_template=(
            "    if (SSD1306_InitDefault(&[[i2c_handle]], [[i2c_address_macro]], 100) == HAL_OK) {",
            "        (void)SSD1306_Clear(&[[i2c_handle]], [[i2c_address_macro]], 100);",
            "    }",
        ),
        notes=(
            "I2C requires external pull-up resistors.",
            "Many breakout boards already hard-wire RESET, so the reset pin can be omitted.",
        ),
        sources=("Solomon Systech SSD1306 Rev 1.1",),
        definition_path="builtin:module:ssd1306_i2c",
        app_logic_snippets={
            "display_text": {
                "description": "Display text string on OLED at specified position",
                "init": [
                    "SSD1306_InitDefault(&[[i2c_handle]], [[i2c_address_macro]], 100);",
                    "SSD1306_Clear(&[[i2c_handle]], [[i2c_address_macro]], 100);",
                ],
                "periodic_task": {"every_ms": 1000, "run": [
                    "SSD1306_WriteString5x7(&[[i2c_handle]], [[i2c_address_macro]], 0, 0, \"Hello OLED\", 100);",
                ]},
                "key_apis": ["SSD1306_InitDefault", "SSD1306_Clear", "SSD1306_SetCursor", "SSD1306_WriteString5x7", "SSD1306_WriteChar5x7"],
            }
        },
    ),
    "mpu6050_i2c": ModuleSpec(
        key="mpu6050_i2c",
        display_name="MPU6050",
        summary="MPU6050 6-axis sensor over I2C, usually address 0x68 or 0x69.",
        hal_components=("GPIO", "I2C", "DMA"),
        template_files=("modules/mpu6050.c", "modules/mpu6050.h"),
        resource_requests=("i2c_device", "gpio_in:int:optional"),
        address_options=(0x68, 0x69),
        bus_kind="i2c",
        optional_signals=("int",),
        c_init_template=("    (void)MPU6050_Wake(&[[i2c_handle]], [[i2c_address_macro]], 100);",),
        notes=(
            "The interrupt pin is optional for polling mode.",
            "I2C commonly runs at 400 kHz for this device.",
        ),
        sources=("TDK InvenSense MPU-6000/MPU-6050 Product Specification Rev 3.4",),
        definition_path="builtin:module:mpu6050_i2c",
        app_logic_snippets={
            "read_accel": {
                "description": "Read raw accelerometer XYZ and log via UART",
                "init": ["MPU6050_Wake(&[[i2c_handle]], [[i2c_address_macro]], 100);"],
                "periodic_task": {"every_ms": 500, "run": [
                    "int16_t ax = 0, ay = 0, az = 0;",
                    "if (MPU6050_ReadAccelRaw(&[[i2c_handle]], [[i2c_address_macro]], &ax, &ay, &az, 100) == HAL_OK) {",
                    "    char buf[48];",
                    "    snprintf(buf, sizeof(buf), \"AX:%d AY:%d AZ:%d\", ax, ay, az);",
                    "    DebugUart_WriteLine(&[[uart_handle]], buf, 100);",
                    "}",
                ]},
                "key_apis": ["MPU6050_Wake", "MPU6050_ReadAccelRaw", "MPU6050_ReadWhoAmI"],
            }
        },
    ),
    "at24c02_i2c": ModuleSpec(
        key="at24c02_i2c",
        display_name="AT24C02",
        summary="2 Kbit I2C EEPROM with base address 1010 A2 A1 A0.",
        hal_components=("GPIO", "I2C", "DMA"),
        template_files=("modules/at24c02.c", "modules/at24c02.h"),
        resource_requests=("i2c_device",),
        address_options=(0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57),
        bus_kind="i2c",
        c_init_template=(
            "    /* AT24C02 transport ready: AT24C02_ReadByte(&[[i2c_handle]], [[i2c_address_macro]], mem_addr, &value, 100); */",
        ),
        notes=("Supports standard and fast mode up to 400 kHz.",),
        sources=("Microchip AT24HC02C Datasheet 20006123A",),
        definition_path="builtin:module:at24c02_i2c",
        simulation={
            "renode": {
                "attach": [
                    {
                        "kind": "i2c_mock",
                        "interface": "i2c",
                        "model": "at24c02",
                        "name": "eeprom_mock",
                    }
                ]
            }
        },
    ),
    "bh1750_i2c": ModuleSpec(
        key="bh1750_i2c",
        display_name="BH1750",
        summary="Ambient light sensor over I2C, usually address 0x23 or 0x5C.",
        hal_components=("GPIO", "I2C", "DMA"),
        template_files=("modules/bh1750.c", "modules/bh1750.h"),
        resource_requests=("i2c_device",),
        address_options=(0x23, 0x5C),
        bus_kind="i2c",
        c_init_template=(
            "    (void)BH1750_PowerOn(&[[i2c_handle]], [[i2c_address_macro]], 100);",
            "    (void)BH1750_StartContinuousHighRes(&[[i2c_handle]], [[i2c_address_macro]], 100);",
        ),
        notes=("ADDR pin selects the 7-bit I2C address between 0x23 and 0x5C.",),
        sources=("ROHM BH1750FVI datasheet",),
        definition_path="builtin:module:bh1750_i2c",
        app_logic_snippets={
            "read_lux": {
                "description": "Read ambient light in lux and log via UART",
                "init": [
                    "BH1750_PowerOn(&[[i2c_handle]], [[i2c_address_macro]], 100);",
                    "BH1750_StartContinuousHighRes(&[[i2c_handle]], [[i2c_address_macro]], 100);",
                ],
                "periodic_task": {"every_ms": 2000, "run": [
                    "float lux = 0.0f;",
                    "if (BH1750_ReadLux(&[[i2c_handle]], [[i2c_address_macro]], &lux, 200) == HAL_OK) {",
                    "    char buf[32];",
                    "    snprintf(buf, sizeof(buf), \"Light: %.1f lux\", lux);",
                    "    DebugUart_WriteLine(&[[uart_handle]], buf, 100);",
                    "}",
                ]},
                "key_apis": ["BH1750_PowerOn", "BH1750_StartContinuousHighRes", "BH1750_ReadLux", "BH1750_ReadRaw"],
            }
        },
    ),
    "ds18b20_1wire": ModuleSpec(
        key="ds18b20_1wire",
        display_name="DS18B20",
        summary="1-Wire temperature sensor using one GPIO data pin.",
        hal_components=("GPIO",),
        template_files=("modules/ds18b20.c", "modules/ds18b20.h"),
        resource_requests=("onewire_gpio",),
        c_init_template=(
            "    DS18B20_ReleaseBus([[dq_port_macro]], [[dq_pin_macro]]);",
            "    /* TODO: add us-level delay callbacks before implementing 1-Wire timing slots. */",
        ),
        notes=(
            "The DQ line needs an external pull-up resistor, often 4.7k.",
            "Current planner only targets a single device on the 1-Wire bus.",
        ),
        sources=("Analog Devices DS18B20 datasheet",),
        definition_path="builtin:module:ds18b20_1wire",
    ),
}
