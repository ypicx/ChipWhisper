# Resource Solver And Pack Fields

This note documents the pack-level fields and planner behavior added during the EXTI, DMA, and clock-profile upgrade work.

## What Changed

- GPIO interrupt signals now consume real EXTI lines, so `PA0` and `PB0` conflict if both need interrupts.
- DMA is now modeled as a global resource instead of a loose HAL toggle.
- Shared I2C DMA can be declared once per bus instead of once per module instance.
- Board and chip packs can carry clock data, and the generator renders `SystemClock_Config()` from that data.
- Module packs can now also carry `simulation` metadata so Renode validation can inject buttons, LEDs, and lightweight bus mocks from the same pack catalog.
- Requests and generated app logic can now contribute `generated_files`, so business logic is no longer forced into a single `app_main.c` anchor set.
- Module packs can now expose optional `plugin.py` hooks to extend planning and generation without patching core code.

## `dma_requests`

Modules can declare DMA needs in `module.json`:

```json
{
  "dma_requests": [
    "uart_rx",
    "uart_tx",
    "i2c_rx:optional:shared_bus",
    "i2c_tx:optional:shared_bus"
  ]
}
```

Supported forms:

- symbolic names such as `uart_rx`, `uart_tx`, `i2c_rx`, `i2c_tx`
- exact chip request names such as `USART1_RX`

Supported flags:

- `:optional`
  Means the planner may skip DMA if no channel is available.
- `:shared_bus`
  Means the request should be grouped at the bus level. This is the recommended shape for shared I2C DMA.

## EXTI Modeling

Interrupt-style GPIO requests such as `gpio_in:int` and `gpio_in:interrupt` now allocate:

- the pin itself
- the EXTI line derived from the pin number
- the generated IRQ routing in the scaffolded project

The planner rejects requests that would alias onto the same EXTI line when both signals require dedicated interrupt ownership.

## Clock Profiles

`clock_profile` can appear in either chip packs or board packs.

Recommended split:

- chip pack: fallback family-level clock profile
- board pack: real oscillator and PLL settings for the actual board

Example:

```json
{
  "clock_profile": {
    "summary": "8 MHz HSE + PLL x9 -> 72 MHz SYSCLK",
    "cpu_clock_hz": 72000000,
    "hse_value": 8000000,
    "hsi_value": 8000000,
    "lsi_value": 40000,
    "lse_value": 32768,
    "external_clock_value": 48000,
    "system_clock_config": [
      "    RCC_OscInitTypeDef RCC_OscInitStruct = {0};",
      "    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};"
    ]
  }
}
```

Board profiles override chip-level fallback profiles during planning and scaffolding.

## Generated Runtime Skeleton

For allocated DMA and interrupt resources, scaffolding now emits:

- `HAL_I2C_MspInit` / `HAL_I2C_MspDeInit`
- `HAL_UART_MspInit` / `HAL_UART_MspDeInit`
- `HAL_TIM_PWM_MspInit` / `HAL_TIM_PWM_MspDeInit`
- DMA handle declarations, init, link, IRQ handlers, and deinit
- EXTI IRQ handlers and `HAL_GPIO_EXTI_IRQHandler(...)` calls

That gives the generated project a complete init/deinit lifecycle instead of a one-way setup path.

## `generated_files`

Requests and LLM-generated app logic can now emit extra source files directly:

```json
{
  "generated_files": {
    "app/sensor_task.h": "#pragma once\nvoid SensorTask_Run(void);\n",
    "app/sensor_task.c": "#include \"sensor_task.h\"\n\nvoid SensorTask_Run(void) {}\n"
  }
}
```

Supported target prefixes:

- `app/...`
  Writes into `App/Inc` or `App/Src`.
- `modules/...`
  Writes into `Modules/Inc` or `Modules/Src`.

Behavior:

- these files are normalized before planning, preview, and scaffold
- diff preview and proposal review include them like normal generated files
- plugins can also return `generated_files` from `on_plan()` and `on_generate()`

This is the first step toward multi-file business logic generation instead of forcing everything into `AppTop` / `AppInit` / `AppLoop` / `AppCallbacks`.

## `plugin.py` Hooks

Each module pack may optionally include `modules/<module_key>/plugin.py`.

Supported hook names:

- `on_plan(context)`
  Runs during planning and can extend the loaded module spec.
- `on_generate(context)`
  Runs during scaffold/preview and can emit extra generated files.

Typical `on_plan()` return payload:

```python
def on_plan(context: dict) -> dict:
    return {
        "warnings": ["custom planner hint"],
        "template_files": ["app/custom_logic.c", "app/custom_logic.h"],
        "generated_files": {
            "app/custom_logic.h": "void CustomLogic_Run(void);\n",
        },
        "c_init_template": ["    CustomLogic_Run();"],
    }
```

Typical `on_generate()` return payload:

```python
def on_generate(context: dict) -> dict:
    return {
        "generated_files": {
            "app/custom_logic.c": "#include \"custom_logic.h\"\n",
        }
    }
```

Hook rules:

- custom pack directories are now layered on top of the default `packs/` catalog instead of replacing it
- `plugin.py` errors fail the current module clearly instead of silently falling back
- returned file paths are normalized through the same generated-file pipeline used by requests and LLM output

## `simulation`

Modules can optionally describe Renode-only simulation behavior:

```json
{
  "simulation": {
    "renode": {
      "attach": [
        {
          "kind": "button",
          "signal": "input",
          "name": "user_button",
          "actions": [
            {"at": 1.0, "action": "press_and_release"}
          ]
        },
        {
          "kind": "led",
          "signal": "control",
          "name": "status_led"
        },
        {
          "kind": "i2c_mock",
          "interface": "i2c",
          "model": "echo",
          "name": "eeprom_mock"
        }
      ]
    }
  }
}
```

Current behavior:

- `button`
  Renode injects a virtual `Miscellaneous.Button` on the planned GPIO pin and can replay timed actions such as `press_and_release`.
- `led`
  Renode attaches a `Miscellaneous.LED` to the planned GPIO pin so runtime validation can observe it. LED probes with an `expect` field become `log_contains` expectations when `renode_expect.json` is missing.
- `i2c_mock`
  Renode attaches a lightweight I2C mock to the planned bus and device address. The runner supports generic transport-level `echo` / `dummy` models plus memory-backed `at24c02` and `at24c32` EEPROM-style mocks.

The planner now copies this metadata into `project_ir.json`, and the Renode runner translates it into `machine LoadPlatformDescriptionFromString ...` commands during runtime validation.
When `renode_expect.json` is absent, the runner also derives a first-pass expectation file from generated debug-UART lines in `build.app_logic` and from simulation metadata such as LED probe expectations.
