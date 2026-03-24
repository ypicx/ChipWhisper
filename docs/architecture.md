# 架构说明

## 设计原则

这个项目现在明确采用：

- 规则优先
- LLM 辅助
- 文件化扩展

也就是说：

- 芯片事实、引脚复用、总线约束不交给大模型“猜”
- 大模型后续只负责解析需求、起草扩展包、补充说明
- 最终规划和生成以结构化数据为准

## 当前分层

### 1. Catalog / Extension Packs

职责：

- 提供内置芯片和内置模块
- 读取 `packs/` 下的外部芯片和模块定义
- 把“新增支持”从改 Python 代码改成加 JSON 和模板文件

当前入口：

- `stm32_agent/catalog.py`
- `stm32_agent/extension_packs.py`

### 2. Planner

职责：

- 检查芯片是否支持
- 检查模块是否支持
- 分配 I2C/UART/PWM/GPIO
- 处理保留引脚、避让引脚、地址冲突
- 输出 `project_ir`

当前入口：

- `stm32_agent/planner.py`

### 3. Project Generator

职责：

- 根据 `project_ir` 生成 `Keil5` 工程骨架
- 生成 `Core/App/Modules` 代码文件
- 如果模块 pack 自带模板文件，则优先使用模板

当前入口：

- `stm32_agent/keil_generator.py`

### 4. Build / Environment

职责：

- 检查 Keil 命令行环境
- 检查 STM32CubeF1 固件包
- 导入官方 Drivers
- 真实调用 `UV4 -b` 构建

当前入口：

- `stm32_agent/keil_builder.py`
- `stm32_agent/cube_repository.py`
- `stm32_agent/path_config.py`

### 5. CLI

职责：

- 提供统一命令入口
- 支持规划、生成、构建、路径诊断、pack 管理

当前入口：

- `stm32_agent/cli.py`

## 当前数据流

```text
request.json
-> load catalog + packs
-> planner
-> project_ir
-> keil generator
-> generated project
-> import STM32Cube drivers
-> doctor-keil / build-keil
```

## 模块资源请求格式

模块定义里的 `resource_requests` 现在支持数据驱动写法：

- `gpio_out`
- `gpio_in`
- `pwm_out`
- `uart_port`
- `i2c_device`
- `onewire_gpio`
- `gpio_out:reset`
- `gpio_in:int:optional`

这意味着后面很多模块不需要再去改规划器里的硬编码判断，只要能用这些资源类型描述，就可以直接加入。

## 为什么现在扩展性比以前强

以前新增模块/芯片主要靠：

- 改 `catalog.py`
- 改规划器里的特殊判断
- 改生成器里的硬编码

现在至少先把第一层拆开了：

- 芯片可以加 `packs/chips/*.json`
- 模块可以加 `packs/modules/<module>/module.json`
- 自定义模板可以加到 `packs/modules/<module>/templates/...`
- 已支持把厂商提供的 `.h/.c` 文件直接导入到模块 pack，再参与 Keil 工程生成

这一步还不是“完全插件化”，但已经从“改核心文件”变成“优先加文件”。

## 现实边界

当前这套文件化扩展，真实能做到的是：

- 新增同类资源模型的模块
- 新增芯片定义并参与规划
- 新增模块模板并进入生成工程

当前还没有完全做完的是：

- 不同芯片族的完整 family 适配
- 自动根据新芯片切换 startup/system/HAL family
- 上传手册后自动生成并自动验真扩展包

所以现在最稳的路线是：

1. 继续扩模块 pack
2. 再扩第二颗芯片
3. 再做 LLM 辅助导入 pack

## LangGraph 骨架

当前仓库已经补入一版 `LangGraph` 编排骨架，但它不会替换现有的确定性主链：

- `retrieve`
- `draft`
- `validate_request`
- `plan`
- `review (interrupt)`
- `scaffold`
- `import_drivers`
- `build`
- `repair`

对应代码：

- `stm32_agent/graph/state.py`
- `stm32_agent/graph/retrieval.py`
- `stm32_agent/graph/nodes.py`
- `stm32_agent/graph/workflow.py`

这一层的职责是：

- 管理全局状态
- 支撑人机审批断点
- 为后续桌面端“打回修改”“知识检索”“编译失败重试”预留统一编排层

详细说明见：

- `docs/langgraph_workflow.md`
