# CubeMX Chip Import

ChipWhisper now includes an offline importer that converts STM32CubeMX MCU XML files into `packs/chips/*.json` chip packs.

This is useful when you want to:

- add a new STM32 device without hand-writing every interface entry
- bootstrap a new family from the official CubeMX database
- keep chip definitions grounded in ST's own pin and signal tables

## Command

```powershell
python -m stm32_agent import-cubemx-chip <refname|xml_path> [chip_name] [packs_dir]
```

Examples:

```powershell
python -m stm32_agent import-cubemx-chip STM32G431RBTxZ STM32G431RBT6
python -m stm32_agent import-cubemx-chip D:\STM32CubeMX\db\mcu\STM32G431RBTxZ.xml STM32G431RBT6
python -m stm32_agent import-cubemx-chip STM32G431RBTxZ STM32G431RBT6 .\packs
```

## What the importer reads

From the STM32CubeMX XML, the importer extracts:

- `RefName`
- family and package
- core, flash and RAM
- GPIO pin list
- ADC-capable pins
- interface candidates for:
  - `I2C`
  - `UART / USART / LPUART`
  - `SPI`
  - `TIMx_CHy` PWM outputs

## Output

The importer writes a normal chip pack JSON file under:

```text
packs/chips/<chip_name>.json
```

The result is immediately compatible with:

- `python -m stm32_agent doctor-packs`
- `python -m stm32_agent plan ...`
- `python -m stm32_agent scaffold ...`

## Important limits

This importer is intentionally conservative.

- It infers bus mappings from the CubeMX pin signal list, so complex remap combinations may still need manual review.
- If CubeMX uses a generic `RefName` such as `STM32G431RBTxZ`, the importer can guess a concrete chip name like `STM32G431RBT6`, but you should pass the exact commercial name yourself when possible.
- `c_define` is inferred heuristically for now, especially outside the already-supported STM32 families.

## Recommended workflow

1. Import a chip from CubeMX.
2. Open the generated `packs/chips/*.json`.
3. Quickly review:
   - `name`
   - `device_name`
   - `c_define`
   - `reserved_pins`
   - `interfaces`
4. Run `doctor-packs`.
5. Use the new chip in a small project first.
