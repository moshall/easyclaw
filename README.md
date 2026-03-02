# EasyClaw

EasyClaw 是 OpenClaw 的管理工具，提供：
- TUI 管理台（终端交互）
- Web UI（浏览器可视化管理）

## 1. 功能特性

- 模型与供应商管理
  - 供应商资源库管理
  - 模型池拉取、筛选、激活
  - 全局主模型与备用链管理
  - Agent 级模型覆盖、Spawn 默认模型策略
- Agent 与工作区管理
  - Agent 新增与工作区绑定
  - 运行环境 / 工作区访问 / 工具能力 配置
  - 控制层快捷命令放行
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
- 终端内完成主要配置管理
- 数字输入 + 回车
- 低依赖，适合服务器环境

### 3.2 Web UI 访问

启动：

```bash
easyclaw web --port 4231
```

浏览器访问：

- `http://127.0.0.1:4231/`
- 若启用 token：`http://127.0.0.1:4231/?token=<your-token>`

### 3.3 Agent 运行环境与权限怎么理解

EasyClaw 把 OpenClaw 官方的 `sandbox + tools` 映射成更直观的 2 层：

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

## 4. 常见问题

### Q1: Web UI 打不开？

A: 依次检查：
- 进程是否已启动（`easyclaw web --port 4231`）
- 端口是否被占用（改用其他端口）
- 若在 Docker 内运行，是否做了端口映射

### Q2: 提示 `openclaw` 不存在？

A: EasyClaw 可启动，但官方能力依赖 OpenClaw CLI。请先在当前环境安装并确保 `openclaw` 可执行。

### Q3: 配置改坏了怎么恢复？

A: 使用“服务配置 -> 配置备份与回滚”恢复最近备份。

### Q4: “只读自己的工作区”是不是绝对隔离？

A: 不是单独靠这个选项就能绝对隔离。只有在启用 sandbox 时，这类“工作区访问”设置才会变成硬隔离语义；如果 sandbox 关闭，它更接近默认工作目录控制。
