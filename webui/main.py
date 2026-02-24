#!/usr/bin/env python3
"""
EasyClaw Web UI - FastAPI 后端（增强版）
功能与 CLI 完全对齐：搜索服务增强、资源库删除、自动备份
"""
import os
import sys
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core import (
    config,
    run_cli,
    run_cli_json,
    DEFAULT_AUTH_PROFILES_PATH,
    DEFAULT_BACKUP_DIR,
    DEFAULT_CONFIG_PATH
)

app = FastAPI(title="EasyClaw Web UI")

# 静态文件和模板
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# ========== 从 CLI tools.py 导入的常量 ==========
DEFAULT_OFFICIAL_SEARCH_PROVIDERS = [
    "brave",
    "perplexity",
    "grok",
]

OFFICIAL_SEARCH_KEYS = {
    "brave": "BRAVE_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "grok": "GROK_API_KEY",
}


def get_official_search_providers() -> list:
    """获取官方搜索服务列表（优先从配置读取，否则用默认列表）"""
    config.reload()
    custom_providers = config.data.get("easyclaw", {}).get("searchProviders", [])
    return list(set(DEFAULT_OFFICIAL_SEARCH_PROVIDERS + custom_providers))


def auto_backup_config():
    """自动备份配置"""
    config.reload()
    return config.backup()


# 简单的 token 验证
def get_gateway_token() -> str:
    """获取 OpenClaw gateway token"""
    try:
        result = run_cli_json(["config", "get", "gateway.auth.token"])
        if isinstance(result, str) and result:
            return result
        if isinstance(result, dict) and "error" not in result:
            return str(result)
    except Exception:
        pass
    return ""


GATEWAY_TOKEN = get_gateway_token()


# ========== Pydantic Models ==========
class LoginRequest(BaseModel):
    token: str


class SetDefaultModelRequest(BaseModel):
    model: str


class AddFallbackRequest(BaseModel):
    model: str


class RemoveFallbackRequest(BaseModel):
    index: int


class RestartGatewayRequest(BaseModel):
    confirm: bool = False


class DeleteProviderRequest(BaseModel):
    provider: str
    confirm: bool = False


class SetSearchProviderRequest(BaseModel):
    provider: str


class SetSearchConfigRequest(BaseModel):
    provider: str
    key: str
    value: str


class AddCustomOfficialProviderRequest(BaseModel):
    provider: str


# ========== 页面路由 ==========
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 - 登录或仪表盘"""
    return templates.TemplateResponse("index.html", {"request": request})


# ========== API 路由 - 身份验证 ==========
@app.post("/api/login")
async def api_login(login_req: LoginRequest):
    """登录验证"""
    if login_req.token == GATEWAY_TOKEN:
        return JSONResponse({"success": True, "message": "登录成功"})
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效"
        )


# ========== API 路由 - 资产大盘 (Health) ==========
@app.get("/api/health")
async def api_health():
    """资产大盘 - 获取完整健康状态"""
    try:
        status = run_cli_json(["models", "status", "--json"])
        return JSONResponse(status)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ========== API 路由 - 资源库 (Inventory) ==========
@app.get("/api/inventory/providers")
async def api_inventory_providers():
    """获取服务商列表"""
    try:
        config.reload()
        providers = config.get_all_providers()
        return JSONResponse({"providers": providers})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/inventory/models")
async def api_inventory_models():
    """获取已激活模型列表"""
    try:
        config.reload()
        all_models = config.get_all_models_flat()
        return JSONResponse({"models": all_models})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/inventory/models-all")
async def api_inventory_models_all():
    """获取所有可用模型（来自 models list --all）"""
    try:
        models_list = run_cli_json(["models", "list", "--all", "--json"])
        return JSONResponse(models_list)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/inventory/delete-provider")
async def api_inventory_delete_provider(req: DeleteProviderRequest):
    """删除服务商（带二次确认和备份）"""
    if not req.confirm:
        return JSONResponse({"success": False, "error": "需要确认"}, status_code=400)
    
    try:
        # 先备份
        backup_path = auto_backup_config()
        
        # 从 models.providers 中删除
        providers_cfg = get_models_providers()
        if req.provider in providers_cfg:
            del providers_cfg[req.provider]
            set_models_providers(providers_cfg)
        
        return JSONResponse({
            "success": True,
            "provider": req.provider,
            "backupPath": backup_path
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ========== API 路由 - 任务指派 (Routing) ==========
@app.get("/api/routing")
async def api_routing():
    """获取路由配置"""
    try:
        status = run_cli_json(["models", "status", "--json"])
        return JSONResponse({
            "defaultModel": status.get("defaultModel"),
            "fallbacks": status.get("fallbacks", []),
            "subagent": config.get_subagent_status()
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/routing/set-default")
async def api_routing_set_default(req: SetDefaultModelRequest):
    """设置默认模型"""
    try:
        # 先备份
        backup_path = auto_backup_config()
        
        stdout, stderr, code = run_cli(["models", "set", req.model])
        if code == 0:
            return JSONResponse({
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
                "backupPath": backup_path
            })
        else:
            return JSONResponse({
                "success": False,
                "error": stderr or "设置失败"
            }, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/routing/fallbacks/add")
async def api_routing_fallbacks_add(req: AddFallbackRequest):
    """添加备选模型"""
    try:
        # 先备份
        backup_path = auto_backup_config()
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "add", req.model])
        if code == 0:
            return JSONResponse({
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
                "backupPath": backup_path
            })
        else:
            return JSONResponse({
                "success": False,
                "error": stderr or "添加失败"
            }, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/routing/fallbacks/remove")
async def api_routing_fallbacks_remove(req: RemoveFallbackRequest):
    """删除备选模型"""
    try:
        # 先备份
        backup_path = auto_backup_config()
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "remove", str(req.index)])
        if code == 0:
            return JSONResponse({
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
                "backupPath": backup_path
            })
        else:
            return JSONResponse({
                "success": False,
                "error": stderr or "删除失败"
            }, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/routing/fallbacks/clear")
async def api_routing_fallbacks_clear():
    """清空备选链"""
    try:
        # 先备份
        backup_path = auto_backup_config()
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "clear"])
        if code == 0:
            return JSONResponse({
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
                "backupPath": backup_path
            })
        else:
            return JSONResponse({
                "success": False,
                "error": stderr or "清空失败"
            }, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ========== API 路由 - 搜索服务增强 ==========
@app.get("/api/search/providers")
async def api_search_providers():
    """获取官方搜索服务列表"""
    try:
        providers = get_official_search_providers()
        return JSONResponse({"providers": providers})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/search/config")
async def api_search_config():
    """获取搜索配置"""
    try:
        config.reload()
        search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
        return JSONResponse(search_cfg)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/search/set-provider")
async def api_search_set_provider(req: SetSearchProviderRequest):
    """设置默认搜索服务"""
    try:
        # 先备份
        backup_path = auto_backup_config()
        
        # 更新配置
        config.reload()
        if "tools" not in config.data:
            config.data["tools"] = {}
        if "web" not in config.data["tools"]:
            config.data["tools"]["web"] = {}
        if "search" not in config.data["tools"]["web"]:
            config.data["tools"]["web"]["search"] = {}
        
        config.data["tools"]["web"]["search"]["provider"] = req.provider
        config.save()
        
        return JSONResponse({
            "success": True,
            "provider": req.provider,
            "backupPath": backup_path
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/search/add-custom-official")
async def api_search_add_custom_official(req: AddCustomOfficialProviderRequest):
    """添加自定义官方搜索服务"""
    try:
        # 先备份
        backup_path = auto_backup_config()
        
        # 更新配置
        config.reload()
        if "easyclaw" not in config.data:
            config.data["easyclaw"] = {}
        if "searchProviders" not in config.data["easyclaw"]:
            config.data["easyclaw"]["searchProviders"] = []
        
        if req.provider not in config.data["easyclaw"]["searchProviders"]:
            config.data["easyclaw"]["searchProviders"].append(req.provider)
            config.save()
        
        return JSONResponse({
            "success": True,
            "provider": req.provider,
            "backupPath": backup_path
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ========== API 路由 - 系统操作 ==========
@app.post("/api/system/restart-gateway")
async def api_system_restart_gateway(req: RestartGatewayRequest = None):
    """重启网关"""
    try:
        stdout, stderr, code = run_cli(["gateway", "restart"])
        if code == 0:
            return JSONResponse({"success": True, "stdout": stdout, "stderr": stderr})
        else:
            return JSONResponse({"success": False, "error": stderr or "重启失败"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/system/config")
async def api_system_config():
    """获取完整配置（脱敏）"""
    try:
        config.reload()
        full_config = config.get_full_config()
        # 脱敏 token
        if "gateway" in full_config and "auth" in full_config["gateway"]:
            if "token" in full_config["gateway"]["auth"]:
                full_config["gateway"]["auth"]["token"] = "***"
        return JSONResponse(full_config)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ========== 辅助函数（从 core 导入，简化）==========
def get_models_providers() -> Dict:
    """获取 models.providers 配置"""
    result = run_cli_json(["config", "get", "models.providers"])
    if "error" not in result:
        return result
    return {}


def set_models_providers(providers_dict: Dict) -> bool:
    """设置 models.providers 配置"""
    payload = json.dumps(providers_dict or {})
    _, _, retcode = run_cli(["config", "set", "models.providers", payload, "--json"])
    return retcode == 0


# ========== 创建默认模板 ==========
def create_default_templates():
    """创建默认的 HTML 模板和静态文件"""
    
    # index.html（简化版，主要是后端 API 增强）
    index_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EasyClaw - 关键配置管理（增强版）</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; line-height: 1.6; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; border-radius: 12px; margin-bottom: 30px; }
        header h1 { font-size: 2rem; margin-bottom: 10px; }
        .card { background: white; border-radius: 12px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .card h2 { color: #667eea; margin-bottom: 20px; font-size: 1.3rem; }
        .btn { background: #667eea; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 1rem; cursor: pointer; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.9; }
        .btn-danger { background: #e74c3c; }
        .btn-success { background: #2ecc71; }
        .login-container { max-width: 400px; margin: 60px auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
        .login-container h1 { text-align: center; color: #667eea; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; color: #555; }
        .form-group input, .form-group select { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1rem; transition: border-color 0.2s; }
        .form-group input:focus, .form-group select:focus { outline: none; border-color: #667eea; }
        .hidden { display: none; }
        .toast { position: fixed; top: 20px; right: 20px; padding: 16px 24px; border-radius: 8px; color: white; font-weight: 500; box-shadow: 0 4px 20px rgba(0,0,0,0.2); z-index: 1000; opacity: 0; transform: translateY(-20px); transition: all 0.3s; }
        .toast.show { opacity: 1; transform: translateY(0); }
        .toast-success { background: #2ecc71; }
        .toast-error { background: #e74c3c; }
        .toast-info { background: #667eea; }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .status-item { background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }
        .status-item .label { color: #666; font-size: 0.9rem; margin-bottom: 8px; }
        .status-item .value { font-size: 1.8rem; font-weight: bold; color: #667eea; }
        @media (max-width: 768px) {
            header h1 { font-size: 1.5rem; }
            .status-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div id="toast" class="toast"></div>
    
    <div class="container">
        <!-- 登录页面 -->
        <div id="loginPage" class="login-container">
            <h1>🔐 EasyClaw</h1>
            <div class="form-group">
                <label for="tokenInput">请输入 OpenClaw Gateway Token</label>
                <input type="password" id="tokenInput" placeholder="粘贴你的 token" onkeypress="if(event.key==='Enter')login()">
            </div>
            <button class="btn" style="width:100%" onclick="login()">登录</button>
        </div>
        
        <!-- 仪表盘页面 -->
        <div id="dashboardPage" class="hidden">
            <header>
                <h1>🎛️ EasyClaw 关键配置管理（增强版）</h1>
                <p>搜索服务增强、资源库删除、自动备份</p>
            </header>
            
            <!-- 状态概览 -->
            <div class="card">
                <h2>📊 状态概览</h2>
                <div class="status-grid">
                    <div class="status-item">
                        <div class="label">默认模型</div>
                        <div class="value" id="defaultModel">-</div>
                    </div>
                    <div class="status-item">
                        <div class="label">备选链长度</div>
                        <div class="value" id="fallbackCount">-</div>
                    </div>
                    <div class="status-item">
                        <div class="label">已激活模型</div>
                        <div class="value" id="modelCount">-</div>
                    </div>
                    <div class="status-item">
                        <div class="label">子 Agent</div>
                        <div class="value" id="subagentStatus">-</div>
                    </div>
                </div>
            </div>
            
            <!-- 说明：后端 API 已增强，前端界面后续优化 -->
            <div class="card">
                <h2>📋 说明</h2>
                <p>后端 API 已增强：</p>
                <ul>
                    <li>搜索服务管理 API（官方+第三方，3个官方搜索服务）</li>
                    <li>资源库删除 API（带二次确认和备份）</li>
                    <li>所有修改操作前自动备份</li>
                </ul>
                <p>前端界面后续优化中...</p>
            </div>
        </div>
    </div>
    
    <script>
        let isLoggedIn = false;
        
        // Toast 提示
        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast toast-' + type;
            setTimeout(() => toast.classList.add('show'), 10);
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
        
        // 登录
        async function login() {
            const token = document.getElementById('tokenInput').value;
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token })
                });
                if (res.ok) {
                    isLoggedIn = true;
                    showDashboard();
                    loadData();
                    showToast('登录成功！', 'success');
                } else {
                    showToast('Token 无效，请重试', 'error');
                }
            } catch (e) {
                showToast('登录失败: ' + e.message, 'error');
            }
        }
        
        // 显示仪表盘
        function showDashboard() {
            document.getElementById('loginPage').classList.add('hidden');
            document.getElementById('dashboardPage').classList.remove('hidden');
        }
        
        // 加载数据
        async function loadData() {
            try {
                // 加载路由配置
                const routingRes = await fetch('/api/routing');
                if (routingRes.ok) {
                    const data = await routingRes.json();
                    document.getElementById('defaultModel').textContent = data.defaultModel || '-';
                    document.getElementById('fallbackCount').textContent = (data.fallbacks || []).length;
                }
                
                // 加载模型列表
                const modelsRes = await fetch('/api/inventory/models');
                if (modelsRes.ok) {
                    const data = await modelsRes.json();
                    document.getElementById('modelCount').textContent = (data.models || []).length;
                }
                
                // 加载子 Agent 状态
                const subagentRes = await fetch('/api/routing');
                if (subagentRes.ok) {
                    const data = await subagentRes.json();
                    const enabled = data.subagent && data.subagent.enabled;
                    document.getElementById('subagentStatus').textContent = 
                        enabled ? '✅ 开启' : '❌ 关闭';
                }
            } catch (e) {
                console.error('加载数据失败', e);
            }
        }
    </script>
</body>
</html>
"""
    
    # 写入 index.html
    index_path = os.path.join(templates_dir, "index.html")
    with open(index_path, "w") as f:
        f.write(index_html)
    
    print(f"✅ 默认模板已创建/更新: {index_path}")


if __name__ == "__main__":
    # 创建默认模板
    create_default_templates()
    
    # 启动服务
    import uvicorn
    print("\n🚀 Starting EasyClaw Web UI (增强版)...")
    print("📱 访问地址: http://localhost:2001/")
    print("🔑 Token 来自 OpenClaw gateway.auth.token")
    print()
    uvicorn.run(app, host="0.0.0.0", port=2001)
