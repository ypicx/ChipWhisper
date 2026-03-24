# Chip Packs

Place external chip definitions here.

Supported layout:
- `packs/chips/<chip_name>.json`

These files are the runtime source of truth for chip-level capabilities:
- memory layout
- GPIO preference and reserved pins
- ADC-capable pins
- interface candidate mappings such as `I2C`, `UART`, `SPI`, `PWM`

Helpful commands:

```powershell
python -m stm32_agent new-chip-pack STM32F103C8T6
python -m stm32_agent import-cubemx-chip STM32G431RBTxZ STM32G431RBT6
```

Repo examples:

- `stm32f103c8t6.json`
- `stm32f103rbt6.json`
- `stm32g431rbt6.json`
