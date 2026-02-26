# Natural Language Command Executor (nlcmd)

一个可把自然语言实时翻译成 Shell 命令并安全执行的跨平台控制台工具。当前实现支持结构化 JSON 协议、交互式澄清/选择、显示 AI 对话记录，并在 Windows 下优先适配 PowerShell。

## 功能概览
- 结构化 JSON 协议：模型严格返回三种形态之一
  - execute：{"status":"execute","command":"..."}
  - choose：{"status":"choose","options":[{"cmd":"...","reason":"..."}, ...]}
  - clarify：{"status":"clarify","questions":["...","..."]}
- 交互式流程：
  - 单命令执行前确认 Y/n，可选 --dry-run 只展示不执行
  - choose 场景下支持输入序号选择
  - clarify 场景下根据问题继续补充信息，直至得到命令或候选
- 对话记录开关：SHOW_REASONING=true 时打印 System/User/Assistant 全对话
- 跨平台适配：
  - 自动感知 OS 与 SHELL；Windows 下通过 powershell -NoProfile -Command 执行，正确捕获输出
- 安全与易用：
  - 执行前展示命令并确认
  - 语法高亮与美观面板输出

## 目录与关键文件
- 主流程与 CLI：[main.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/main.py)
  - 结构化交互入口：process_query
  - 分支处理：process_payload（execute/choose/clarify）
  - Windows PowerShell 执行分支
- 结构化 LLM 调用：[llm.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/llm.py)
  - generate_structured/continue_structured
  - _build_system_prompt（统一 JSON 协议提示）
  - _request_json（优先使用 JSON Schema/json_object，失败时回退普通模式）
  - _parse_json（容错解析）
- 配置读取：[config.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/config.py)

## 环境要求
- Python 3.9+（推荐）
- 可访问的 OpenAI 兼容接口（或自建服务）

## 安装
- 安装依赖：
  ```bash
  pip install -r requirements.txt
  ```
- 准备环境变量：
  - 复制 `.env.example` 为 `.env`，并填写你的配置

## 配置项（.env）
- OPENAI_API_KEY=你的APIKey
- OPENAI_BASE_URL=可选，兼容的接口地址（例如：https://open.bigmodel.cn/api/paas/v4）
- OPENAI_MODEL=模型名称（例如：glm-4.7-flash；默认见 [config.py](file:///c:/Users/chenjinbo/Documents/trae_projects/console/config.py)）
- SHOW_REASONING=true/false（是否显示 AI 对话记录，仅影响展示）
- SHELL=/bin/bash 或 powershell（用于命令适配）

## 使用
- 单次查询：
  ```bash
  python main.py "查看当前目录下各文件夹大小"
  ```
- 交互模式：
  ```bash
  python main.py -i
  ```
  - 当返回为 choose 时，输入序号选择候选命令
  - 当返回为 clarify 时，按问题提示补充信息
- 只展示命令、不执行：
  ```bash
  python main.py -i --dry-run
  ```

## 输出说明
- AI 对话记录（可选）：展示 System/User/Assistant 原始文本，便于排查
- 命令展示：高亮面板内显示待执行命令
- 执行结果：分别展示 stdout 与 stderr 面板；返回码不为 0 时给出提示

## 常见问题
- “Invalid JSON returned”
  - 已集成自动重试与 JSON Schema/json_object 强制；如仍失败，请检查模型能力或缩短提问，避免超长输出被截断
- Windows 模型返回带有 `powershell` 前缀
  - 已在执行层统一处理；真实命令会用 `powershell -NoProfile -Command` 执行
- 无法得到明确命令
  - 进入 clarify 流程，按问题补充细节；或在交互模式中继续对话

## 打包与发布（建议）
- 使用 PyInstaller 在目标系统上分别打包：
  ```bash
  pip install pyinstaller
  pyinstaller --onefile --name nlcmd main.py
  ```
  - Windows 产物：`dist/nlcmd.exe`
  - macOS 与 Linux 产物：`dist/nlcmd`
- 建议用 CI（GitHub Actions）分别在 windows-latest、macos-latest、ubuntu-latest 构建三套产物
- 注意：
  - Python 不支持跨编译原生二进制，需在目标系统上打包
  - macOS 可能需要代码签名与 notarization；Linux 注意 glibc 版本兼容

## 风险与安全
- API Key 请通过环境变量或 `.env` 提供，避免硬编码
- 命令执行前都需要用户确认；谨慎执行具有破坏性的命令

## 许可
- 许可证未设置，可根据你的需求添加 LICENSE 文件
