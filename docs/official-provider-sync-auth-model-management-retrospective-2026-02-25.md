# 官方供应商同步、授权与模型管理修复复盘（2026-02-25）

## 1. 背景与目标

本轮修复目标：

1. 官方供应商（重点是 `openrouter`）能自动对齐 OpenClaw 最新支持能力。
2. 授权流程走官方实现，避免 EasyClaw 自己维护脆弱分支逻辑。
3. 模型管理（拉取、搜索、激活、取消、手动添加）在 TUI 中稳定可用。
4. 把踩坑经验沉淀为可复用规范，避免后续回归。

---

## 2. 核心问题与根因

### 2.1 官方 API Key 授权“写入失败（config set failed）”

现象：

- TUI 输入 API Key 后失败，提示 `config set failed`。

根因：

- 旧实现把官方 provider 当成自定义 provider，直接写 `models.providers`。
- OpenClaw 对部分 provider（如 `openrouter`）的 schema 有约束（例如 `baseUrl`），导致写入被拒绝。

结论：

- 官方 provider 不能优先走 `models.providers` 直写，必须走 OpenClaw 官方 auth/onboard 流程。

---

### 2.2 授权成功但“账号数=0”

现象：

- 配置成功后，服务商管理仍显示账号为 0。

根因：

- 账号统计只看 `openclaw.json.auth.profiles`，没并入 `auth-profiles.json`（官方实际凭据存储）。

结论：

- 账号状态需要双源合并并去重。

---

### 2.3 模型列表只显示 `openrouter/auto`

现象：

- 进入模型管理时只有 router 占位模型，没有真实模型列表。

根因：

- 数据源优先级错误：先读 `models.json`（缓存），而该文件在某些场景只含 `auto`。

结论：

- 官方模型列表应优先走 `openclaw models list --all --provider ... --json`。

---

### 2.4 模型激活“看起来成功但实际没生效”

现象：

- 选择后回车，出现失败或无变化。

根因：

1. 写入路径把模型 key 作为带引号下标，OpenClaw 解析后把引号写进真实 key（脏 key）。
2. UI 只打印“失败数量”，不打印失败原因，难以定位。
3. 回车逻辑在某些选择状态下不符合直觉。

结论：

- key path 需规范化；激活失败要透出 `key: reason`；回车行为要和用户直觉一致。

---

### 2.5 资源库出现重复服务商：`'openrouter` + `openrouter`

现象：

- 服务商列表出现两个近似 provider。

根因：

- 历史脏模型 key（如 `'openrouter/test-b'`）在 provider 分组时被识别成新 provider。

结论：

- 启动时必须做 key 归一化清理，provider 名分组也要做 normalize。

---

## 3. 已实现修复（摘要）

### 3.1 官方授权路径对齐

策略：

- 官方 provider（`openrouter` 等）API Key 写入改为调用：
  - `openclaw onboard --non-interactive --accept-risk --auth-choice ...`
- 自定义 provider 保留 `models.providers` 配置写入。

效果：

- 避免 schema 约束导致的写入失败，和 OpenClaw 官方行为一致。

---

### 3.2 账号统计修复

策略：

- 合并读取：
  - `openclaw.json.auth.profiles`
  - `auth-profiles.json`
- 同 profileId 去重合并。

效果：

- 授权成功后账号数正确展示。

---

### 3.3 官方模型列表数据源修复

策略：

- `get_official_models(provider)` 优先 CLI 实时拉取；
- CLI 失败才 fallback `models.json`。

效果：

- OpenRouter 可展示完整模型列表（不再仅 `auto`）。

---

### 3.4 激活链路增强

策略：

1. 写路径改为不引入引号污染。
2. 增加 direct-edit 兜底（CLI 写/读边界异常时仍可激活）。
3. 激活失败显示具体明细（`key: reason`）。

效果：

- 激活稳定性提升，可观测性提升。

---

### 3.5 交互行为修复

策略：

- 若用户未显式调整选择集，`Enter` 默认带上当前光标模型；
- 官方 provider 的 `m 手动添加` 改为直接激活 `provider/model`，避免写 `models.providers` 的 schema 陷阱。

效果：

- “移动到目标模型后直接回车”符合直觉；
- 手动添加在官方 provider 可用。

---

### 3.6 脏数据清理与防再发

策略：

- 增强模型 key 清理（单引号/双引号/残留引号）；
- provider 归一化时统一 strip 引号。

效果：

- 消除 `'openrouter` 重复 provider 问题；
- 后续分组稳定。

---

## 4. 回归测试覆盖

已覆盖的关键场景：

1. 官方模型列表加载。
2. 搜索过滤 + 激活。
3. 单模型激活（Enter）。
4. 多模型勾选激活。
5. 取消激活。
6. 手动添加模型（官方 provider）。
7. 账号数统计（官方凭据文件）。
8. 脏 key 清理与 provider 归一化。

容器内端到端回归结果：

- `openrouter` 模型管理 6/6 场景通过。

---

## 5. 防回归规范（后续开发必须遵守）

### 5.1 官方 vs 自定义 provider 边界

1. 官方 provider：授权必须优先官方流程（onboard/auth）。
2. 自定义 provider：才允许以 `models.providers` 为主配置源。

### 5.2 数据源优先级

1. 官方模型目录：`models list --all --provider ...`（权威）。
2. `models.json` 仅作为离线 fallback。
3. `models.providers.*.models` 仅自定义 provider 使用。

### 5.3 激活链路约束

1. 每次激活后必须 read-back 校验。
2. 若 CLI 路径异常，必须有文件级兜底。
3. UI 失败提示必须包含 `key + reason`。

### 5.4 启动自愈

1. 进入资源库前执行 key 清理（引号污染）。
2. provider 分组统一 normalize。

---

## 6. 快速验收命令（建议发布前执行）

```bash
# 1) 运行核心回归测试
docker exec easyclaw-web bash -lc 'cd /easyclaw && python3 -m unittest -v \
  test_inventory_provider_auth.py \
  test_write_engine_api_key.py \
  test_datasource_normalize.py \
  test_profiles_by_provider.py'

# 2) 校验 openrouter 模型目录是否完整（不应只有 auto）
docker exec easyclaw-web bash -lc 'openclaw models list --all --provider openrouter --json | head -c 600'

# 3) 校验配置中不存在带引号污染 key
docker exec easyclaw-web bash -lc "python3 - <<'PY'
import json
d=json.load(open('/root/.openclaw/openclaw.json'))
models=((d.get('agents') or {}).get('defaults') or {}).get('models') or {}
bad=[k for k in models if k.startswith(\"'\") or k.startswith('\"')]
print('bad_keys', bad[:20], 'count=', len(bad))
PY"
```

---

## 7. 后续可继续优化的方向

1. 把官方 auth-choice / flag 映射进一步动态化（减少静态表维护成本）。
2. 模型管理增加“已激活变更摘要”与“最近操作日志”。
3. 为 TUI 增加无交互回归脚本入口，便于 CI 自动验收。

