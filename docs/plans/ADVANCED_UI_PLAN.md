# EasyClaw 高级界面重构计划 (方案 B)

## 目标
打造一个**既清爽又高级**的 TUI 界面，用 Rich Layout、状态管理、单界面交互。

## 设计原则
1. **单界面交互** —— 不全屏清屏，只更新变化的部分
2. **侧边栏导航** —— 固定侧边栏菜单，主内容区动态更新
3. **状态管理** —— 集中管理应用状态，通知、加载动画统一处理
4. **渐进式加载** —— 数据加载时显示 loading 状态
5. **通知系统** —— 顶部/底部通知栏显示操作结果
6. **快捷键支持** —— 数字键快速导航
7. **保留所有功能** —— 资产大盘、资源库、任务指派、工具配置、网关设置、系统辅助

## 技术栈
- Rich (Console, Layout, Panel, Table, Live, Align)
- Python 3.x
- 现有 core 模块（不变）

## 架构
```
easyclaw/
├── app.py              # 主入口 + 高级界面
├── core/               # 现有核心模块（不变）
├── tui/                # 现有模块（保留，备用）
└── ui/                 # 新的高级界面模块
    ├── __init__.py
    ├── state.py        # 状态管理
    ├── layout.py       # Layout 构建
    ├── components/     # 可复用组件
    │   ├── sidebar.py
    │   ├── header.py
    │   ├── footer.py
    │   └── notification.py
    └── screens/       # 各个界面
        ├── main.py
        ├── health.py
        ├── inventory.py
        ├── routing.py
        ├── tools.py
        ├── gateway.py
        └── system.py
```

## 功能映射
现有功能 → 新界面屏幕：
1. 资产大盘 → HealthScreen
2. 资源库 → InventoryScreen
3. 任务指派 → RoutingScreen
4. 工具配置 → ToolsScreen
5. 网关设置 → GatewayScreen
6. 系统辅助 → SystemScreen

## 交互流程
1. 启动 → 显示主界面（侧边栏 + 欢迎内容）
2. 用户按数字键/选择菜单 → 切换屏幕
3. 屏幕内操作 → 局部更新主内容区
4. 操作结果 → 显示通知
5. 按 0 → 返回主界面

## 下一步
调用 claude code CLI 来实现这个架构！
