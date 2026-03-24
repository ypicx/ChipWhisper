# CT117E-M4 / STM32G431RBT6 支持说明

这份说明只记录已经按官方资料和本机真实编译结果确认过的内容，不把还没落地的资源提前写成“已支持”。

## 当前已支持

- 目标板卡
  - `CT117E-M4`
  - `STM32G431RBT6`
- 工程链
  - `STM32CubeG4`
  - `Keil5`
  - `fromelf` 自动导出 `hex`
- 本机已验证的 `STM32Cube` 仓库路径
  - `C:\Users\YOUR_NAME\STM32Cube\Repository`
  - `STM32Cube_FW_G4_V1.6.2`

## 已确认的板载资源

- LCD 并口
  - `PC0-PC15`
  - `PB9 = CS`
  - `PB8 = RS`
  - `PB5 = WR`
  - `PA8 = RD`
- 板载 I2C 总线
  - `PB6 = SCL`
  - `PB7 = SDA`
- 板载 I2C 器件
  - `AT24C02`
  - `MCP4017`
- 板载 8 灯锁存器
  - `PD2 = LED_LE`
  - `PC8-PC15` 为锁存数据总线
  - 这一组数据线和 LCD 高 8 位共用
- 板载 4 按键
  - `B1 = PB0`
  - `B2 = PB1`
  - `B3 = PB2`
  - `B4 = PB14`
  - 生成器默认按低电平按下处理

## 已接入项目的板级能力

- board pack
  - [ct117e_m4_g431.json](../packs/boards/ct117e_m4_g431.json)
- 板载 LCD 模块
  - [ct117e_lcd_parallel](../packs/modules/ct117e_lcd_parallel/module.json)
- 板载 LED 锁存器模块
  - [ct117e_led_latch](../packs/modules/ct117e_led_latch/module.json)
- 板载按键模块
  - 直接复用 [key_bank_4_gpio](../packs/modules/key_bank_4_gpio/module.json)，由 board profile 固定到 `PB0/PB1/PB2/PB14`
- 板载数字电位器模块
  - [mcp4017_i2c](../packs/modules/mcp4017_i2c/module.json)
- 板载 EEPROM
  - 直接复用内置 `at24c02_i2c`

## 已验证示例

- 板载资源综合示例
  - [g431_ct117e_board_resources.json](../examples/g431_ct117e_board_resources.json)
- 板载按键联动 LCD/LED 示例
  - [g431_ct117e_key_demo.json](../examples/g431_ct117e_key_demo.json)
- DHT11 最小示例
  - [g431_dht11_demo.json](../examples/g431_dht11_demo.json)

## 可复用项目模板

这些不是比赛题名模板，而是更适合反复做项目时直接起步的板级入口：

- 参数设置台
  - [g431_ct117e_settings_console.json](../examples/g431_ct117e_settings_console.json)
  - 复用板载 `LCD + 4 按键 + EEPROM`
- 环境监测站
  - [g431_ct117e_env_station.json](../examples/g431_ct117e_env_station.json)
  - 复用板载 `LCD + 4 按键 + 8 LED`，外接一个 `DHT11`
- I2C 仪表盘
  - [g431_ct117e_i2c_dashboard.json](../examples/g431_ct117e_i2c_dashboard.json)
  - 复用板载 `LCD + 4 按键 + EEPROM + MCP4017`，再外挂一个 `BH1750`

## 本机真实编译结果

以下工程都已经在当前机器上真实生成、导入 `CubeG4 Drivers`、通过 `Keil` 编译并导出 `hex`：

- [g431_ct117e_board_resources_project_v3.uvprojx](../out/g431_ct117e_board_resources_project_v3/MDK-ARM/g431_ct117e_board_resources_project_v3.uvprojx)
- [g431_ct117e_board_resources_project_v3.hex](../out/g431_ct117e_board_resources_project_v3/MDK-ARM/Objects/g431_ct117e_board_resources_project_v3.hex)
- [g431_ct117e_key_demo_project.uvprojx](../out/g431_ct117e_key_demo_project/MDK-ARM/g431_ct117e_key_demo_project.uvprojx)
- [g431_ct117e_key_demo_project.hex](../out/g431_ct117e_key_demo_project/MDK-ARM/Objects/g431_ct117e_key_demo_project.hex)
- [g431_dht11_demo_project.uvprojx](../out/g431_dht11_demo_project/MDK-ARM/g431_dht11_demo_project.uvprojx)
- [g431_dht11_demo_project.hex](../out/g431_dht11_demo_project/MDK-ARM/Objects/g431_dht11_demo_project.hex)

## 当前仍然保守处理的部分

- 板载双路信号发生器相关资源已经从原理图确认接到 `PB4` 和 `PA15`，但还没有封成专用 module pack，也还没做频率测量/输入捕获模板。
- 板上的模拟扩展、分压电位器等资源，还没有完成专门的 board-level 模块化封装。
- 当前重点是“把官方板载资源起步工程跑通”，不是“把整块竞赛板所有扩展一次性全自动化”。

## 推荐使用方式

1. 先用 [g431_ct117e_board_resources.json](../examples/g431_ct117e_board_resources.json) 跑通板载 `LCD + LED + EEPROM + MCP4017`。
2. 再用 [g431_ct117e_key_demo.json](../examples/g431_ct117e_key_demo.json) 验证板载按键、LCD 和 8 灯联动。
3. 之后优先从“参数设置台 / 环境监测站 / I2C 仪表盘”这些项目模板起步，再叠加你自己的业务逻辑。
