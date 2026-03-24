# Vendor Module Imports

## Purpose

Use this flow when a module already has vendor-provided `.h` / `.c` example files and you want the generated Keil project to include those files directly instead of relying on hand-written templates.

This is the recommended path for modules such as `AS608` fingerprint readers, where the packet protocol and serial command details are better handled by verified vendor code.

## Supported Now

- Import `.h`
- Import `.c`
- Copy those files into `packs/modules/<module_key>/templates/modules/`
- Automatically update `module.json -> template_files`
- Use the imported files when running `plan` and `scaffold`

## CLI Flow

1. Create or prepare the module pack.

```powershell
python -m stm32_agent new-module-pack as608_uart
```

2. Edit `packs/modules/as608_uart/module.json` to declare the real resources.

Recommended fields for `AS608`:

```json
{
  "hal_components": ["GPIO", "USART", "DMA"],
  "resource_requests": ["uart_port", "gpio_out:bl:optional", "gpio_out:rst:optional"],
  "dma_requests": ["uart_rx", "uart_tx"]
}
```

3. Import the official vendor files.

```powershell
python -m stm32_agent import-module-files as608_uart D:\vendor\AS608.h D:\vendor\AS608.c
```

4. Generate the project.

```powershell
python -m stm32_agent scaffold .\examples\as608_demo.json .\out\as608_project
```

## AS608 Modeling Notes

- Treat `AS608` as a UART module first.
- Core required resource: one `uart_port`
- Optional resources: `BL` and `RST` if your board exposes them
- Keep the serial protocol in vendor code whenever possible
- Only generate the board-side HAL resource allocation and project structure in the agent

## Real-World Limits

- Different `AS608` sellers may ship different default baud rates.
- Some vendor example code is STM32 Standard Peripheral Library based, not HAL based.
- If the imported code depends on extra support files, import those files too or add a small HAL adapter layer.
- This workflow guarantees file inclusion and resource planning. It does not guarantee that third-party vendor code is already HAL-compatible.
