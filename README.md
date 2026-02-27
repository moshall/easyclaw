# EasyClaw

OpenClaw 的本地管理工具，提供稳定的数字输入 TUI（默认）和面板模式 TUI，用于统一管理模型、供应商、Agent、搜索服务与系统配置。

## 当前能力

- `📊 资产大盘`：查看模型状态、配额与关键摘要
- `🧩 模型与供应商`：
  - 供应商/模型资源库管理
  - 全局模型优先级（主模型 + 备用链）
  - 指定 Agent 模型优先级（覆盖全局）
  - Spawn Agent 默认模型优先级（默认继承全局）
- `🧭 Agent 与工作区`：
  - 新增 Agent
  - 工作区手动绑定/自动识别绑定
  - 访问限制（仅工作区）与控制层快捷命令放行
- `👥 Agent派发管理`：
  - 派发开关
  - 最大派发并发
  - 固定 Agent 白名单
  - 按 Agent 维度管理派发策略
- `🛠️ 服务配置`：
  - 工具配置（搜索服务、向量化）
  - 搜索服务支持“官方 + 扩展源”统一配置
  - 搜索服务主备切换（Primary/Fallback）
  - 配置回滚（查看备份并一键恢复）
- `🔌 自动化与集成`：
  - 网关设置
  - 系统辅助（Onboard/重启/回滚）

## 搜索服务能力

### 官方搜索服务

当前菜单内支持配置官方搜索服务：

- `brave`
- `perplexity`
- `grok`
- `gemini`
- `kimi`

### 扩展搜索服务（适配层）

当前内置扩展适配：

- `zhipu`
- `serper`
- `tavily`

扩展配置文件：

- `/root/.openclaw/easyclaw/search_adapters.json`（容器内路径）

支持统一主备切换链：

- `official:*` 与 `adapter:*` 可混合配置
- 可演练 failover 验证切换行为

## 快速开始

### 一键安装（推荐）

```bash
sudo bash install.sh
```

安装脚本会自动：

- 识别运行环境（Docker/主机）
- 安装依赖并创建虚拟环境
- 将当前项目安装到 `/root/.openclaw/easyclaw`
- 自动探测 `openclaw.json`（必要时创建最小骨架）
- 注册命令：`easyclaw`、`easytui`

安装后直接使用：

```bash
easyclaw tui
easyclaw web
```

### 环境要求

- Python 3.10+
- OpenClaw CLI 可用（建议在容器内运行）
- Linux/Docker（推荐）

### 本地运行（当前目录）

```bash
python3 easyclaw.py tui
```

### 面板模式（可选）

```bash
EASYCLAW_TUI_MODE=panel python3 easyclaw.py tui
```

### Web 模式（可选）

```bash
python3 easyclaw.py web
```

- 默认端口：`4231`
- 自定义端口：

```bash
python3 easyclaw.py web --port 5001
# 或
EASYCLAW_WEB_PORT=5001 python3 easyclaw.py web
```

### 在 Docker 容器中运行（示例）

```bash
docker exec -it easyclaw-web bash
# 进入项目目录后运行
python3 easyclaw.py tui
```

## TUI 交互说明

- 默认采用“稳定模式”：数字输入 + 回车
- 主菜单输入 `1-6` 进入模块，输入 `0` 返回/退出
- 避免依赖方向键兼容性差异（尤其是 macOS 终端）

## 项目结构

```text
easyclaw/
├── easyclaw.py          # 统一入口（tui/web）
├── cli.py               # 稳定模式主界面
├── app.py               # 面板模式主界面
├── install.sh           # 一键安装脚本（部署到 /root/.openclaw/easyclaw）
├── core/                # 配置读写、执行器、搜索适配、同步等核心逻辑
├── tui/                 # 各模块菜单与交互实现
├── cmd/                 # 命令工具
├── web/                 # Web 服务端
└── tests/               # 回归测试
```

## 开发与测试

```bash
python3 -m unittest discover -s tests -p "test_*.py" -q
```

说明：

- 部分测试依赖 `rich` 与 OpenClaw 可执行环境，建议在 Docker 目标环境中运行。

## 提交范围约定

当前仓库默认不提交以下目录/文件：

- `openclaw_src/`
- `docs/`
- 调试/临时参考文件（见 `.gitignore`）

## 许可证

MIT
