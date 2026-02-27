# Official Provider RUNBOOK（OpenRouter 优先）

## 1. 目标

当官方供应商（如 `openrouter`）出现“拉不到模型、授权后账号数异常、模型激活失败”时，使用本手册快速定位与修复。

---

## 2. 快速原则（必须遵守）

1. 官方 provider 授权走官方流程（`onboard/auth`），不要优先写 `models.providers`。
2. 官方模型列表优先 `openclaw models list --all --provider <id> --json`。
3. 激活后必须 read-back 校验；失败时输出 `key: reason`。
4. 启动前清理脏 key（引号污染）并统一 provider 名。

---

## 3. 常见故障与一步定位

### 3.1 API Key 写入失败（`config set failed`）

原因：
- 误走 `models.providers` 直写，触发 schema（如 `baseUrl`）约束。

处理：
- 改走官方 `onboard --non-interactive --auth-choice ...`。

---

### 3.2 授权成功但账号数=0

原因：
- 只看了 `openclaw.json.auth.profiles`，没读 `auth-profiles.json`。

处理：
- 合并两个来源并按 profileId 去重。

---

### 3.3 模型管理只有 `openrouter/auto`

原因：
- 读了缓存 `models.json`（不完整）。

处理：
- 优先 CLI 实时列表，失败再 fallback 缓存。

---

### 3.4 选中模型后回车没激活

原因：
- Enter 语义与选择集不一致，或激活写入链路读回失败。

处理：
1. Enter 默认包含当前光标模型（当用户未显式变更选择集）。
2. 激活失败打印 `key: reason`。
3. 写入链路保留 direct-edit 兜底。

---

### 3.5 出现两个 provider：`'openrouter` / `openrouter`

原因：
- 历史模型 key 带引号残留。

处理：
- 运行 key 清理并 normalize provider 名。

---

## 4. 日常排查命令（容器：`easyclaw-web`）

```bash
# A. 核心回归
docker exec easyclaw-web bash -lc 'cd /easyclaw && python3 -m unittest -v \
  test_inventory_provider_auth.py \
  test_write_engine_api_key.py \
  test_datasource_normalize.py \
  test_profiles_by_provider.py'

# B. 官方模型目录是否完整
docker exec easyclaw-web bash -lc \
  'openclaw models list --all --provider openrouter --json | head -c 800'

# C. 账号来源是否正常
docker exec easyclaw-web bash -lc "python3 - <<'PY'
import json
cfg=json.load(open('/root/.openclaw/openclaw.json'))
print('auth.profiles=', list(((cfg.get('auth') or {}).get('profiles') or {}).keys())[:10])
try:
  store=json.load(open('/root/.openclaw/agents/main/agent/auth-profiles.json'))
  print('auth-profiles=', list((store.get('profiles') or {}).keys())[:10])
except Exception as e:
  print('auth-profiles error=', e)
PY"

# D. 脏 key 检测（引号污染）
docker exec easyclaw-web bash -lc "python3 - <<'PY'
import json
d=json.load(open('/root/.openclaw/openclaw.json'))
models=((d.get('agents') or {}).get('defaults') or {}).get('models') or {}
bad=[k for k in models if k.startswith(\"'\") or k.startswith('\"')]
print('bad_keys_count=', len(bad))
print('sample=', bad[:20])
PY"
```

---

## 5. 变更验收清单（发布前）

1. OpenRouter 模型数 > 50（不是只有 `auto`）。
2. 授权后资源库账号数 > 0。
3. 激活一个 `:free` 模型后可在 `agents.defaults.models` 看到无引号 key。
4. 资源库 provider 列表不出现 `'openrouter` 这类脏项。
5. 模型激活失败时，UI 必须显示具体 `key: reason`。

---

## 6. 紧急回滚策略

1. 优先回滚 TUI 层改动（`tui/inventory.py`）保持可用性。
2. 保留 `core/write_engine.py` 的 key/path 修复（这是基础稳定性保障）。
3. 若出现统计异常，保留 `core/__init__.py` 的 profile 双源合并逻辑。

