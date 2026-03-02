# EasyClaw 新版 Agent 创建方案

更新时间：2026-03-02

## 1. 背景与问题

当前 EasyClaw 的 Agent 创建逻辑，本质上是本地补配置：

- 向 `openclaw.json` 写入 `agents.list[]`
- 手动创建 workspace
- 手动补 `AGENTS.md`、`SOUL.md`、`IDENTITY.md` 等文件

这与 OpenClaw 官方的多 Agent 能力并不等价。

当前实现的主要问题：

1. 未走官方创建入口，缺少官方 wizard / bootstrap / identity 链路。
2. 将 workspace 绑定误当成 Agent 初始化完成，导致 auth、session、routing、persona 工作流缺失。
3. 使用了非官方字段 `security`，已确认会触发配置校验错误。
4. 多处逻辑仍然硬编码 `main`，不支持真实的多 Agent 状态读取。
5. “工作区限制”目前不是官方隔离模型，真实隔离应落在 per-agent `sandbox` 和 `tools`。

## 2. 官方结论

基于 OpenClaw 官方最新文档，固定 Agent 的正式模型是：

- 每个 Agent 有独立 `workspace`
- 每个 Agent 有独立 `agentDir`
- 每个 Agent 有独立 `sessions`
- 入站消息通过 `bindings` 路由到目标 Agent
- 身份与头像通过 `openclaw agents set-identity` 写入
- 首次运行时由官方 bootstrap 触发问答、写入 persona 文件

官方创建与管理入口：

```bash
openclaw agents list
openclaw agents add work --workspace ~/.openclaw/workspace-work
openclaw agents bindings
openclaw agents bind --agent work --bind telegram:ops
openclaw agents unbind --agent work --bind telegram:ops
openclaw agents set-identity --workspace ~/.openclaw/workspace-work --from-identity
openclaw agents set-identity --agent work --name "Work" --emoji "💼"
openclaw agents delete work
openclaw agent --agent work --message "hello"
```

## 3. 设计目标

新版 EasyClaw 的 Agent 创建服务，目标不是“自己造 Agent”，而是：

**作为 OpenClaw 官方多 Agent 能力的管理壳。**

也就是：

1. 优先调用官方 CLI 完成创建。
2. 仅在 CLI 不足时，补充官方兼容配置结构。
3. UI 负责收集参数、校验、可视化展示，不再手搓内部生命周期。
4. 隔离、身份、路由、模型、授权全部按官方概念拆开。

## 4. 新版能力边界

新版“Agent 创建服务”只负责固定 Agent，不负责 Sub-Agent。

区分如下：

- 固定 Agent：长期存在；有独立 workspace、auth、sessions、persona。
- Spawn/Sub-Agent：任务期临时派发；是运行时 session，不是新的人格实例。

因此：

- “创建 Agent”页面只管理固定 Agent。
- “派发管理”页面只管理 subagents。

## 5. 新版创建流程

### 5.1 标准流程

用户在 EasyClaw 中点击“新增 Agent”后，流程如下：

1. 输入 `agentId`
2. 选择或输入 workspace 路径
3. 选择初始化方式
4. 是否设置身份信息
5. 是否创建路由绑定
6. 是否设置隔离策略
7. 执行官方 CLI
8. 刷新本地状态

### 5.2 初始化方式

提供两种模式：

#### 模式 A：官方初始化（推荐）

- 调用 `openclaw agents add <id> --workspace <path>`
- 保持 bootstrap 可用
- 首次真正运行 Agent 时，由 OpenClaw 官方触发：
  - `AGENTS.md`
  - `BOOTSTRAP.md`
  - `IDENTITY.md`
  - `USER.md`
  - persona 问答

适用场景：

- 新建完整 Agent
- 希望官方首次问答工作流跑通

#### 模式 B：绑定已有工作区

- 要求 workspace 已存在
- 要求至少具备官方核心文件骨架
- 创建 Agent 后，允许执行：

```bash
openclaw agents set-identity --workspace <path> --from-identity
```

适用场景：

- 用户已有成熟 workspace
- 迁移已有 Agent
- 从模板复制出新 Agent

## 6. EasyClaw 菜单方案

### 6.1 一级菜单

`Agent 与工作区`

### 6.2 二级菜单

1. 新增 Agent
2. 查看 Agent 列表
3. 管理工作区绑定
4. 管理身份信息
5. 管理消息路由绑定
6. 管理隔离与工具权限
7. 删除 Agent
0. 返回

### 6.3 说明

- “新增 Agent”只做创建
- “工作区绑定”只做 workspace 变更或修复
- “身份信息”单独管理，避免创建流程过重
- “消息路由绑定”单独管理，避免与 workspace 混淆
- “隔离与工具权限”单独管理，避免把 sandbox 做成隐式附带逻辑

## 7. 每个菜单对应的官方实现

### 7.1 新增 Agent

优先调用：

```bash
openclaw agents add <agentId> --workspace <workspace>
```

若用户不显式输入 workspace，则按官方习惯默认：

- `~/.openclaw/workspace`
- `~/.openclaw/workspace-<agentId>`

### 7.2 身份信息

支持两类写入：

#### 从 `IDENTITY.md` 导入

```bash
openclaw agents set-identity --workspace <workspace> --from-identity
```

#### 直接填写表单写入

```bash
openclaw agents set-identity --agent <agentId> --name "<name>" --emoji "<emoji>"
```

后续可扩展：

- `theme`
- `avatar`

### 7.3 路由绑定

支持：

```bash
openclaw agents bindings
openclaw agents bind --agent <agentId> --bind telegram:ops
openclaw agents unbind --agent <agentId> --bind telegram:ops
openclaw agents unbind --agent <agentId> --all
```

UI 层建议拆成：

- 绑定某个 channel 默认账号
- 绑定某个 channel/accountId
- 绑定某个特定群 / peer
- 查看当前 bindings

### 7.4 删除 Agent

调用：

```bash
openclaw agents delete <agentId>
```

删除前应提示用户：

- 是否保留 workspace
- 是否保留 auth 与 sessions

若官方 CLI 不处理保留策略，则 EasyClaw 只做“逻辑删除 Agent 配置”，不擅自删用户文件。

## 8. 隔离模型设计

### 8.1 当前错误做法

当前 EasyClaw 通过自定义字段：

```json
security: {
  workspaceScope: "workspace-only",
  controlPlaneCapabilities: [...]
}
```

该字段不属于官方配置，已被官方校验拒绝。

### 8.2 官方正确做法

官方可用的能力，应抽象成三层，而不是让用户直接理解 JSON：

#### 1. 访问范围（workspaceAccess）

官方支持：

- `none`：不开放工作区文件访问
- `ro`：只读当前 Agent 的 workspace
- `rw`：读写当前 Agent 的 workspace

这是最适合转成用户语言的第一层设置。

#### 2. Sandbox

官方支持：

- `agents.list[].sandbox`

它决定这个 Agent 是否在更严格的执行边界中运行。

示例：

```json
{
  "sandbox": {
    "mode": "all",
    "scope": "agent"
  }
}
```

#### 3. Tools profile + allow/deny

官方支持：

- `agents.list[].tools.profile`
- `agents.list[].tools.allow`
- `agents.list[].tools.deny`

其中 `profile` 可优先使用官方预设：

- `minimal`
- `messaging`
- `coding`
- `full`

只有在用户需要细调时，再暴露 `allow/deny`。

### 8.3 EasyClaw 的用户语言设计

这里不应该让用户直接看：

- `sandbox`
- `tools.allow`
- `tools.deny`
- 路径白名单

而应改成更直观的两个概念：

1. 文件访问范围
2. 能力级别

即用户看到的是：

- 这个 Agent 能不能看到自己的 workspace
- 是只读还是可改
- 能不能执行命令
- 能不能发消息/调其他 Agent

底层再映射到官方 `workspaceAccess + sandbox + tools`。

### 8.4 EasyClaw 推荐预设

提供 5 套预设，尽量覆盖大多数场景。

#### 预设 A：完全开放

用户理解：

- 可读写自己的 workspace
- 可执行命令
- 可使用完整工具

官方映射：

- `workspaceAccess: rw`
- `sandbox: off`
- `tools.profile: full`

适用场景：

- 主 Agent
- 本地 coding Agent

#### 预设 B：只读分析

用户理解：

- 只能查看自己的 workspace
- 不能改文件
- 不能执行命令

官方映射：

- `workspaceAccess: ro`
- `sandbox: { mode: "all", scope: "agent" }`
- `tools.profile: minimal`
- `tools.deny: ["write", "edit", "apply_patch", "exec", "process"]`

适用场景：

- 审计 Agent
- Review Agent
- 只读知识整理 Agent

#### 预设 C：安全执行

用户理解：

- 可读自己的 workspace
- 可以运行命令
- 默认不能改文件

官方映射：

- `workspaceAccess: ro`
- `sandbox: { mode: "all", scope: "agent" }`
- `tools.profile: coding`
- `tools.deny: ["write", "edit", "apply_patch"]`

适用场景：

- 检查类 Agent
- 测试 Agent
- 构建/诊断 Agent

#### 预设 D：工作区协作

用户理解：

- 只能操作自己的 workspace
- 可读写
- 可做有限的开发修改

官方映射：

- `workspaceAccess: rw`
- `sandbox: { mode: "all", scope: "agent" }`
- `tools.profile: coding`

适用场景：

- 某个独立项目的专属 Agent
- 需要隔离人设与代码上下文的固定 Agent

#### 预设 E：通讯协调

用户理解：

- 不看文件或几乎不看文件
- 主要负责消息转发、调度、协作

官方映射：

- `workspaceAccess: none`
- `sandbox: off`
- `tools.profile: messaging`

适用场景：

- 调度 Agent
- 群聊分流 Agent
- 协作中控 Agent

### 8.5 高级模式

默认不展示原始 `allow/deny`。

只有在用户手动点开“高级模式”后，才允许：

1. 微调工具白名单/黑名单
2. 微调 sandbox 细节
3. 查看最终写入的官方配置 JSON

这样可以同时满足两类用户：

- 小白用户：选“预设”即可
- 高级用户：仍可看到官方底层配置

### 8.6 UI 呈现建议

在 EasyClaw 中，“隔离与权限”页面建议改成：

1. 访问范围
   - 不访问工作区
   - 只读自己的工作区
   - 读写自己的工作区

2. 能力级别
   - 完全开放
   - 只读分析
   - 安全执行
   - 工作区协作
   - 通讯协调

3. 高级模式
   - 查看官方映射
   - 手动微调 tools / sandbox

### 8.7 关键原则

“仅可见自己的 workspace” 这种表达应保留在 UI。

实现时不让用户自己填路径，而是直接使用：

- 当前 Agent 的 `workspace`

作为默认作用域。

也就是说：

- 用户选的是语义
- EasyClaw 负责把这个语义映射到官方权限模型
- 用户不直接接触路径细节，除非主动进入高级模式

## 9. 模型与授权策略

### 9.1 Auth

官方行为：

- 每个 Agent 使用自己的 `agentDir`
- auth 文件位于：

```text
~/.openclaw/agents/<agentId>/agent/auth-profiles.json
```

因此：

- 不再默认共用 `main` 的 auth
- 如需共享授权，应明确提供“复制授权配置到该 Agent”的操作

### 9.2 模型

模型策略分三层：

1. 全局默认
2. Agent 覆盖
3. Sub-Agent 覆盖

Agent 创建页不再承担完整模型配置，只做“创建后可跳转到模型策略页”。

## 10. Agent 间协作设计

### 10.1 固定 Agent 协作

推荐基于官方：

```bash
openclaw agent --agent <id> --message "..."
```

后续 EasyClaw 可做“从 A 向 B 发送测试消息”按钮，用于验证：

- Agent 是否可运行
- workspace 是否生效
- identity 是否生效
- 模型/授权是否正常

### 10.2 Sub-Agent 协作

继续沿用官方 `subagents` 能力，不纳入“新建 Agent”服务。

## 11. 数据读取与状态刷新

当前多处逻辑硬编码 `main`，必须改造为按 `agentId` 读取。

需要改的类别：

1. `auth-profiles.json` 读取
2. `models.json` 读取
3. 资产大盘统计
4. Agent 列表页状态回显

原则：

- 以 `agents.list[].agentDir` 为准
- 若未设置 `agentDir`，按官方默认路径推导
- 不再写死 `/root/.openclaw/agents/main/agent/...`

## 12. 与当前代码的冲突点

当前需要淘汰或重构的核心逻辑：

1. `tui/routing.py` 中本地拼装 Agent 的逻辑
2. 手写模板 `_ensure_workspace_scaffold()`
3. 自定义 `security` 写入
4. 所有硬编码 `main` 的状态读取逻辑

### 12.1 重点问题代码

- `tui/routing.py:256`
  - 手工创建 bootstrap/persona 文件，不等于官方 bootstrap
- `tui/routing.py:287`
  - 直接 upsert `agents.list[]`
- `tui/routing.py:318`
  - 写入非官方 `security`
- `cmd/status.py:37`
  - auth 路径硬编码 `main`
- `core/datasource.py:10`
  - models 路径硬编码 `main`
- `install.sh:157`
  - 默认 auth profile 路径硬编码 `main`

## 13. 推荐实施顺序

### Phase 1：先修正数据模型

目标：

- 删除 `security`
- 引入 per-agent `sandbox` / `tools`
- 所有读取逻辑改为按 `agentId`

### Phase 2：替换创建链路

目标：

- “新增 Agent”改为调用 `openclaw agents add`
- workspace 绑定改为“官方创建后补充修复”
- identity 管理独立出来

### Phase 3：补齐 bindings 管理

目标：

- 支持 `list/bind/unbind`
- 将路由管理从“workspace 绑定”中分离

### Phase 4：补齐验证工具

目标：

- `openclaw agent --agent <id> --message ...` 冒烟测试
- Agent 状态页增加：
  - workspace
  - identity
  - auth 状态
  - routing bindings
  - sandbox/profile

## 14. EasyClaw 最终产品定义

新版 EasyClaw 中，“创建 Agent”不再意味着：

- 创建一个目录
- 填几份模板
- 改几段 JSON

而是意味着：

**通过官方机制创建一个完整、可运行、可绑定、可授权、可隔离的固定 Agent。**

## 15. 结论

新版实现原则：

1. 创建 Agent：优先官方 CLI
2. persona/identity：优先官方 `set-identity` 与 bootstrap
3. 路由：优先官方 bindings
4. 隔离：优先官方 sandbox + tools
5. 协作：固定 Agent 用 `openclaw agent`，临时派发用 `subagents`
6. EasyClaw 自身只做管理壳，不再伪实现 Agent 生命周期

## 参考资料

- OpenClaw CLI `agents`
  - https://docs.openclaw.ai/cli/agents
- OpenClaw Multi-Agent Routing
  - https://docs.openclaw.ai/concepts/multi-agent
- OpenClaw Agent Bootstrapping
  - https://docs.openclaw.ai/start/bootstrapping
- OpenClaw Agent Workspace
  - https://docs.openclaw.ai/concepts/agent-workspace
- OpenClaw Configuration Reference
  - https://docs.openclaw.ai/gateway/configuration-reference
- OpenClaw Multi-Agent Sandbox & Tools
  - https://docs.openclaw.ai/tools/multi-agent-sandbox-tools
- OpenClaw Agent Send
  - https://docs.openclaw.ai/tools/agent-send
- OpenClaw Sub-Agents
  - https://docs.openclaw.ai/tools/subagents
