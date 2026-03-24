# 项目规划

## 阶段 1：真实规划器

已完成：

- `STM32F103C8T6` 芯片级知识库
- 常用模块规划
- I2C/UART/PWM/GPIO 分配
- 地址冲突和保留引脚检查
- `project_ir`

## 阶段 2：Keil5 工程生成

已完成：

- `Keil5 .uvprojx` 生成
- `GPIO/I2C/UART/TIM/PWM` 初始化骨架
- 常用模块 `.c/.h` 生成
- OLED 最小文本和数值显示示例

## 阶段 3：真实构建链

已完成：

- `doctor-cubef1`
- `import-cubef1-drivers`
- `doctor-keil`
- `build-keil`

已经验证过至少两套工程真实构建通过。

## 阶段 4：文件化扩展

本轮已完成：

- `packs/chips/*.json`
- `packs/modules/<module>/module.json`
- `packs/modules/<module>/templates/...`
- `doctor-packs`
- `init-packs`
- `new-module-pack`
- `new-chip-pack`
- `export-builtins`

这一步的意义是把“新增支持”从改核心代码，转成优先加文件。

## 阶段 5：第二批常用模块

建议优先级：

- `HC-SR04`
- `AHT20`
- `PCF8574`
- `74HC595`
- `LCD1602`
- `W25Qxx`

## 阶段 6：第二颗芯片

建议优先级：

- `STM32F103RCT6`
- `STM32F401CCU6`
- `STM32F401RE`

这一步要同时补：

- 芯片 pack
- family 适配
- startup/system/HAL 配置差异

## 阶段 7：LLM 辅助扩展包

目标不是让模型直接改核心工程，而是：

1. 用户上传用户手册、数据手册、示例代码
2. 大模型起草 `module.json` / `chip.json`
3. 大模型起草模板 `.c/.h`
4. 规则引擎校验
5. 人工确认后再纳入 pack

真实边界：

- 这一步可以做成“辅助生成”
- 不适合承诺“自动 100% 正确接入”

## 阶段 8：自然语言入口

本轮已完成第一版：

- 工作台自然语言 -> request JSON 草稿
- 基于当前启用 Profile 的受控 JSON 起草
- 本地 JSON 提取、规范化和基础校验

下一步继续做：

- 中文需求转更严格的结构化 JSON
- 缺参追问
- 需求澄清

## 暂不做

- Proteus 全自动仿真闭环
- 任意 STM32 任意模块一步到位
- 不经审核的自动扩展包落库
