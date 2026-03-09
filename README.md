# ClawPanel

ClawPanel 是 OpenClaw 的管理工具，提供：
- TUI 管理台（终端交互）
- Web UI（浏览器可视化管理）

说明：仓库已更名为 `moshall/clawpanel`，文档与安装脚本 URL 已同步更新；运行命令统一为 `clawpanel` / `clawtui`。

## 1. 功能特性

- 模型与凭据管理
  - 管理 `models.providers`（OpenAI / Google / Vercel / 自定义 provider）
  - 拉取模型池、激活/停用模型、维护主备链路
  - 支持全局模型策略、Agent 覆盖策略、Spawn 默认策略
  - 记忆检索向量配置统一落位到 `agents.defaults.memorySearch.*`
- Agent 生命周期与权限管理
  - 官方 `openclaw agents add` 创建 Agent，保留官方 schema 兼容
  - 可视化配置 `sandbox + tools`（工作区访问、能力预设）
  - 细粒度权限策略（目录白名单、fs/exec/deny/elevated）
  - 控制面命令白名单独立管理（不污染官方字段）
- 派发与协作
  - `subagents.allowAgents` 开关、白名单与并发上限
  - Agent 级工作区绑定和运行路径管理
  - 支持多 Agent 协作场景的策略化配置
- 服务与可运维能力
  - 搜索源配置（官方 + 适配层）与主备切换
  - 配置备份/回滚、运行状态查看、快速诊断入口
  - TUI + Web 双入口，适配服务器与桌面环境

## 2. Quickstart

### 升级前重要声明

- OpenClaw 官方更新频率较高，升级前建议先与 AI 或维护者核对本次版本是否涉及：
  - 安全策略变更（如 sandbox、权限模型、执行策略）
  - 文件/目录权限边界调整（如 workspace 挂载、读写范围）
  - 配置文件结构与字段迁移（如 `openclaw.json` schema 变化）
  - 社区已知回归问题或兼容性 Bug
- 完成上述核对后再执行升级，可显著降低生产环境风险。

安装前建议先确认：
- Python 3.10+（Linux 建议额外安装 `python3-venv`）
- OpenClaw CLI（`openclaw` 命令可执行）
- `curl`、`tar`、`bash` 可用（在线安装脚本依赖）
- 一键脚本会尝试自动安装缺失系统依赖（不含 OpenClaw CLI），如需关闭可加 `--no-auto-deps`

### npm 安装（新增）

全局安装（推荐）：

```bash
npm install -g @moshall/clawpanel
```

安装后可直接使用：

```bash
clawpanel tui
clawpanel web --port 4231
```

说明：
- npm 包会在全局安装后尝试自动执行 `install.sh`；若失败，可手动执行 `clawpanel install` 或 `clawpanel-install`。
- 首次执行 `clawpanel` 时如果发现运行时未安装，会自动触发引导安装（可用 `CLAWPANEL_AUTO_BOOTSTRAP=0` 关闭）。
- 需自定义安装目录时，可在 npm 安装前传入环境变量：

```bash
CLAWPANEL_INSTALL_DIR=/opt/clawpanel \
CLAWPANEL_BIN_DIR=/usr/local/bin \
CLAWPANEL_OPENCLAW_HOME=/root/.openclaw \
npm install -g @moshall/clawpanel
```

### 在线一键安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-online.sh | bash
```

自定义安装目录（便于脚本化调用）：

```bash
curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-online.sh | bash -s -- --install-dir /opt/clawpanel
```

也可同时指定命令目录：

```bash
curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-online.sh | bash -s -- --install-dir /opt/clawpanel --bin-dir /opt/clawpanel/bin
```

关闭自动依赖安装（仅检查，不自动装）：

```bash
curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-online.sh | bash -s -- --no-auto-deps
```

### 本地源码安装（macOS / Linux）

```bash
cd /path/to/easyclaw
bash install.sh
```

默认安装到：
- `~/.openclaw/clawpanel`

兼容说明：
- 若历史目录 `~/.openclaw/easyclaw` 已存在，安装脚本会优先复用该目录（避免覆盖迁移风险）。
- 新命令为 `clawpanel` / `clawtui`，同时保留 `easyclaw` / `easytui` 兼容别名。

说明：
- 安装脚本会自动探测 `openclaw` 可执行路径（如 `/usr/bin/openclaw` 或 `/usr/local/bin/openclaw`）并写入运行环境。

如需安装到系统命令目录：

```bash
sudo bash install.sh
```

CLI 方式自定义目录（适合其他工具调用）：

```bash
bash install.sh --install-dir /opt/clawpanel --bin-dir /opt/clawpanel/bin
```

### Docker 一键安装

推荐直接在宿主机执行（目标容器需已启动）：

```bash
set -o pipefail
curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-docker.sh | \
  bash -s -- --container clawpanel-web
```

自定义安装目录（传给容器内 `install.sh`）：

```bash
set -o pipefail
curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-docker.sh | \
  bash -s -- --container clawpanel-web \
  --install-dir /root/.openclaw/software/clawpanel \
  --openclaw-home /root/.openclaw \
  --bin-dir /usr/local/bin
```

说明：
- `install-docker.sh` 会在容器内检查并自动补齐 `bash/curl/tar`（若缺失）。
- 脚本不会自动安装 OpenClaw CLI；请确保容器内 `openclaw` 可执行，或先自行安装。
- `--install-dir` / `--openclaw-home` / `--bin-dir` 必须写**容器内路径**，不是宿主机路径。
- 若不确定路径映射，先查挂载关系：

```bash
docker inspect clawpanel-web --format '{{range .Mounts}}{{println .Source "=>" .Destination}}{{end}}'
```

1Panel 常见场景示例（宿主机 `/opt/1panel/apps/openclaw_260205` 挂载到容器 `/root/.openclaw`）：

```bash
set -o pipefail
curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-docker.sh | \
  bash -s -- --container openclaw_260205 \
  --install-dir /root/.openclaw/software/clawpanel \
  --openclaw-home /root/.openclaw
```

也可直接在容器内执行在线安装：

```bash
docker exec -i clawpanel-web bash -lc 'curl -fsSL https://raw.githubusercontent.com/moshall/clawpanel/main/install-online.sh | bash'
```

安装后可直接在容器中运行：

```bash
docker exec -it clawpanel-web bash -lc 'clawpanel tui'
docker exec -it clawpanel-web bash -lc 'clawpanel web --port 4231'
```

Docker 权限建议：
- ClawPanel 在 Docker 环境会默认禁用 sandbox（避免容器内套 Docker 的常见权限报错）。
- 若你需要 sandbox 隔离，建议改为宿主机安装 OpenClaw；或自行准备 DooD/DinD 后再手动调整 OpenClaw 原生配置。

### 环境差异与默认处理（实体机 / Docker）

| 项 | 实体机 / VM | Docker 容器 |
|---|---|---|
| 运行环境识别 | 非 Docker | 自动识别 Docker |
| 能力预设 | 支持全部（含 sandbox 预设） | 自动降级到非 sandbox 预设 |
| `workspace-collab` 等需 sandbox 预设 | 保持原样 | 自动转成 `full-access` |
| 细粒度权限策略 | 可设置可清空 | 可设置可清空（附加在 `tools/sandbox`） |
| 推荐隔离方式 | OpenClaw sandbox | 容器挂载边界 + `workspaceOnly` + deny |

提示：
- Docker 内关闭 sandbox 只是不走官方沙盒，不影响你配置 `tools.fs.workspaceOnly`、`tools.exec.security`、`tools.deny`、`tools.elevated.enabled`。
- 如果你要做真正硬隔离，建议通过容器挂载设计（每个 agent 独立挂载目录）实现。

## 3. 运行执行方式

### 3.1 TUI 执行

```bash
clawpanel tui
```

特点：
- 终端内完成主要配置管理
- 数字输入 + 回车
- 低依赖，适合服务器环境

### 3.2 Web UI 访问

启动：

```bash
clawpanel web --port 4231
```

浏览器访问：

- `http://127.0.0.1:4231/`
- 若启用 token：`http://127.0.0.1:4231/?token=<your-token>`

### 3.3 Agent 运行环境与权限怎么理解

ClawPanel 把 OpenClaw 官方的 `sandbox + tools` 映射成更直观的 2 层：

- 工作区访问
  - `不访问工作区`
    - 不挂载真实 workspace
    - 适合纯协调、消息中转、最小数据接触
  - `只读自己的工作区`
    - 只能读自己的 workspace，不能写
    - 适合审查、检索、分析
  - `读写自己的工作区`
    - 可读写自己的 workspace
    - 适合编码、改文档、修配置
- 工具能力
  - `完全开放`
    - 高权限模式，适合主 Agent 或高信任维护 Agent
  - `只读分析`
    - 只读、只分析，不写不执行
  - `安全执行`
    - 可执行命令，但不写文件
  - `工作区协作`
    - 读写自己的 workspace，适合开发协作
  - `通讯协调`
    - 偏调度、路由、消息协同

注意：
- 只有在启用 sandbox 时，“工作区访问”才代表硬隔离
- 若 sandbox 关闭，workspace 更接近默认工作目录，不等于真正文件隔离
- 新增“细粒度目录/功能权限”支持（默认不配置，可单独保存/清空）：
  - `tools.profile`（`full` / `coding` / `messaging` / `minimal`，用于新版 OpenClaw 通用手动适配）
  - 目录白名单绑定（`sandbox.docker.binds`）
  - `tools.fs.workspaceOnly`
  - `tools.exec.security`
  - `tools.deny`
  - `tools.elevated.enabled`
- 细粒度权限元数据默认保存到 `~/.openclaw/clawpanel/agent_meta.json`（兼容读取旧路径 `~/.openclaw/easyclaw/agent_meta.json`，且不会污染 OpenClaw 官方 schema）

## 4. 常见问题

### Q1: Web UI 打不开？

A: 依次检查：
- 进程是否已启动（`clawpanel web --port 4231`）
- 端口是否被占用（改用其他端口）
- 若在 Docker 内运行，是否做了端口映射

### Q2: 提示 `openclaw` 不存在？

A: ClawPanel 可启动，但官方能力依赖 OpenClaw CLI。请先在当前环境安装并确保 `openclaw` 可执行。

### Q3: 配置改坏了怎么恢复？

A: 使用“服务配置 -> 配置备份与回滚”恢复最近备份。

### Q4: “只读自己的工作区”是不是绝对隔离？

A: 不是单独靠这个选项就能绝对隔离。只有在启用 sandbox 时，这类“工作区访问”设置才会变成硬隔离语义；如果 sandbox 关闭，它更接近默认工作目录控制。
