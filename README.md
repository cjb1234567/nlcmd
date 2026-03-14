# Natural Language Command Executor (nlcmd)

一个把自然语言实时翻译成 Shell 命令并安全执行的跨平台控制台工具。基于 pydantic-ai Agent 框架，**内置语义记忆系统**，支持交互式命令确认、自定义技能（Skills）、工作目录管理，并在 Windows 下优先适配 PowerShell。

## 功能概览
- **语义记忆系统 (Semantic Memory)**：
  - **持久化存储**：重要信息自动记录为 Markdown 文件，方便查阅。
  - **语义检索**：基于 `txtai` 和 `BAAI/bge-small-zh` 模型，支持自然语言模糊检索历史记忆。
  - **上下文保持**：自动记住用户偏好、常用配置和重要上下文，提升多轮交互体验。
  - **记忆工具**：支持列出、添加、编辑、检索记忆，AI 可在思考过程中动态管理记忆内容。
- **定时任务系统 (Cron Scheduler)**：
  - **任务调度**：支持间隔调度（如每 10 分钟）和 cron 表达式（如 `0 9 * * *`）
  - **思考任务**：定时执行 AI 思考任务，自动处理复杂工作流
  - **索引重建**：定时检测记忆文件变化并重建语义索引，保持检索准确性
  - **交互式管理**：通过 CLI 添加、删除、查看定时任务
- **交互式流程**：
  - 单命令执行前确认 Y/n，可选 `--dry-run` 只展示不执行
  - 多选项场景支持输入序号选择
- **Workspace 工作目录管理**：
  - 默认工作目录为 `./workspace`，所有文件操作在此目录下执行
- **跨平台适配**：
  - 自动感知 OS 与 SHELL
  - Windows 下通过 `powershell -NoProfile -Command` 执行
  - PowerShell 语法规则自动注入系统提示
- **安全与易用**：
  - 执行前展示命令并确认
  - 语法高亮与美观面板输出（Rich 库）
- **高效文件操作**：
  - 支持直接写入文件（无需确认），方便创建临时文件或新文档
  - 智能区分“打开文件”与“读取内容”意图
- **自定义技能（Skills）**：
  - 支持 Python、PowerShell、bash、bat/cmd/exe 脚本
  - 自动选择合适的解释器执行

## Skills（Agent Skills 规范）
- **结构**
  - 每个技能是一个文件夹，包含 `SKILL.md`（必须）
  - `SKILL.md` 顶部是 YAML frontmatter：
    - `name`: 技能标识（必填）
    - `description`: 使用场景（必填）
    - `triggers`: 触发关键词列表（推荐）
  - 可选子目录：
    - `scripts/`: 可执行脚本
    - `references/`: 参考文档
    - `assets/`: 模板与资源
- **示例**
  - [skills/sysinfo/SKILL.md](skills/sysinfo/SKILL.md)

## 技能脚本解析与执行
当返回 execute 命令中包含 `scripts/<name>.<ext>`，自动重写为技能目录中的绝对路径：
- `.py`：使用系统 Python 解释器
- `.ps1`：使用 PowerShell（`-NoProfile -File`）
- `.sh`：使用 bash
- `.bat/.cmd/.exe`：直接执行

## 项目结构
```
nlcmd/
├── src/
│   └── nlcmd/           # 主包
│       ├── __init__.py  # 包入口
│       ├── main.py      # CLI 入口
│       ├── llm.py       # Agent 定义
│       ├── config.py    # 配置管理
│       ├── utils.py     # 命令执行
│       ├── ui.py        # 控制台输出
│       ├── cron/        # 定时任务模块
│       │   ├── cli.py       # 定时任务 CLI
│       │   ├── scheduler.py # 任务调度器
│       │   └── tasks.py     # 任务函数定义
│       └── memory/      # 记忆模块
│           ├── store.py     # 记忆存储
│           └── indexer.py   # 语义索引
├── skills/              # 技能目录
│   ├── canvas-design/   # Canvas 设计技能
│   ├── docx/            # Word 文档技能
│   └── sysinfo/         # 系统信息技能
├── workspace/           # 工作目录（自动创建）
├── pyproject.toml       # 项目配置
├── uv.lock              # 依赖锁定
├── .env.example         # 环境变量示例
└── README.md
```

## 环境要求
- Python 3.11+
- uv (推荐)
- 可访问的 OpenAI 兼容接口

## 安装与开发

**方式一：使用 uv（推荐）**

1. 安装 uv（如果尚未安装）：
   ```bash
   pip install uv
   ```

2. 同步依赖环境：
   ```bash
   uv sync
   ```

3. 运行命令：
   ```bash
   uv run nlcmd "查看当前目录下各文件夹大小"
   ```

**方式二：传统 pip 安装**

```bash
pip install -e .
```

复制 `.env.example` 为 `.env`，填写配置。

## 配置项（.env）
| 变量 | 说明 | 默认值 |
|------|------|--------|
| OPENAI_API_KEY | API 密钥 | 必填 |
| OPENAI_BASE_URL | 接口地址 | 无 |
| OPENAI_MODEL | 模型名称 | glm-4-5-flash |
| SHOW_REASONING | 显示 AI 推理过程 | false |
| SHOW_TOOLCALLING | 显示工具调用 | false |
| SHELL | Shell 类型 | Windows: powershell, 其他: /bin/bash |
| WORKSPACE | 工作目录 | ./workspace |

## 使用

**方式一：通过 uv 运行（推荐）**
```bash
# 单次执行
uv run nlcmd "查看当前目录下各文件夹大小"

# 交互模式
uv run nlcmd -i

# Dry-run 模式（只展示不执行）
uv run nlcmd "删除所有文件" --dry-run
```

**方式二：激活虚拟环境后运行**
```bash
# Windows
.venv\Scripts\activate
nlcmd "查看当前目录下各文件夹大小"

# Linux/macOS
source .venv/bin/activate
nlcmd "查看当前目录下各文件夹大小"
```

## 工作目录说明
- 默认工作目录：`./workspace`（相对于项目根目录）
- 所有文件操作在 workspace 目录下执行
- 目录不存在时自动创建
- 创建失败（权限不足/路径无效）时中断执行并报错

## 定时任务

通过 `nlcmd cron` 子命令管理定时任务：

```bash
# 添加定时任务（交互式）
uv run nlcmd cron add my-task

# 添加定时任务（命令行参数）
uv run nlcmd cron add daily-report --func run_thinking_agent --schedule "daily" --prompt "总结今日工作"

# 列出所有任务
uv run nlcmd cron list

# 删除任务
uv run nlcmd cron remove my-task

# 启动调度器
uv run nlcmd cron start
```

**任务类型**：
| 任务名 | 说明 |
|--------|------|
| `run_thinking_agent` | 执行 AI 思考任务，需要提供 `prompt` 参数 |
| `run_reindexing` | 检测记忆文件变化并重建语义索引 |

**调度格式**：
- 间隔调度：`every N seconds/minutes/hours/days`（如 `every 10 minutes`）
- 每日调度：`daily`（每天执行一次）
- Cron 表达式：`分 时 日 月 周`（如 `0 9 * * *` 表示每天 9:00）

## 开发

**环境准备**：
```bash
# 同步依赖（包含开发依赖）
uv sync --extra dev
```

**代码格式化与检查**：
```bash
uv run black src/
uv run ruff check src/
```

**打包发布**：
```bash
uv build
```

## 常见问题
- **命令执行失败**：检查 workspace 目录是否存在且有权限
- **PowerShell 语法问题**：系统提示已包含 PowerShell 语法规则
- **无法得到明确命令**：补充更多细节或使用交互模式

## 风险与安全
- API Key 通过环境变量或 `.env` 提供，避免硬编码
- 命令执行前需要用户确认
- 谨慎执行具有破坏性的命令

## 许可
MIT License

## 更新日志

### 2026-03-14：用户 Skills 目录支持

- **动态 Skills 加载**
  - 支持从用户 workspace 目录加载自定义 skills
  - SkillsToolset 同时扫描项目级 `skills/` 和用户级 `{workspace}/skills/` 目录
  - 用户可在自己的工作空间中定义专属技能，无需修改项目代码

### 2026-03-08：定时任务系统与记忆工具增强

- **定时任务系统 (Cron Scheduler)**
  - 新增 `nlcmd cron` 子命令，支持定时任务管理
  - 支持间隔调度（`every N minutes`）和 cron 表达式
  - 内置 `run_thinking_agent` 思考任务和 `run_reindexing` 索引重建任务
  - 任务配置持久化到 `cron_tasks.toml`

- **记忆工具增强**
  - 新增 `edit_memory` 工具，支持替换、删除、追加、重写记忆内容
  - `save_memory` 重命名为 `add_memory`，更准确描述其行为
  - AI 可在思考过程中动态管理记忆文件

### 2026-03-04：稳定性与体验优化

- **全异步化改造**
  - 所有 LLM 工具方法改为 `async def`，保证 API 一致性
  - 使用 `anyio.Path` 和 `anyio.open_file()` 进行异步文件操作
  - 使用 `asyncio.create_subprocess_shell` 替代 `subprocess.run` 实现原生异步命令执行
  - 使用 `anyio.to_thread.run_sync()` 处理同步用户输入

- **索引串行化**
  - `MemoryIndexer` 添加 `asyncio.Lock`，保证索引操作串行化
  - 提供 `search_async()`、`index_memory_async()` 异步接口

- **数据库并发优化**
  - 启用 SQLite WAL 模式，解决 "database is locked" 错误
  - 增加重试机制，提升索引写入稳定性

- **时间感知增强**
  - 系统提示中添加当前日期时间，LLM 能正确识别"今天"
  - `recall_memory` 返回结果中包含记忆的日期时间元数据

- **Bug 修复**
  - 修复 `anyio.Path.resolve()` 缺少 `await` 导致的协程错误

- **依赖更新**
  - 新增 `anyio>=3.7.0`，为 FastAPI 生态做准备

### 2026-03-02：记忆系统升级 (Memory System Upgrade)

- **语义记忆 (Semantic Memory)**
  - 集成 `txtai` 引擎，使用 `BAAI/bge-small-zh-v1.5` 模型提供中文语义向量支持。
  - 实现混合检索（Hybrid Search），结合 BM25 关键词匹配与向量语义检索，提升记忆召回准确率。

- **结构化存储 (Structured Storage)**
  - 实现 `MemoryStore` 类，采用双重存储策略：
    - **可读存储**：Markdown 文件按类别存放在 `workspace/memory/{category}/`。
    - **索引存储**：`txtai` 向量索引存放在 `workspace/memory/index/`。

- **新增工具 (New Tools)**
  - `save_memory`: 保存记忆到 Markdown 文件，并自动增量更新向量索引。
  - `recall_memory`: 支持通过自然语言查询相关记忆，返回内容及元数据（如时间、类别）。
  - `list_memories`: 列出当前已有的记忆分类，辅助 Agent 进行分类管理。

- **修复与优化**
  - 修复了索引目录未自动创建导致持久化失败的问题。
  - 优化了元数据存储结构，解决了 `txtai` 默认不支持字典类型元数据的问题。

- **依赖更新**
  - 新增 `txtai>=7.0.0` 及相关依赖。
