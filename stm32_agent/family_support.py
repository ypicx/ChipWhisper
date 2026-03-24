from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class FamilySupport:
    family: str
    hal_prefix: str
    cmsis_device_dir: str
    hal_driver_dir: str
    system_source: str
    startup_source: str
    it_header: str
    it_source: str
    hal_conf_header: str
    hal_msp_source: str
    main_hal_header: str
    main_extra_includes: tuple[str, ...]
    cube_package_glob: str
    cube_package_label: str
    cube_package_config_key: str
    device_pack_dir: str
    cpu_clock_hz: int
    sim_dll: str
    sim_arg: str
    hal_can_module_macro: str
    hal_can_header: str
    hal_pwr_extra_headers: tuple[str, ...]
    default_hse_value: int
    default_hsi_value: int
    default_lsi_value: int
    can_handle_type: str
    usb_irq_map: dict[str, str]
    global_msp_init_lines: tuple[str, ...]
    dma_setup_clock_lines: tuple[str, ...]
    dma_uses_request_field: bool
    implicit_hal_components: tuple[str, ...]
    hal_source_map: dict[str, tuple[str, ...]]

    def build_can_handle_name(self, instance: str) -> str:
        normalized = str(instance or "").strip().lower()
        suffix = normalized.replace("fdcan", "").replace("can", "") or "1"
        if self.can_handle_type == "FDCAN_HandleTypeDef":
            return f"hfdcan{suffix}"
        return f"hcan{suffix}"

    def resolve_usb_irq(self, instance: str) -> str:
        normalized = str(instance or "").strip().upper()
        return self.usb_irq_map.get(normalized, "")


F1_SUPPORT = FamilySupport(
    family="STM32F1",
    hal_prefix="stm32f1xx",
    cmsis_device_dir="STM32F1xx",
    hal_driver_dir="STM32F1xx_HAL_Driver",
    system_source="system_stm32f1xx.c",
    startup_source="startup_stm32f103xb.s",
    it_header="stm32f1xx_it.h",
    it_source="stm32f1xx_it.c",
    hal_conf_header="stm32f1xx_hal_conf.h",
    hal_msp_source="stm32f1xx_hal_msp.c",
    main_hal_header="stm32f1xx_hal.h",
    main_extra_includes=(),
    cube_package_glob="STM32Cube_FW_F1_V*",
    cube_package_label="STM32CubeF1",
    cube_package_config_key="stm32cube_f1_package_path",
    device_pack_dir="STM32F1xx_DFP",
    cpu_clock_hz=8_000_000,
    sim_dll="SARMCM3.DLL",
    sim_arg="-pCM3",
    hal_can_module_macro="HAL_CAN_MODULE_ENABLED",
    hal_can_header="stm32f1xx_hal_can.h",
    hal_pwr_extra_headers=(),
    default_hse_value=8_000_000,
    default_hsi_value=8_000_000,
    default_lsi_value=40_000,
    can_handle_type="CAN_HandleTypeDef",
    usb_irq_map={
        "USB": "USB_LP_CAN1_RX0_IRQn",
        "USB_FS": "USB_LP_CAN1_RX0_IRQn",
        "USB_OTG_FS": "USB_LP_CAN1_RX0_IRQn",
    },
    global_msp_init_lines=(
        "__HAL_RCC_AFIO_CLK_ENABLE();",
        "__HAL_RCC_PWR_CLK_ENABLE();",
    ),
    dma_setup_clock_lines=(),
    dma_uses_request_field=False,
    implicit_hal_components=(),
    hal_source_map={
        "RCC": (
            "stm32f1xx_hal.c",
            "stm32f1xx_hal_rcc.c",
            "stm32f1xx_hal_rcc_ex.c",
            "stm32f1xx_hal_cortex.c",
        ),
        "FLASH": (
            "stm32f1xx_hal_flash.c",
            "stm32f1xx_hal_flash_ex.c",
        ),
        "GPIO": (
            "stm32f1xx_hal_gpio.c",
            "stm32f1xx_hal_gpio_ex.c",
        ),
        "DMA": ("stm32f1xx_hal_dma.c",),
        "ADC": (
            "stm32f1xx_hal_adc.c",
            "stm32f1xx_hal_adc_ex.c",
        ),
        "I2C": ("stm32f1xx_hal_i2c.c",),
        "SPI": ("stm32f1xx_hal_spi.c",),
        "USART": ("stm32f1xx_hal_uart.c",),
        "DAC": (
            "stm32f1xx_hal_dac.c",
            "stm32f1xx_hal_dac_ex.c",
        ),
        "CAN": ("stm32f1xx_hal_can.c",),
        "PCD": ("stm32f1xx_hal_pcd.c",),
        "TIM": (
            "stm32f1xx_hal_tim.c",
            "stm32f1xx_hal_tim_ex.c",
        ),
    },
)


G4_SUPPORT = FamilySupport(
    family="STM32G4",
    hal_prefix="stm32g4xx",
    cmsis_device_dir="STM32G4xx",
    hal_driver_dir="STM32G4xx_HAL_Driver",
    system_source="system_stm32g4xx.c",
    startup_source="startup_stm32g431xx.s",
    it_header="stm32g4xx_it.h",
    it_source="stm32g4xx_it.c",
    hal_conf_header="stm32g4xx_hal_conf.h",
    hal_msp_source="stm32g4xx_hal_msp.c",
    main_hal_header="stm32g4xx_hal.h",
    main_extra_includes=("stm32g4xx_ll_pwr.h",),
    cube_package_glob="STM32Cube_FW_G4_V*",
    cube_package_label="STM32CubeG4",
    cube_package_config_key="stm32cube_g4_package_path",
    device_pack_dir="STM32G4xx_DFP",
    cpu_clock_hz=80_000_000,
    sim_dll="SARMCM4.DLL",
    sim_arg="-pCM4",
    hal_can_module_macro="HAL_FDCAN_MODULE_ENABLED",
    hal_can_header="stm32g4xx_hal_fdcan.h",
    hal_pwr_extra_headers=("stm32g4xx_hal_pwr_ex.h",),
    default_hse_value=24_000_000,
    default_hsi_value=16_000_000,
    default_lsi_value=32_000,
    can_handle_type="FDCAN_HandleTypeDef",
    usb_irq_map={
        "USB": "USB_FS_IRQn",
        "USB_FS": "USB_FS_IRQn",
        "USB_OTG_FS": "OTG_FS_IRQn",
    },
    global_msp_init_lines=(
        "__HAL_RCC_SYSCFG_CLK_ENABLE();",
        "__HAL_RCC_PWR_CLK_ENABLE();",
        "LL_PWR_DisableDeadBatteryPD();",
    ),
    dma_setup_clock_lines=("__HAL_RCC_DMAMUX1_CLK_ENABLE();",),
    dma_uses_request_field=True,
    implicit_hal_components=("PWR", "EXTI"),
    hal_source_map={
        "RCC": (
            "stm32g4xx_hal.c",
            "stm32g4xx_hal_rcc.c",
            "stm32g4xx_hal_rcc_ex.c",
            "stm32g4xx_hal_cortex.c",
        ),
        "FLASH": (
            "stm32g4xx_hal_flash.c",
            "stm32g4xx_hal_flash_ex.c",
        ),
        "GPIO": (
            "stm32g4xx_hal_gpio.c",
        ),
        "DMA": (
            "stm32g4xx_hal_dma.c",
            "stm32g4xx_hal_dma_ex.c",
        ),
        "ADC": (
            "stm32g4xx_hal_adc.c",
            "stm32g4xx_hal_adc_ex.c",
        ),
        "I2C": (
            "stm32g4xx_hal_i2c.c",
            "stm32g4xx_hal_i2c_ex.c",
        ),
        "SPI": ("stm32g4xx_hal_spi.c",),
        "USART": (
            "stm32g4xx_hal_uart.c",
            "stm32g4xx_hal_uart_ex.c",
        ),
        "DAC": (
            "stm32g4xx_hal_dac.c",
            "stm32g4xx_hal_dac_ex.c",
        ),
        "CAN": ("stm32g4xx_hal_fdcan.c",),
        "FDCAN": ("stm32g4xx_hal_fdcan.c",),
        "TIM": (
            "stm32g4xx_hal_tim.c",
            "stm32g4xx_hal_tim_ex.c",
        ),
        "PWR": (
            "stm32g4xx_hal_pwr.c",
            "stm32g4xx_hal_pwr_ex.c",
        ),
        "EXTI": ("stm32g4xx_hal_exti.c",),
    },
)


FAMILY_SUPPORTS = {
    F1_SUPPORT.family: F1_SUPPORT,
    G4_SUPPORT.family: G4_SUPPORT,
}


def get_family_support(family: str) -> FamilySupport:
    normalized = str(family or "").strip().upper()
    if not normalized or normalized == F1_SUPPORT.family:
        return F1_SUPPORT
    support = FAMILY_SUPPORTS.get(normalized)
    if support is None:
        raise ValueError(f"暂未适配该芯片族: {family}")
    return support


def collect_hal_sources(components: Iterable[str], family: str) -> list[str]:
    support = get_family_support(family)
    requested = {str(item) for item in components}
    requested.update(support.implicit_hal_components)
    if "TIM" in requested:
        requested.add("DMA")
    collected: list[str] = []
    for component in sorted(requested):
        for filename in support.hal_source_map.get(component, ()):
            if filename not in collected:
                collected.append(filename)
    return collected
