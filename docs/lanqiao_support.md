# Lanqiao Support

当前项目支持两条蓝桥杯相关方向，但成熟度不同。

## 已支持

- 旧版 `STM32F103RBT6` 训练 / 竞赛平台
  - [stm32f103rb_training_board.json](../packs/boards/stm32f103rb_training_board.json)
- `CT117E-M4 / STM32G431RBT6` 官方竞赛平台
  - [ct117e_m4_g431.json](../packs/boards/ct117e_m4_g431.json)

## 当前推荐的 G431 板级能力

- 板载 LCD 并口显示
- 板载 4 按键
- 板载 8 LED 锁存器
- 板载 I2C 总线
- 板载 EEPROM `AT24C02`
- 板载数字电位器 `MCP4017`
- 默认串口调试链路

这些能力已经写进 `CT117E-M4` 的 board pack，规划结果和 `project_ir` 会直接带出，方便后续做对话式方案推荐。

## 常见模块

- [led_bank_8_gpio](../packs/modules/led_bank_8_gpio/module.json)
- [key_bank_4_gpio](../packs/modules/key_bank_4_gpio/module.json)
- [ds1302_gpio](../packs/modules/ds1302_gpio/module.json)
- [pcf8591_i2c](../packs/modules/pcf8591_i2c/module.json)
- [ct117e_lcd_parallel](../packs/modules/ct117e_lcd_parallel/module.json)
- [ct117e_led_latch](../packs/modules/ct117e_led_latch/module.json)
- [mcp4017_i2c](../packs/modules/mcp4017_i2c/module.json)
- `active_buzzer`
- `uart_debug`

## 示例请求

- [lanqiao_legacy_common.json](../examples/lanqiao_legacy_common.json)
- [g431_running_leds.json](../examples/g431_running_leds.json)
- [g431_ct117e_board_resources.json](../examples/g431_ct117e_board_resources.json)
- [g431_ct117e_key_demo.json](../examples/g431_ct117e_key_demo.json)
- [g431_ct117e_settings_console.json](../examples/g431_ct117e_settings_console.json)
- [g431_ct117e_env_station.json](../examples/g431_ct117e_env_station.json)
- [g431_ct117e_i2c_dashboard.json](../examples/g431_ct117e_i2c_dashboard.json)

## `CT117E-M4` 的真实边界

以下资源已经确认并接入生成链：

- LCD 并口
- 板载 I2C
- `AT24C02`
- `MCP4017`
- 板载 4 按键
- 板载 8 LED 锁存器

以下资源还没有封成可直接复用的 module pack：

- 双路信号发生器相关路径
- 模拟扩展和电位器路径

更细的板级说明见：

- [ct117e_g431_support.md](./ct117e_g431_support.md)
