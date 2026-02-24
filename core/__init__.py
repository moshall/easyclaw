"""
Core 模块 - OpenClaw 配置和 API 封装
"""
import json
import os
import subprocess
from datetime import datetime
from typing import Any, Optional, Dict, List

# 配置路径
DEFAULT_CONFIG_PATH = os.environ.get("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json")
DEFAULT_BACKUP_DIR = os.environ.get("OPENCLAW_BACKUP_DIR", "/root/.openclaw/backups")
DEFAULT_AUTH_PROFILES_PATH = os.environ.get("OPENCLAW_AUTH_PROFILES_PATH", "/root/.openclaw/agents/main/agent/auth-profiles.json")
DEFAULT_ENV_PATH = os.environ.get("OPENCLAW_ENV_PATH", "/root/.openclaw/.env")
DEFAULT_ENV_TEMPLATE_PATH = os.environ.get("OPENCLAW_ENV_TEMPLATE_PATH", "/root/.openclaw/workspace/templates/openclaw.env.example")

# CLI 路径
OPENCLAW_BIN = os.environ.get("OPENCLAW_BIN", "/usr/local/bin/openclaw")

# 无效 token 值的黑名单
INVALID_TOKEN_PATTERNS = [
    "Symbol(clack:cancel)",
    "Symbol(clack:",
    "undefined",
    "null",
    "",
]


class OpenClawConfig:
    """OpenClaw 配置管理"""
    
    def __init__(self, path: str = DEFAULT_CONFIG_PATH):
        self.path = path
        self.data: dict = {}
        self._load()

    def _is_dry_run(self) -> bool:
        return os.environ.get("EASYCLAW_DRY_RUN", "0") == "1"
    
    def _load(self):
        """加载配置"""
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r') as f:
                    self.data = json.load(f)
        except Exception as e:
            print(f"加载配置失败: {e}")
            self.data = {}
    
    def reload(self):
        """重新加载配置"""
        self._load()
    
    def save(self) -> bool:
        """保存配置（自动备份）"""
        try:
            if self._is_dry_run():
                return True

            # 内容无变化则跳过备份/写入
            if os.path.exists(self.path):
                try:
                    with open(self.path, 'r') as f:
                        current = json.load(f)
                    if current == self.data:
                        return True
                except Exception:
                    pass

            self.backup()
            with open(self.path, 'w') as f:
                json.dump(self.data, f, indent=2)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def backup(self) -> Optional[str]:
        """备份配置"""
        if self._is_dry_run():
            return None

        if not os.path.exists(DEFAULT_BACKUP_DIR):
            os.makedirs(DEFAULT_BACKUP_DIR, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{DEFAULT_BACKUP_DIR}/easyclaw_{timestamp}.json.bak"
        
        if os.path.exists(self.path):
            subprocess.run(["cp", self.path, backup_path], check=False)
            return backup_path
        return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split(".")
        val = self.data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default
        return val
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置值"""
        keys = key.split(".")
        data = self.data
        
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        
        data[keys[-1]] = value
        return self.save()
    
    # ========== 便捷方法 ==========
    
    def get_profiles_by_provider(self) -> dict:
        """按服务商归类账号"""
        profiles = self.data.get("auth", {}).get("profiles", {})
        pool = {}
        for key, info in profiles.items():
            provider = info.get("provider", "unknown")
            if provider not in pool:
                pool[provider] = []
            info['_key'] = key
            pool[provider].append(info)
        return pool
    
    def get_models_by_provider(self) -> dict:
        """按服务商归类模型"""
        models = self.data.get("agents", {}).get("defaults", {}).get("models", {})
        pool = {}
        
        for full_name, info in models.items():
            if "/" in full_name:
                provider, model_name = full_name.split("/", 1)
            else:
                provider = info.get("provider", "其他")
                model_name = full_name
            
            if provider not in pool:
                pool[provider] = []
            
            model_info = {
                '_full_name': full_name,
                '_display_name': model_name,
                '_provider': provider
            }
            model_info.update(info)
            pool[provider].append(model_info)
        
        return pool
    
    def get_all_models_flat(self) -> list:
        """获取所有模型扁平列表"""
        result = []
        for provider, models in self.get_models_by_provider().items():
            for m in models:
                result.append({
                    'full_name': m['_full_name'],
                    'display': f"[{m['_provider']}] {m['_display_name']}"
                })
        return result


def run_cli(args: list, capture: bool = True) -> tuple:
    """执行 openclaw CLI 命令
    
    Args:
        args: 命令参数列表
        capture: 是否捕获输出
    
    Returns:
        (stdout, stderr, returncode)
    """
    cmd = [OPENCLAW_BIN] + args
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            shell=False,
            timeout=30
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "命令执行超时", 1
    except Exception as e:
        return "", str(e), 1


def run_cli_json(args: list) -> dict:
    """执行 CLI 并尝试解析 JSON"""
    stdout, stderr, code = run_cli(args + ["--json"])
    if code == 0 and stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"error": "JSON 解析失败", "raw": stdout}
    return {"error": stderr or "命令执行失败", "code": code}


# ========== 辅助函数 ==========

def sanitize_auth_profiles(provider_name: Optional[str] = None) -> List[str]:
    """检查并清理无效的 auth profile 条目
    
    Args:
        provider_name: 如果指定，只检查该 provider 的条目
    
    Returns:
        list: 被清理的条目 key 列表
    """
    cleaned = []
    try:
        if not os.path.exists(DEFAULT_AUTH_PROFILES_PATH):
            return cleaned
        
        with open(DEFAULT_AUTH_PROFILES_PATH, 'r') as f:
            data = json.load(f)
        
        profiles = data.get("profiles", {})
        keys_to_remove = []
        
        for key, profile in profiles.items():
            # 如果指定了 provider，只检查匹配的
            if provider_name and profile.get("provider") != provider_name:
                continue
            
            # 检查 token 类型的 profile
            if profile.get("type") == "token":
                token_val = profile.get("token", "")
                # 检查是否是无效值
                for pattern in INVALID_TOKEN_PATTERNS:
                    if pattern and pattern in str(token_val):
                        keys_to_remove.append(key)
                        break
                # 空 token 也无效
                if not token_val or str(token_val).strip() == "":
                    if key not in keys_to_remove:
                        keys_to_remove.append(key)
        
        # 执行清理
        if keys_to_remove:
            for key in keys_to_remove:
                del profiles[key]
                cleaned.append(key)
            
            # 保存修改
            with open(DEFAULT_AUTH_PROFILES_PATH, 'w') as f:
                json.dump(data, f, indent=2)
    
    except Exception as e:
        print(f"⚠️ 清理 auth profiles 时出错: {e}")
    
    return cleaned


def normalize_provider_name(name: str) -> str:
    """标准化服务商名称"""
    name = (name or "").strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        name = name[1:-1].strip()
    return name


def read_env_keys() -> Dict[str, str]:
    """读取 .env 文件中的 key"""
    keys = {}
    if not os.path.exists(DEFAULT_ENV_PATH):
        return keys
    try:
        with open(DEFAULT_ENV_PATH, "r") as f:
            for line in f.read().splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                keys[k.strip()] = v.strip()
    except Exception:
        pass
    return keys


def set_env_key(key: str, value: str) -> bool:
    """设置 .env 文件中的 key"""
    if not key:
        return False
    try:
        lines = []
        if os.path.exists(DEFAULT_ENV_PATH):
            with open(DEFAULT_ENV_PATH, "r") as f:
                lines = f.read().splitlines()
        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("")
            new_lines.append(f"{key}={value}")
        # 确保目录存在
        env_dir = os.path.dirname(DEFAULT_ENV_PATH)
        if env_dir and not os.path.exists(env_dir):
            os.makedirs(env_dir, exist_ok=True)
        with open(DEFAULT_ENV_PATH, "w") as f:
            f.write("\n".join(new_lines) + "\n")
        return True
    except Exception as e:
        print(f"⚠️ 更新 .env 失败: {e}")
        return False


def check_existing_key(key_name: str, provider_name: Optional[str] = None) -> bool:
    """检查是否已有 key 存在"""
    # 1) .env
    env_keys = read_env_keys()
    if key_name in env_keys and env_keys[key_name]:
        return True
    # 2) models.providers
    providers = get_models_providers()
    if provider_name and provider_name in providers:
        if providers.get(provider_name, {}).get("apiKey"):
            return True
    # 3) auth-profiles.json
    try:
        if os.path.exists(DEFAULT_AUTH_PROFILES_PATH):
            with open(DEFAULT_AUTH_PROFILES_PATH, "r") as f:
                data = json.load(f)
            profiles = data.get("profiles", {})
            for _, profile in profiles.items():
                if provider_name and profile.get("provider") != provider_name:
                    continue
                ptype = profile.get("type")
                if ptype in ["api_key", "token"]:
                    if profile.get("key") or profile.get("token"):
                        return True
    except Exception:
        pass
    return False


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


def get_memory_search_config() -> Dict:
    """获取 memorySearch 配置"""
    config.reload()
    return config.data.get("memorySearch", {}) or {}


def clear_memory_search_config(clear_provider: bool = False):
    """清除 memorySearch 配置"""
    if clear_provider:
        run_cli(["config", "unset", "memorySearch.provider"])
    run_cli(["config", "unset", "memorySearch.local"])
    run_cli(["config", "unset", "memorySearch.remote"])


def write_env_template(to_env: bool = True) -> bool:
    """写入 .env 模板"""
    template = """# OpenClaw Embeddings API Keys
# 选择一项或多项（按你配置的 provider 使用）

# OpenAI embeddings
OPENAI_API_KEY=sk-...

# Gemini embeddings
GEMINI_API_KEY=...

# Voyage embeddings
VOYAGE_API_KEY=...

# 可选：自定义 OpenAI 兼容端点（仅当 memorySearch.remote.baseUrl 配置时）
# OPENAI_API_KEY=sk-...
"""

    # 确保模板目录存在
    tpl_dir = os.path.dirname(DEFAULT_ENV_TEMPLATE_PATH)
    if not os.path.exists(tpl_dir):
        os.makedirs(tpl_dir, exist_ok=True)

    try:
        with open(DEFAULT_ENV_TEMPLATE_PATH, "w") as f:
            f.write(template)
    except Exception as e:
        print(f"⚠️ 写入模板失败: {e}")
        return False

    if not to_env:
        return True

    # 写入 ~/.openclaw/.env
    try:
        if os.path.exists(DEFAULT_ENV_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{DEFAULT_ENV_PATH}.{timestamp}.bak"
            subprocess.run(["cp", DEFAULT_ENV_PATH, backup_path], check=False)
        with open(DEFAULT_ENV_PATH, "w") as f:
            f.write(template)
        return True
    except Exception as e:
        print(f"⚠️ 写入 .env 失败: {e}")
        return False


# ========== 扩展 OpenClawConfig 方法 ==========

def get_subagent_status(self) -> Dict:
    """获取当前子 Agent 策略状态"""
    defaults = self.data.get("agents", {}).get("defaults", {}).get("subagents", {})
    max_c = defaults.get("maxConcurrent", 8)
    
    allow_agents = []
    for agent in self.data.get("agents", {}).get("list", []):
        if agent.get("id") == "main":
            allow_agents = agent.get("subagents", {}).get("allowAgents", [])
    
    is_enabled = len(allow_agents) > 0
    return {
        "enabled": is_enabled,
        "allowAgents": allow_agents,
        "maxConcurrent": max_c
    }


def update_subagent_global(self, allow_agents: Optional[List] = None, max_concurrent: Optional[int] = None) -> bool:
    """更新子 Agent 全局策略"""
    success = True
    
    if allow_agents is not None:
        # 使用 CLI 设置 allowAgents
        allow_json = json.dumps(allow_agents)
        _, _, retcode = run_cli(["config", "set", "agents.list[0].subagents.allowAgents", allow_json, "--json"])
        if retcode != 0:
            success = False
    
    if max_concurrent is not None:
        # 使用 CLI 设置 maxConcurrent
        _, _, retcode = run_cli(["config", "set", "agents.defaults.subagents.maxConcurrent", str(max_concurrent), "--json"])
        if retcode != 0:
            success = False
    
    # 刷新本地缓存
    self.reload()
    return success


# 动态绑定方法
OpenClawConfig.get_subagent_status = get_subagent_status
OpenClawConfig.update_subagent_global = update_subagent_global

# 全局配置实例
config = OpenClawConfig()
