# EasyClaw 渐进式重写计划

## 原则
- **保留原有功能体验** —— 原来好用的地方一个都不能丢
- **渐进式调整** —— 不推翻重写，逐步优化
- **用 Rich 和 Questionary 提升体验** —— 但要克制，不要为了用而用
- **对齐 OpenClaw 官方 CLI** —— 优先使用官方 CLI 命令保证稳定性

## 阶段一：核心基础设施 ✅
- ✅ `core/__init__.py` - 配置管理和 CLI 封装
- ✅ 补充了：自动清理无效 token、备份机制、env 管理等细节

## 阶段二：移植核心功能逻辑 ✅ (全部完成)
从原来的 `claw-commander.py` 里把核心逻辑移植过来：

1. **资源库 (Inventory)** - 服务商/账号/模型管理 ✅ (已完成，在 `tui/inventory.py`)
2. **资产大盘 (Health)** - 账号状态、模型用量、子 Agent 状态 ✅ (已完成，在 `tui/health.py`)
3. **任务指派 (Routing)** - 全局默认模型、备选链、子 Agent 策略 ✅ (已完成，在 `tui/routing.py`)
   - 完全对齐 OpenClaw 官方 CLI：
     - `openclaw models set` - 设置默认模型
     - `openclaw models fallbacks [list|add|remove|clear]` - 管理备选链
4. **工具配置** - Web 搜索、向量化配置 ✅ (已完成，在 `tui/tools.py`)
5. **网关设置** - 端口、绑定、认证 ✅ (已完成，在 `tui/gateway.py`)
6. **系统辅助** - 重启、更新、回滚、Onboard ✅ (已完成，在 `tui/system.py`)

## 阶段三：用 Rich 和 Questionary 优化交互
- 用 `questionary` 做菜单选择（比 `input()` 体验好）
- 用 `rich` 做表格、进度条、状态展示
- 保留原来的状态图标（🟢🟡🔴⛔）

## 阶段四：模块化整理
- 把大函数拆成小函数
- 按功能模块组织文件

---

## 🎉 当前状态 (全部完成！)
- ✅ `core/__init__.py` - 完整的核心辅助函数
- ✅ `tui/health.py` - 资产大盘模块（保留了原来的所有细节体验）
- ✅ `tui/inventory.py` - 资源库模块（完整功能）
- ✅ `tui/routing.py` - 任务指派模块（完全对齐 OpenClaw 官方 CLI）
- ✅ `tui/tools.py` - 工具配置模块（Web 搜索 + 向量化）
- ✅ `tui/gateway.py` - 网关设置模块（端口/绑定/认证/WebUI）
- ✅ `tui/system.py` - 系统辅助模块（重启/更新/回滚/Onboard）
- ✅ `cli.py` - 主菜单已集成所有新模块，精简了旧代码
- 📦 依赖：已安装 `rich` 和 `questionary`

## 总结
所有核心模块移植完成！EasyClaw 现在：
- 保留了原来 easy_cli 的所有功能和细节体验
- 用 Rich 做了更好的表格和状态展示
- 任务指派模块完全对齐 OpenClaw 官方 CLI，保证稳定性
- 代码结构清晰，模块化良好




