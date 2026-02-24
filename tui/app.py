"""
EasyClaw TUI - 现代化终端界面（增强版）
基于 Textual 框架，支持键盘操作、搜索过滤
"""
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, ListView, ListItem, Button, Input, Label
from textual.binding import Binding
from textual import work
import os
from datetime import datetime


# 主题色
THEME = {
    "primary": "#00D9FF",      # 青色
    "secondary": "#7C3AED",    # 紫色
    "success": "#10B981",      # 绿色
    "warning": "#F59E0B",      # 橙色
    "danger": "#EF4444",       # 红色
    "bg": "#0F172A",           # 深色背景
    "surface": "#1E293B",      # 卡片背景
    "text": "#F8FAFC",         # 主文字
    "muted": "#94A3B8",        # 辅助文字
}


class EasyClawApp(App):
    """EasyClaw TUI 主程序"""
    
    TITLE = "EasyClaw - OpenClaw 管理面板"
    SUB_TITLE = "↑↓ 导航 | Enter 确认 | Esc 返回 | / 搜索 | q 退出"
    
    BINDINGS = [
        Binding("q", "quit", "退出", show=True),
        Binding("r", "refresh", "刷新", show=True),
        Binding("b", "go_back", "返回", show=True),
        Binding("/", "focus_search", "搜索", show=True),
        Binding("1", "nav_1", "资产", show=True),
        Binding("2", "nav_2", "资源", show=True),
        Binding("3", "nav_3", "路由", show=True),
        Binding("4", "nav_4", "工具", show=True),
        Binding("5", "nav_5", "网关", show=True),
        Binding("6", "nav_6", "系统", show=True),
        Binding("escape", "cancel", "取消", show=True),
        Binding("n", "next_page", "下一页", show=True),
        Binding("p", "prev_page", "上一页", show=True),
    ]
    
    # 状态
    nav_path: list = []
    current_screen_name: str = "dashboard"
    search_query: str = ""
    current_page: int = 0
    items_per_page: int = 10
    
    def __init__(self):
        super().__init__()
        self.selected_index: int = 0
        self.current_items: list = []
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        # 搜索栏
        with Horizontal(id="search-bar"):
            yield Input(placeholder="输入搜索... (按 / 聚焦, Esc 取消)", id="search-input")
        
        # 主内容区
        with ScrollableContainer(id="main"):
            # 顶部导航
            with Horizontal(id="nav-bar"):
                yield Static("📊 资产", id="nav-dashboard")
                yield Static("⚙️ 资源", id="nav-inventory")
                yield Static("🤖 路由", id="nav-routing")
                yield Static("🧭 工具", id="nav-tools")
                yield Static("🌐 网关", id="nav-gateway")
                yield Static("🛠️ 系统", id="nav-system")
            
            # 列表视图
            with ListView(id="content-list"):
                pass
            
            # 内容显示区
            with Vertical(id="content-detail"):
                yield Static("加载中...", id="content-text")
        
        # 底部状态栏
        with Horizontal(id="status-bar"):
            yield Static("按 1-6 快速导航 | / 搜索 | q 退出", id="status-hint")
            yield Static("", id="status-page")
        
        yield Footer()
    
    def on_mount(self) -> None:
        self.nav_path = ["dashboard"]
        self.query_one("#search-input").display = False
        self.highlight_nav("dashboard")
        self.refresh_dashboard()
    
    # ==================== 导航 ====================
    
    def highlight_nav(self, active: str):
        nav_map = {
            "dashboard": "nav-dashboard",
            "inventory": "nav-inventory", 
            "routing": "nav-routing",
            "tools": "nav-tools",
            "gateway": "nav-gateway",
            "system": "nav-system"
        }
        
        for name, nav_id in nav_map.items():
            widget = self.query_one(f"#{nav_id}")
            if name == active:
                widget.update(f"▶ {self._get_nav_icon(name)}")
                widget.styles.color = THEME["primary"]
            else:
                widget.update(f"  {self._get_nav_icon(name)}")
                widget.styles.color = THEME["muted"]
    
    def _get_nav_icon(self, name: str) -> str:
        icons = {
            "dashboard": "📊 资产",
            "inventory": "⚙️ 资源",
            "routing": "🤖 路由",
            "tools": "🧭 工具",
            "gateway": "🌐 网关",
            "system": "🛠️ 系统"
        }
        return icons.get(name, "")
    
    def action_nav_1(self):
        self._navigate_to("dashboard")
    
    def action_nav_2(self):
        self._navigate_to("inventory")
    
    def action_nav_3(self):
        self._navigate_to("routing")
    
    def action_nav_4(self):
        self._navigate_to("tools")
    
    def action_nav_5(self):
        self._navigate_to("gateway")
    
    def action_nav_6(self):
        self._navigate_to("system")
    
    def _navigate_to(self, screen: str):
        self.current_screen_name = screen
        self.nav_path = [screen]
        self.current_page = 0
        self.search_query = ""
        self.query_one("#search-input").value = ""
        self.query_one("#search-input").display = False
        self.highlight_nav(screen)
        
        if screen == "dashboard":
            self.refresh_dashboard()
        elif screen == "inventory":
            self.refresh_inventory()
        elif screen == "routing":
            self.refresh_routing()
        elif screen == "tools":
            self.refresh_tools()
        elif screen == "gateway":
            self.refresh_gateway()
        elif screen == "system":
            self.refresh_system()
    
    def action_go_back(self):
        if len(self.nav_path) > 1:
            self.nav_path.pop()
            self.current_screen_name = self.nav_path[-1]
            self.highlight_nav(self.current_screen_name)
            self._refresh_current()
        elif self.current_screen_name != "dashboard":
            self._navigate_to("dashboard")
    
    def action_refresh(self):
        self._refresh_current()
    
    def _refresh_current(self):
        if self.current_screen_name == "dashboard":
            self.refresh_dashboard()
        elif self.current_screen_name == "inventory":
            self.refresh_inventory()
        elif self.current_screen_name == "routing":
            self.refresh_routing()
        elif self.current_screen_name == "tools":
            self.refresh_tools()
        elif self.current_screen_name == "gateway":
            self.refresh_gateway()
        elif self.current_screen_name == "system":
            self.refresh_system()
    
    def action_cancel(self):
        """取消搜索或返回"""
        if self.search_query:
            self.search_query = ""
            self.query_one("#search-input").value = ""
            self.query_one("#search-input").display = False
            self._refresh_current()
        elif self.current_screen_name != "dashboard":
            self.action_go_back()
    
    def action_focus_search(self):
        """聚焦搜索框"""
        self.query_one("#search-input").display = True
        self.query_one("#search-input").focus()
    
    def action_next_page(self):
        self.current_page += 1
        self._render_list()
    
    def action_prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_list()
    
    # ==================== 搜索过滤 ====================
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """搜索框输入变化"""
        self.search_query = event.value.lower()
        self.current_page = 0
        self._refresh_current()
    
    def _filter_items(self, items: list, fields: list) -> list:
        """根据搜索词过滤"""
        if not self.search_query:
            return items
        
        filtered = []
        for item in items:
            for field in fields:
                val = str(item.get(field, "")).lower()
                if self.search_query in val:
                    filtered.append(item)
                    break
        return filtered
    
    def _render_list(self):
        """渲染列表"""
        list_view = self.query_one("#content-list")
        list_view.clear()
        
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_items = self.current_items[start:end]
        
        for i, item in enumerate(page_items):
            label = item.get("label", str(item))
            list_view.append(ListItem(Label(label, id=f"item-{i}")))
        
        # 更新分页状态
        total_pages = max(1, (len(self.current_items) - 1) // self.items_per_page + 1)
        status = f"第 {self.current_page + 1}/{total_pages} 页 | 共 {len(self.current_items)} 项"
        self.query_one("#status-page").update(status)
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """列表项选中"""
        # 可以在这里处理选中操作
        pass
    
    # ==================== 各视图刷新逻辑 ====================
    
    def refresh_dashboard(self):
        """资产大盘"""
        from core import config, run_cli, run_cli_json
        import json
        
        # 获取数据
        status = run_cli_json(["status"])
        usage = run_cli_json(["status", "--usage"])
        
        # 账号数据
        auth_path = "/root/.openclaw/agents/main/agent/auth-profiles.json"
        auth_profiles = {}
        if os.path.exists(auth_path):
            try:
                with open(auth_path) as f:
                    auth_profiles = json.load(f).get("profiles", {})
            except Exception:
                pass
        
        # 构建显示
        lines = ["📊 资产大盘".center(50, "─"), ""]
        
        # 账号
        lines.append("┌─ 🔑 账号状态 ─────────────────────────────┐")
        if not auth_profiles:
            lines.append("│  尚未绑定任何账号                       │")
        else:
            for key, info in auth_profiles.items():
                provider = info.get("provider", "unknown")
                ptype = info.get("type", "unknown")
                email = info.get("email", "")
                
                if ptype == "oauth":
                    expires = info.get("expires", 0)
                    remaining = expires - int(datetime.now().timestamp() * 1000)
                    if remaining > 86400000:
                        time_str = f"{remaining // 86400000}天"
                    elif remaining > 3600000:
                        time_str = f"{remaining // 3600000}小时"
                    elif remaining > 0:
                        time_str = f"{remaining // 60000}分钟"
                    else:
                        time_str = "已过期"
                    display = f"{email} ({time_str})" if email else time_str
                else:
                    display = "API Key"
                
                icon = "🔑" if ptype == "oauth" else "🔐"
                lines.append(f"│  {icon} {provider:<14} │ {display:<18}│")
        
        lines.append("└────────────────────────────────────────────┘")
        
        # 模型
        models = config.get_all_models_flat()
        default = status.get("defaultModel", "未设置")
        
        lines.extend(["", "┌─ 🤖 已激活模型 ───────────────────────────┐"])
        
        if not models:
            lines.append("│  尚未激活任何模型                       │")
        else:
            # 过滤
            filtered = self._filter_items(models, ['full_name', 'display'])
            self.current_items = filtered
            
            start = self.current_page * self.items_per_page
            end = start + self.items_per_page
            page_models = filtered[start:end]
            
            for m in page_models:
                is_default = "⭐" if m['full_name'] == default else " "
                lines.append(f"│  {is_default} {m['display']:<40}│")
            
            if len(filtered) > self.items_per_page:
                lines.append(f"│  ... 还有 {len(filtered) - len(page_models)} 个 (按 n 下一页)      │")
        
        lines.append("└────────────────────────────────────────────┘")
        
        # 用量
        lines.extend(["", "┌─ 📈 用量配额 ─────────────────────────────┐"])
        
        providers = usage.get("usage", {}).get("providers", [])
        if providers:
            for p in providers[:3]:
                name = p.get("displayName") or p.get("provider", "?")
                plan = p.get("plan", "")
                title = f"{name} ({plan})" if plan else name
                lines.append(f"│  {title:<40}│")
                for w in p.get("windows", [])[:1]:
                    label = w.get("label", "")
                    used = w.get("usedPercent", 0)
                    left = 100 - int(used)
                    lines.append(f"│    {label}: {left}% left{' ' * 28}│")
        else:
            lines.append("│  无用量数据 (按 --usage 查看)           │")
        
        lines.append("└────────────────────────────────────────────┘")
        
        lines.extend(["", "┌─ 🎯 快捷操作 ─────────────────────────────┐"])
        lines.append("│  / 搜索模型  |  n 下一页  |  p 下一页        │")
        lines.append("│  1-6 切换模块  |  r 刷新  |  q 退出          │")
        lines.append("└────────────────────────────────────────────┘")
        
        # 显示到详情区
        self.query_one("#content-text").update("\n".join(lines))
        
        # 更新列表（用于搜索时显示）
        if models:
            filtered = self._filter_items(models, ['full_name', 'display'])
            self.current_items = filtered
            self._render_list()
    
    def refresh_inventory(self):
        """资源库"""
        from core import config
        import json
        
        profiles = config.get_profiles_by_provider()
        models = config.get_models_by_provider()
        all_providers = sorted(set(list(profiles.keys()) + list(models.keys())))
        
        # 过滤
        if self.search_query:
            all_providers = [p for p in all_providers if self.search_query in p.lower()]
        
        self.current_items = [{"label": p, "name": p} for p in all_providers]
        
        lines = ["⚙️ 资源库 - 服务商管理".center(50, "─"), ""]
        
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_providers = all_providers[start:end]
        
        if not page_providers:
            lines.append("│  无服务商                              │")
        else:
            lines.append(f"{'序号':<4} │ {'服务商':<20} │ {'账号':<4} │ {'模型':<4}")
            lines.append("─" * 50)
            
            for i, p in enumerate(page_providers):
                global_idx = start + i + 1
                p_count = len(profiles.get(p, []))
                m_count = len(models.get(p, []))
                lines.append(f"{global_idx:<4} │ {p:<20} │ {p_count:<4} │ {m_count:<4}")
        
        lines.extend(["", "─" * 50])
        lines.append("│  [Enter] 管理服务商  |  [N] 添加官方    │")
        lines.append("│  [C] 添加自定义  |  [B] 返回           │")
        lines.append("└────────────────────────────────────────────┘")
        
        self.query_one("#content-text").update("\n".join(lines))
        self._render_list()
    
    def refresh_routing(self):
        """任务指派"""
        from core import config
        
        global_model = config.get("agents.defaults.model", {})
        if isinstance(global_model, dict):
            primary = global_model.get("primary", "未设置")
            fallbacks = global_model.get("fallbacks", [])
        else:
            primary = global_model or "未设置"
            fallbacks = []
        
        lines = [
            "🤖 任务指派 - 模型路由".center(50, "─"),
            "",
            f"🌟 全局默认: {primary}",
        ]
        
        if fallbacks:
            lines.append(f"🔄 备选链: {' → '.join(fallbacks[:2])}")
        
        agents = config.get("agents.list", [])
        self.current_items = [{"label": f"{a.get('id', '?')} - {a.get('model', '跟随全局')}", "name": a.get("id", "")} for a in agents]
        
        lines.extend(["", "┌─ Agent 列表 ─────────────────────────────┐"])
        
        if not agents:
            lines.append("│  未发现已配置的 Agent                  │")
        else:
            start = self.current_page * self.items_per_page
            end = start + self.items_per_page
            page_agents = agents[start:end]
            
            for i, a in enumerate(page_agents):
                aid = a.get("id", "?")
                m = a.get("model", "跟随全局")
                if isinstance(m, dict):
                    m = m.get("primary", "跟随全局")
                lines.append(f"│  {i+1}. {aid:<12} │ {m:<28}│")
        
        lines.extend([
            "└────────────────────────────────────────────┘",
            "",
            "│  [D] 设置默认  |  [H] Heartbeat  |  [G] 子Agent │",
            "└────────────────────────────────────────────┘",
        ])
        
        self.query_one("#content-text").update("\n".join(lines))
        self._render_list()
    
    def refresh_tools(self):
        """工具配置"""
        self.current_items = []
        
        lines = [
            "🧭 工具配置".center(50, "─"),
            "",
            "┌─ Web 搜索 ───────────────────────────────┐",
            "│  1. Brave Search (默认)                   │",
            "│  2. Perplexity                            │",
            "└────────────────────────────────────────────┘",
            "",
            "┌─ 向量化/记忆检索 ─────────────────────────┐",
            "│  3. Auto (依赖 .env)                      │",
            "│  4. OpenAI                                │",
            "│  5. Gemini                                │",
            "│  6. Voyage                               │",
            "│  7. Local                                 │",
            "└────────────────────────────────────────────┘",
            "",
            "操作: 数字键选择 | S 保存 | B 返回"
        ]
        
        self.query_one("#content-text").update("\n".join(lines))
        
        # 清空列表
        list_view = self.query_one("#content-list")
        list_view.clear()
    
    def refresh_gateway(self):
        """网关设置"""
        from core import run_cli_json
        
        gw = run_cli_json(["config", "get", "gateway"])
        
        port = gw.get("port", 18789)
        bind = gw.get("bind", "loopback")
        auth = gw.get("auth", {}).get("mode", "token")
        
        self.current_items = []
        
        lines = [
            "🌐 网关设置".center(50, "─"),
            "",
            f"  端口 (port):    {port}",
            f"  绑定模式 (bind): {bind}",
            f"  认证模式 (auth): {auth}",
            "",
            "─" * 50,
            "",
            "┌─ 操作 ───────────────────────────────────┐",
            "│  [1] 修改端口    |  [2] 修改绑定         │",
            "│  [3] 修改认证    |  [4] 信任代理         │",
            "│  [5] WebUI 开关 |  [B] 返回             │",
            "└────────────────────────────────────────────┘",
        ]
        
        self.query_one("#content-text").update("\n".join(lines))
        
        list_view = self.query_one("#content-list")
        list_view.clear()
    
    def refresh_system(self):
        """系统辅助"""
        self.current_items = []
        
        lines = [
            "🛠️ 系统辅助".center(50, "─"),
            "",
            "┌─ 操作 ───────────────────────────────────┐",
            "│  1. 🔄 重启/重载配置                     │",
            "│  2. 🚀 检查系统更新                     │",
            "│  3. 🛡️ 配置回滚                         │",
            "│  4. 🧙 重新运行 Onboard                  │",
            "└────────────────────────────────────────────┘",
            "",
            "┌─ 当前环境 ───────────────────────────────┐",
        ]
        
        # 环境信息
        is_docker = os.path.exists("/.dockerenv") or os.path.exists("/proc/1/cgroup")
        lines.append(f"│  运行环境: {'Docker 容器' if is_docker else '宿主机':<28}│")
        lines.append(f"│  配置路径: /root/.openclaw              │")
        lines.append("└────────────────────────────────────────────┘")
        
        self.query_one("#content-text").update("\n".join(lines))
        
        list_view = self.query_one("#content-list")
        list_view.clear()


if __name__ == "__main__":
    app = EasyClawApp()
    app.run()
