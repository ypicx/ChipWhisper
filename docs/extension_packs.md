# Extension Packs

## 目标

让用户以后扩展芯片和模块时，优先通过“加文件”完成，而不是改核心 Python 代码。

## 目录结构

```text
packs/
  README.md
  chips/
    stm32f103c8t6.json
  boards/
    nucleo_f103rb.json
  modules/
    relay_gpio/
      module.json
      templates/
        modules/
          relay_gpio.h.tpl
          relay_gpio.c.tpl
```

## 模块 Pack

最小文件：

- `packs/modules/<module_key>/module.json`

可选模板：

- `packs/modules/<module_key>/templates/...`

示例字段：

```json
{
  "schema_version": "1.0",
  "kind": "module",
  "key": "relay_gpio",
  "display_name": "Relay GPIO",
  "summary": "Single-channel relay module driven by one GPIO output.",
  "hal_components": ["GPIO"],
  "template_files": ["modules/relay_gpio.c", "modules/relay_gpio.h"],
  "resource_requests": ["gpio_out:control"],
  "notes": ["This pack models the common VCC/GND/IN relay module wiring."],
  "sources": ["Generic 1-channel relay module wiring pattern."]
}
```

## 芯片 Pack

最小文件：

- `packs/chips/<chip_name>.json`

## 板级 Pack

最小文件：

- `packs/boards/<board_key>.json`

板级 pack 当前支持这些真实字段：

- `chip`
- `reserved_pins`
- `avoid_pins`
- `preferred_signals`

`preferred_signals` 适合描述板载资源偏好，例如：

- `led.control`
- `button.input`
- `uart_debug.tx`
- `uart_debug.rx`
- `can_port.tx`
- `spi_device.sck`
- `usb_device.dp`

芯片 pack 需要提供真实字段：

- 基本信息
- Flash / RAM
- `c_define`
- 保留引脚
- GPIO 优先级
- `interfaces`

`interfaces` 里当前支持：

- `i2c`
- `uart`
- `spi`
- `pwm`

## 模板文件规则

如果 `module.json` 里声明了：

- `modules/demo_sensor.c`
- `modules/demo_sensor.h`

那生成器会优先查找这些模板：

- `templates/modules/demo_sensor.c.tpl`
- `templates/modules/demo_sensor.h.tpl`
- 或同名非 `.tpl` 文件

如果找不到，就回退到内置占位模板。

## resource_requests 语法

支持这些基础资源：

- `gpio_out`
- `gpio_in`
- `pwm_out`
- `uart_port`
- `i2c_device`
- `onewire_gpio`

支持命名信号：

- `gpio_out:reset`
- `gpio_out:control`

支持可选信号：

- `gpio_in:int:optional`
- `gpio_out:reset:optional`

当信号是可选时，用户请求里可以用这些方式启用：

- 在 `options` 里直接给出该信号的引脚
- `use_<signal>: true`
- `use_<signal>_pin: true`
- `enable_<signal>: true`

例如：

```json
{
  "kind": "demo_sensor",
  "name": "sensor1",
  "options": {
    "use_int": true
  }
}
```

## CLI

```powershell
python -m stm32_agent doctor-packs
python -m stm32_agent init-packs
python -m stm32_agent new-module-pack my_sensor
python -m stm32_agent new-chip-pack STM32F103RCT6
python -m stm32_agent new-board-pack my_board
python -m stm32_agent export-builtins
```

## 推荐扩展流程

### 新增模块

1. 先用 `new-module-pack` 生成目录
2. 补 `module.json`
3. 把真实模板放进 `templates/`
4. 用 `doctor-packs` 检查能否加载
5. 再用 `plan` / `scaffold` 验证

### 新增芯片

1. 先用 `new-chip-pack` 生成骨架
2. 从真实数据手册填充引脚和外设映射
3. 用 `plan` 先验证规划
4. 再补 family 相关工程适配

### 新增板级 Profile

1. 先用 `new-board-pack` 生成骨架
2. 根据真实原理图填写 `chip / reserved_pins / avoid_pins / preferred_signals`
3. 用 `plan` 验证板载 LED、按键、串口是否被优先选中

## LLM 辅助边界

未来可以增加：

- 上传用户手册
- 上传示例代码
- 大模型起草 pack

但当前建议始终保持这个流程：

1. LLM 起草
2. 规则校验
3. 人工审核
4. 再使用

原因很简单：手册抽取、地址解析、引脚理解这些地方，大模型可以帮忙提速，但不能替代事实校验。
