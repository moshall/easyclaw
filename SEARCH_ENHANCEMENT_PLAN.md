# EasyClaw 搜索配置增强方案

## 调研发现

### 当前 OpenClaw 搜索配置结构
```json
"tools": {
  "web": {
    "search": {
      "provider": "brave",
      "perplexity": {
        "baseUrl": "https://openrouter.ai/api/v1",
        "model": "perplexity/sonar-pro"
      }
    }
  }
}
```

---

## 增强目标

### 1. 拆分成搜索服务（3 个官方支持的）
- Brave Search
- Perplexity
- （用户提到的第 3 个，待确认）

### 2. 统一的搜索服务管理
- 官方搜索服务配置
- 第三方搜索服务配置（OpenAI 兼容）
- Base URL / API Key / Model 配置

### 3. 自动对齐 OpenClaw 官方
- 跟随 OpenClaw 官方配置结构
- 自动检测官方支持的搜索服务

---

## 实现方案

### 阶段 1：调研
- [ ] 确认 OpenClaw 最新支持的 3 个官方搜索服务
- [ ] 查看 OpenClaw 官方配置向导的搜索部分

### 阶段 2：实现增强版 `tui/tools.py`
- [ ] 拆分成"搜索服务"主菜单
- [ ] 官方搜索服务配置（Brave/Perplexity/第3个）
- [ ] 第三方搜索服务配置（自定义 Base URL/API Key/Model）
- [ ] 默认搜索 provider 选择

### 阶段 3：测试和对齐
- [ ] 测试所有功能
- [ ] 确保配置结构和 OpenClaw 官方对齐
