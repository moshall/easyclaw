# Changelog

## 0.1.6 - 2026-03-11

### Fixed
- 修复 provider 配置写入后未同步到各 Agent runtime `models.json` 的问题。
- 修复 `openai-responses` 等自定义 provider 在 Agent 模型选择中不可见的问题。

### Changed
- `set_provider_config` 统一走 `set_models_providers`，避免绕过同步链路。
- `set_models_providers` 增加全 Agent 同步流程：优先调用官方 CLI 刷新，失败时回退文件级合并。

### Verified
- 相关回归测试通过（含 provider/runtime 同步路径）。

## 0.1.5 - 2026-03-11

### Added
- 支持 OpenAI Responses 输入模式精细配置（`auto/array/string`），并可按需探测网关兼容性。
- Web 端新增/增强 Responses 协议配置入口（自定义 provider 创建后可直接管理输入模式）。

### Changed
- 子菜单执行统一加固异常兜底，避免异常冒泡导致整个 TUI 直接退出。
- Agent 权限管理增强，支持 `tools.profile` 与目录/功能细粒度策略联动配置。
- Docker 场景下权限预设与运行环境识别逻辑进一步统一，减少误配置。

### Fixed
- 修复“添加官方服务商时误走自定义服务商流程”的问题。
- 修复多处菜单分支的异常输入处理不一致问题（含 `Ctrl+C` / `Ctrl+D` 退出路径）。

### Verified
- Debian 12 全新主机完成 Linux + Docker 回归验证。
- `OpenClaw 2026.2.26` 与 `2026.3.8` 双版本快速兼容回归通过。
- 自动化测试：25 项单测通过。
