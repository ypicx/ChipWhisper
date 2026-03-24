# Extension Packs

This directory lets users add chips and modules without editing Python source files.

Layout:
- `chips/*.json`
- `boards/*.json`
- `modules/<module_key>/module.json`
- `modules/<module_key>/templates/...`
- `modules/<module_key>/plugin.py`

Template rules:
- `template_files` describes the files that the generated Keil project should contain.
- If a matching file exists under `templates/`, the generator copies that file into the project.
- If no template file exists, the generator falls back to a built-in placeholder renderer.
- `c_top_template` can inject generic `AppTop` declarations such as static state objects.
- `c_init_template` can inject generic `App_Init()` lines using `[[token]]` placeholders such as `[[control_port_macro]]`, `[[control_pin_macro]]`, `[[i2c_handle]]`, `[[i2c_address_macro]]`, `[[pwm_handle]]`, and `[[pwm_channel]]`.
- `c_loop_template` can inject generic `App_Loop()` lines for reusable polling/state-machine snippets.
- `c_callbacks_template` can inject reusable weak-callback implementations or middleware glue into `AppCallbacks`.
- Template tokens can provide defaults with `[[token|fallback]]`, which is useful for middleware options such as debounce timing.
- Scalar options also expose `[[option_name_brackets|[32]]]` style tokens for array declarations and similar C syntax.
- Dependency-aware tokens can reference the first matching dependent module, for example `[[dep_uart_frame_uart_handle]]` or `[[dep_soft_timer_module_identifier]]`.
- `simulation` can describe optional Renode-only attachments such as buttons, LEDs, and I2C mocks without changing generated firmware code.
- `depends_on` can require another module kind or module name to be present before planning succeeds.
- `init_priority` and `loop_priority` provide deterministic middleware injection order without hard-coding request order.
- `plugin.py` can expose optional `on_plan(context)` / `on_generate(context)` hooks to inject extra metadata or generated files.
- If you already have verified vendor `.h` / `.c` files, use `python -m stm32_agent import-module-files <module_key> <file1> [file2 ...]`.

Supported resource request strings:
- `gpio_out`
- `gpio_in`
- `pwm_out`
- `timer_ic`
- `timer_oc`
- `adc_in`
- `dac_out`
- `uart_port`
- `i2c_device`
- `spi_bus`
- `spi_device`
- `encoder`
- `advanced_timer`
- `can_port`
- `usb_device`
- `onewire_gpio`
- Named form: `gpio_out:reset`
- Optional named form: `gpio_in:int:optional`

Middleware pattern:
- Pure software packs can leave `resource_requests` empty and inject shared runtime code through `c_init_template` and `c_loop_template`.
- Hardware-aware middleware packs can still model pins normally and use `depends_on` to require shared software primitives such as `soft_timer`.
- Storage-oriented middleware packs can stay backend-neutral and delegate EEPROM or Flash access to weak callbacks, which keeps them reusable across boards.

Renode simulation pattern:
- Use `simulation.renode.attach` to describe virtual peripherals or scripted interactions for validation.
- Supported first-step `kind` values are `led`, `button`, and `i2c_mock`.
- When `renode_expect.json` is missing, direct Renode runs now auto-derive first-pass expectations from `build.app_logic` debug UART lines and LED probe `expect` markers.
- `button` entries can schedule timed actions such as `press`, `release`, or `press_and_release`.
- `i2c_mock` currently supports lightweight models such as `echo` and `dummy`, which are useful for transport-level smoke tests.

Board profile hints:
- Use `boards/*.json` to describe real development boards.
- `preferred_signals` can target either a concrete module kind like `led.control` or a generic resource kind like `can_port.tx`, `spi_device.sck`, or `usb_device.dp`.
- Good `preferred_signals` examples are `led.control`, `button.input`, `uart_debug.tx`, `can_port.rx`, and `spi_device.mosi`.

Future LLM workflow:
- Upload user manual, datasheet, and sample code.
- Ask the agent to draft a pack under `packs/modules/<name>/`.
- Review the generated `module.json` and templates before using it for project generation.

Recommended vendor-code workflow:
- Model the hardware resources in `module.json`.
- Import the official `.h` / `.c` files into the pack.
- Generate the project and keep the protocol logic in vendor code whenever practical.
