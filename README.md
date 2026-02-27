# EasyClaw

EasyClaw 是 OpenClaw 的管理工具，提供：
- 稳定模式 TUI（默认，纯数字输入）
- Web UI（浏览器可视化管理）

> 说明：面板模式 TUI 已移除。若设置 `EASYCLAW_TUI_MODE=panel`，程序会提示已废弃并自动使用稳定模式。

## 1. 功能特性

- 模型与供应商管理
  - 供应商资源库管理
  - 模型池拉取、筛选、激活
  - 全局主模型与备用链管理
  - Agent 级模型覆盖、Spawn 默认模型策略
- Agent 与工作区管理
  - Agent 新增与工作区绑定
  - 访问限制（仅工作区）与控制层放行
- Agent 派发管理
  - 派发开关
  - 最大并发
  - 固定 Agent 白名单
- 服务配置
  - 官方搜索服务配置
  - 扩展搜索源配置（适配层）
  - 搜索主备切换
  - 配置备份与回滚
- 自动化与集成
  - 网关设置
  - 系统辅助（如重启、Onboard）

## 2. Quickstart

### macOS 一键安装

```bash
cd /path/to/easyclaw
bash install.sh
```

默认安装到：
- `~/.openclaw/easyclaw`
- 命令目录：`~/.local/bin`（若不在 PATH，脚本会提示）

### Linux 一键安装

```bash
cd /path/to/easyclaw
bash install.sh
```

如需安装到系统命令目录：

```bash
sudo bash install.sh
```

### Docker 一键安装

在你的容器内执行（示例容器名：`easyclaw-web`）：

```bash
docker exec -it easyclaw-web bash -lc 'cd /easyclaw && bash install.sh'
```

安装后可直接在容器中运行：

```bash
docker exec -it easyclaw-web bash -lc 'easyclaw tui'
docker exec -it easyclaw-web bash -lc 'easyclaw web --port 4231'
```

## 3. 运行执行方式

### 3.1 TUI 执行

```bash
easyclaw tui
```

特点：
- 稳定模式
- 数字输入 + 回车
- 不依赖方向键兼容性

### 3.2 Web UI 访问

启动：

```bash
easyclaw web --port 4231
```

浏览器访问：

- `http://127.0.0.1:4231/`
- 若启用 token：`http://127.0.0.1:4231/?token=<your-token>`

## 4. 常见问题

### Q1: `EASYCLAW_TUI_MODE=panel` 为什么不生效？

A: 面板模式已下线。该变量只做兼容提示，程序会自动进入稳定模式 TUI。

### Q2: 安装后找不到 `easyclaw` 命令？

A: 通常是命令目录未加入 PATH。按安装脚本提示执行：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

并写入 `~/.zprofile`（macOS）或 `~/.bashrc`（Linux）。

### Q3: Web UI 打不开？

A: 依次检查：
- 进程是否已启动（`easyclaw web --port 4231`）
- 端口是否被占用（改用其他端口）
- 若在 Docker 内运行，是否做了端口映射

### Q4: 提示 `openclaw` 不存在？

A: EasyClaw 可启动，但官方能力依赖 OpenClaw CLI。请先在当前环境安装并确保 `openclaw` 可执行。

### Q5: 配置改坏了怎么恢复？

A: 使用“服务配置 -> 配置备份与回滚”恢复最近备份。
