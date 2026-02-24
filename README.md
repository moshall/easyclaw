# EasyClaw

> ⚠️ **Status: Work in Progress** - 核心功能尚未完全走通，API 可能随时变更

OpenClaw 管理工具 - 同时支持 TUI（交互式菜单）和 CLI（命令行）两种模式

## 功能特性

- 📊 **资产大盘** - 查看账号状态、模型资产、用量配额
- ⚙️ **资源库** - 管理服务商、账号、模型
- 🤖 **任务指派** - 配置 Agent 模型路由
- 🧭 **工具配置** - Web 搜索、向量化检索
- 🌐 **网关设置** - 端口、绑定、认证
- 🛠️ **系统辅助** - 重启、更新、回滚

## 快速开始

### 环境要求

- Python 3.8+
- OpenClaw CLI 已安装
- Linux/Docker 环境

### 安装

```bash
# 克隆仓库
git clone https://github.com/Gardma/easyclaw.git
cd easyclaw

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .
```

### 使用

```bash
# TUI 模式（交互式菜单）
easyclaw tui

# CLI 模式
# 查看状态
easyclaw status

# 列出模型
easyclaw models list

# 获取配置
easyclaw config get agents.defaults.model
```

## 键盘快捷键（TUI 模式）

| 快捷键 | 功能 |
|--------|------|
| ↑↓ | 导航 |
| Enter | 确认 |
| Esc | 返回 |
| q | 退出 |
| r | 刷新 |
| / | 搜索 |
| 1-6 | 快速切换模块 |

## 项目结构

```
easyclaw/
├── cli.py              # 入口
├── core/               # 核心模块
│   ├── __init__.py     # 配置和 API
├── tui/                # TUI 模块
│   ├── app.py          # 主程序
├── cmd/                # CLI 命令
│   ├── status.py
│   ├── models.py
│   ├── account.py
│   ├── config.py
│   └── install.py
└── .venv/             # 虚拟环境
```

## 开发状态

⚠️ **当前阶段：核心功能开发中**

- [x] 项目基础架构
- [x] TUI 界面框架
- [x] CLI 命令结构
- [ ] API 集成完全走通
- [ ] 配置管理完善
- [ ] 测试覆盖

**已知问题**：
- 部分 OpenClaw 配置校验尚未完全兼容
- 服务商管理 API 调用可能不稳定

## 贡献

欢迎提交 Issue 和 PR！由于项目处于早期阶段，API 可能随时变更。

## 许可证

MIT
