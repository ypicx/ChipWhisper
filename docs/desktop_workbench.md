# ChipWhisper Desktop

## 目标

把当前命令行 STM32 Agent 演进成一个更像真实 Windows 工程软件的桌面工作台，而不是网页风格的聊天壳。

## 当前已实现

- 基于 `PySide6` 的桌面主窗口
- 深色、克制、偏 IDE / 工程工具气质的主题
- 左侧导航工作台：
  - `工作台`
  - `对话`
  - `项目`
  - `配置`
- `工作台` 页面支持：
  - 编辑请求 JSON
  - 调用 `plan_request`
  - 调用 `scaffold_from_request`
  - 调用 `doctor-paths`
  - 调用 `doctor-packs`
  - 调用 `doctor-cubef1`
  - 调用 `doctor-keil`
  - 调用 `build-keil`
  - 显示最近一次导出的 `HEX` 路径
  - 一键打开 `HEX` 所在目录
- `项目` 页面支持：
  - 浏览生成工程目录
  - 查看项目树
  - 预览源码文件
  - 读取 `project_ir.json`
- `配置` 页面支持：
  - 修改并保存 `stm32_agent.paths.json`
  - 修改并保存 `stm32_agent.llm.json`
  - 管理多组模型 Profile
  - 测试 OpenAI-compatible / Ollama 连接
- `对话` 页面支持：
  - 基于已启用 Profile 发起对话
  - OpenAI-compatible 流式输出
  - Ollama 流式输出
  - 显示当前项目目录和当前模型上下文
  - 可附带 `PDF / DOCX / XLSX / CSV / TXT / JSON / 图片` 作为需求补充

## 运行方式

推荐优先使用 conda 独立环境。

先创建并激活环境：

```powershell
conda env create -f .\environment.yml
conda activate stm32-agent
```

如果你只想单独补桌面依赖，也可以继续使用：

```powershell
python -m pip install -r .\requirements-desktop.txt
```

然后启动：

```powershell
python -m stm32_agent.desktop
```

## 当前配置文件

- 路径配置：`stm32_agent.paths.json`
- 模型配置：`stm32_agent.llm.json`
- 模型配置示例：`stm32_agent.llm.example.json`

如果模型配置文件还没生成，可以在桌面端配置页点击“生成模板”，也可以后续补 CLI 命令。

## 当前边界

这版桌面程序已经是真 UI，不是静态 mock，但也还不是最终商业版。当前边界包括：

- 已支持在工作台里把自然语言需求起草成 request JSON，但仍然依赖模型 Profile 和人工确认
- 已支持把 `PDF / DOCX / XLSX / CSV / TXT / JSON` 本地提取后作为需求上下文送给模型
- 已支持在 `OpenAI / OpenAI-compatible` 路径里发送图片给支持视觉的模型
- `Ollama` 当前仍然是文本模式，图片会退化成文件说明
- 还没有把聊天结果直接自动驱动完整工程流水线
- 还没有把附件自动转成模块 pack，但已经支持在桌面端选择官方 `.h/.c` 文件导入模块包
- 还没有做更高级的代码高亮和日志分级视图

## 下一步建议

1. 继续增强“自然语言 -> request JSON”的约束、追问和草稿质量
2. 给对话页增加“生成工程 / 打开项目 / 构建”快捷动作
3. 给项目页增加 `build.log` / `uvprojx` / `project_ir` 专项视图
4. 增加“从 PDF / 用户手册起草模块 pack”的 UI 入口
