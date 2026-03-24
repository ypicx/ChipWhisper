# LangGraph 工作流

当前仓库已经补入一套 `LangGraph` 编排骨架，但它不会替换现有的 `planner / keil_generator / keil_builder`。整体原则仍然是：

- `LLM` 负责理解需求、起草结构化请求
- `Planner` 负责事实约束、引脚和总线分配
- `Generator` 负责把 `project_ir` 落成工程文件
- `Builder` 负责导入驱动、调用 Keil 真实编译并导出 `HEX`
- `LangGraph` 负责把这些阶段串成可挂起、可恢复、可扩展的工作流

## 代码位置

- 状态定义：[stm32_agent/graph/state.py](../stm32_agent/graph/state.py)
- 检索层：[stm32_agent/graph/retrieval.py](../stm32_agent/graph/retrieval.py)
- 节点封装：[stm32_agent/graph/nodes.py](../stm32_agent/graph/nodes.py)
- 图与会话：[stm32_agent/graph/workflow.py](../stm32_agent/graph/workflow.py)

## 当前图拓扑

```text
START
  -> retrieve
  -> draft
  -> validate_request
  -> plan
  -> review (interrupt)
  -> scaffold
  -> import_drivers
  -> build
  -> repair
  -> END
```

说明：

- `review` 使用 `interrupt()` 做正式的人机确认闸门
- 桌面端在这里读取 `proposal_text / change_preview / file_change_preview`
- 用户点击“确认方案并开始生成”时，会通过 `Command(resume=...)` 恢复图执行
- 用户点击“打回并重算”时，会把 `user_feedback` 送回图状态，再次执行 `draft -> plan -> review`
- `repair` 现在已经是受控自修复第一版：
  - 先从 `build.log` 和 `build_logs` 里提取错误
  - 再读取相关源码片段
  - 让模型返回结构化 `search/replace` 补丁
  - 本地做白名单校验后才应用，并触发有限重试
  - 如果模型不可用或补丁不安全，会自动回退到人工复核

## State 关键字段

- `user_input`
- `attachments`
- `active_project_dir`
- `retrieved_docs`
- `retrieval_filters`
- `request_payload`
- `plan_result`
- `project_ir`
- `proposal_text`
- `change_preview`
- `file_change_preview`
- `is_approved`
- `user_feedback`
- `project_dir`
- `scaffold_result`
- `driver_import_result`
- `build_success`
- `build_logs`
- `build_result`
- `repair_count`
- `repair_strategy`

其中最关键的是：

- `request_payload`
  - 代表用户意图的结构化请求
- `project_ir`
  - 代表工程生成的唯一真相源
- `file_change_preview`
  - 代表生成前的文件级变更预览，供桌面端确认

## 生成前的文件级变更预览

现在 `plan` 节点已经会在不真正落盘的前提下，先计算本次方案将影响哪些文件。

预览来源：

- 复用 `keil_generator.py` 的同一套文件生成逻辑
- 逐个比较目标文件当前内容和即将生成的内容
- 生成 `create / update / unchanged` 三类状态

桌面端现在会在两个地方使用它：

- 右侧“待确认方案”里显示文件变更摘要
- 点击“确认方案并开始生成”前，弹窗再次列出重点文件预览

这样用户在真正生成工程前，就能知道：

- 会不会新建目录
- 会不会覆盖当前工程里的核心文件
- 这次大概会改哪些 `.c / .h / .uvprojx / README.generated.md`

## 最小调用方式

```python
from pathlib import Path

from stm32_agent.graph import GraphRuntime, STM32ProjectGraphSession
from stm32_agent.llm_config import LlmProfile

profile = LlmProfile(
    profile_id="demo",
    name="OpenAI Compatible",
    provider_type="openai_compatible",
    base_url="https://api.openai.com/v1",
    api_key="sk-...",
    model="gpt-5.4",
    system_prompt="",
    temperature=0.2,
    enabled=True,
)

runtime = GraphRuntime(
    profile=profile,
    repo_root=Path(r"D:\JAVA\ChipWhisper"),
)

session = STM32ProjectGraphSession(runtime)
pending = session.start("用 CT117E-M4 做一个 DHT11 温湿度显示项目")

print(pending.interrupts)
print(pending.values["proposal_text"])
print(pending.values["file_change_preview"][:5])

finished = session.resume(
    pending.thread_id,
    approved=True,
)

print(finished.values.get("build_success"))
```

## Generator 锚点沙盒

为了避免“修改当前项目”时粗暴覆盖用户代码，生成器现在已经加入了 `USER CODE` 锚点保留机制。

当前做法：

- 在 `main.c / peripherals.c / app_main.c / *_it.c / *_hal_msp.c` 中自动植入 `/* USER CODE BEGIN ... */`
- 重新生成前，先读取已有文件里的同名锚点区块
- 生成新骨架后，把旧文件里的锚点内容原样填回

这样做的意义是：

- 不需要引入复杂且脆弱的 C AST diff
- 更符合 STM32 / CubeMX 开发者已有心智
- 能先把“长周期伴随式开发”能力做稳

当前边界：

- 现在保的是显式锚点区，不是任意位置的自由改动
- 业务文件里若要长期保留手写逻辑，建议优先放进 `USER CODE` 区块

## 当前检索层

检索层现在已经从“轻量关键词检索”升级成了**本地 metadata + hybrid RAG**。

当前会扫描：

- `packs/` 里的芯片、板子、模块定义
- `packs/modules/*/templates` 里的 `.c/.h/.tpl` 示例代码
- `docs/`
- `README.md`
- 当前活动工程目录里的 `project_ir.json / REPORT.generated.md / README.generated.md`

当前检索流程：

1. 从用户输入里抽 `chip / board / module / mcu_family / terms`
2. 先做 metadata 硬过滤
3. 再做 hybrid 排序，综合这些信号：
   - doc_type / source_priority
   - 芯片、板子、模块实体精确命中
   - BM25-like 词项得分
   - 关键词重叠
   - 规范化短语命中

当前检索更适合回答：

- “这个板子上优先复用哪些板载资源”
- “某个模块初始化通常怎么接、怎么写”
- “当前项目还能不能继续加一个模块”
- “有没有现成 pack 或模板代码可以参考”

当前还没接的是：

- 向量数据库
- 外部知识源同步
- 语义 embedding 检索

## 当前边界

- 桌面端“方案确认 -> 生成工程”已经切到 LangGraph
- 普通闲聊仍然还是轻量聊天流，不是统一图工作流
- `repair` 已支持第一版自动补丁，但目前只支持受控的 `search/replace` 方案
- 检索层已经是本地 metadata + hybrid 检索，但还没接向量数据库
- checkpoint 目前还是内存态，不是磁盘持久化

## 下一步建议

1. 把“修改当前项目”的文件级变更预览再细化成模块级和文件级两层
2. 再把检索层接到向量数据库或本地 BM25 索引持久化
3. 给 `repair` 增加更强的补丁策略，比如限定到 `USER CODE` 区块或分文件类型修复
4. 让普通对话也统一进入图状态，减少桌面端两套行为差异
