# Natural Language Command Executor (nlcmd)

一个把自然语言实时翻译成 Shell 命令并安全执行的跨平台控制台工具。基于 pydantic-ai Agent 框架，支持交互式命令确认、自定义技能（Skills）、工作目录管理，并在 Windows 下优先适配 PowerShell。

## 功能概览
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
  - [skills/sysinfo/SKILL.md](file:///c:/Users/chenjinbo/Documents/trae_projects/console/skills/sysinfo/SKILL.md)

## 技能脚本解析与执行
当返回 execute 命令中包含 `scripts/<name>.<ext>`，自动重写为技能目录中的绝对路径：
- `.py`：使用系统 Python 解释器
- `.ps1`：使用 PowerShell（`-NoProfile -File`）
- `.sh`：使用 bash
- `.bat/.cmd/.exe`：直接执行

## 目录与关键文件
- **主入口**：[main.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/main.py)
- **Agent 定义**：[llm.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/llm.py)
  - `CommandGenerator` 类：Agent 封装
  - `run_shell_command` 工具：执行单命令
  - `propose_options` 工具：多选项选择
- **配置**：[config.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/config.py)
- **命令执行**：[utils.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/utils.py)
  - `run_shell_command_with_confirmation`: 带确认的命令执行
  - `_ensure_workspace_dir`: 工作目录检查与创建
  - `WorkspaceError`: 工作目录异常

## 环境要求
- Python 3.9+
- 可访问的 OpenAI 兼容接口

## 安装
```bash
pip install -r requirements.txt
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
**单次查询**：
```bash
python main.py "查看当前目录下各文件夹大小"
```

**交互模式**：
```bash
python main.py -i
```

**Dry-run 模式**（只展示命令，不执行）：
```bash
python main.py "列出文件" --dry-run
```

## 工作目录说明
- 默认工作目录：`./workspace`（相对于项目根目录）
- 所有文件操作在 workspace 目录下执行
- 目录不存在时自动创建
- 创建失败（权限不足/路径无效）时中断执行并报错

## 常见问题
- **命令执行失败**：检查 workspace 目录是否存在且有权限
- **PowerShell 语法问题**：系统提示已包含 PowerShell 语法规则
- **无法得到明确命令**：补充更多细节或使用交互模式

## 打包与发布
```bash
pip install pyinstaller
pyinstaller --onefile --name nlcmd main.py
```

## 风险与安全
- API Key 通过环境变量或 `.env` 提供，避免硬编码
- 命令执行前需要用户确认
- 谨慎执行具有破坏性的命令

## 许可
MIT License
