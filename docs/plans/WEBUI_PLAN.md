# EasyClaw 独立 Web UI 开发计划

## 目标
开发一个独立的 Web UI，专注于**关键配置管理**，让用户轻松掌握和管理：
- 账号状态
- 模型列表
- 路由配置
- 用量概览
- 关键开关

## 技术栈
- **后端**: FastAPI (Python) —— 轻量、快速、自动生成 API 文档
- **前端**: HTML + CSS + Vanilla JS (或简单的 Vue/React) —— 移动端适配
- **身份验证**: OpenClaw gateway token
- **配置读写**: 通过 OpenClaw CLI / 直接读写配置文件

## 功能范围 (MVP)
1. **登录页** —— 输入 OpenClaw token 登录
2. **仪表盘** —— 关键信息概览
   - 账号状态卡片
   - 模型用量概览
   - 子 Agent 开关状态
   - 默认模型展示
3. **账号管理** —— 查看账号列表和状态
4. **模型管理** —— 查看已激活模型和可用状态
5. **路由配置** —— 设置默认模型和备选链
6. **设置** —— 修改 gateway token、重启服务等

## 目录结构
```
easyclaw/
├── webui/
│   ├── __init__.py
│   ├── main.py           # FastAPI 主入口
│   ├── auth.py           # 身份验证
│   ├── config.py         # 配置读写封装
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py     # 资产大盘 API
│   │   ├── inventory.py  # 资源库 API
│   │   ├── routing.py    # 路由 API
│   │   └── system.py     # 系统 API
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── app.js
└── ... (现有文件不变)
```

## 下一步
1. 创建 webui 目录结构
2. 用 claude code 辅助开发 FastAPI 后端
3. 开发简单的前端界面
4. 测试集成
