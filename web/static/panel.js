(function () {
  const state = {
    token: "",
    data: null,
    providerOptions: [],
  };

  const $ = (id) => document.getElementById(id);

  function parseTokenFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return (params.get("token") || "").trim();
  }

  function getSavedToken() {
    return (localStorage.getItem("easyclaw_web_token") || "").trim();
  }

  function setSavedToken(token) {
    localStorage.setItem("easyclaw_web_token", token);
  }

  function showNotice(msg, isError = false) {
    const notice = $("notice");
    notice.className = "notice " + (isError ? "err" : "ok");
    notice.textContent = msg;
    window.setTimeout(() => {
      notice.className = "notice";
      notice.textContent = "";
    }, 3500);
  }

  async function api(path, options = {}) {
    if (!state.token) {
      throw new Error("未设置 X-Claw-Token");
    }
    const headers = Object.assign({}, options.headers || {}, {
      "X-Claw-Token": state.token,
    });
    if (!(options.body instanceof FormData) && !headers["Content-Type"] && options.body) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, Object.assign({}, options, { headers }));
    const text = await res.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch (_) {
      payload = { raw: text };
    }
    if (!res.ok) {
      throw new Error(payload.detail || payload.error || payload.raw || "请求失败");
    }
    return payload;
  }

  function parseCsv(value) {
    return (value || "")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  }

  function selectedMultiValues(selectId) {
    return Array.from($(selectId).selectedOptions || []).map((o) => o.value).filter(Boolean);
  }

  function fillSelect(select, options, valueField = "value", labelField = "label") {
    select.innerHTML = "";
    options.forEach((opt) => {
      const el = document.createElement("option");
      el.value = opt[valueField];
      el.textContent = opt[labelField];
      select.appendChild(el);
    });
  }

  function fillModelSingleSelect(selectId, selectedValue, allowEmpty = true) {
    const select = $(selectId);
    const options = [{ value: "", label: "(未设置)" }];
    getFilteredModels().forEach((m) => {
      const flag = m.available ? "✅" : "❌";
      options.push({ value: m.key, label: `${flag} ${m.provider} / ${m.name}` });
    });
    if (!allowEmpty) {
      options.shift();
    }
    fillSelect(select, options);
    select.value = selectedValue || "";
  }

  function fillModelMultiSelect(selectId, selectedValues) {
    const select = $(selectId);
    const selectedSet = new Set((selectedValues || []).filter(Boolean));
    select.innerHTML = "";
    getFilteredModels().forEach((m) => {
      const el = document.createElement("option");
      el.value = m.key;
      const flag = m.available ? "✅" : "❌";
      el.textContent = `${flag} ${m.provider} / ${m.name}`;
      el.selected = selectedSet.has(m.key);
      select.appendChild(el);
    });
  }

  function updateNav(targetId) {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.target === targetId);
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === targetId);
    });
  }

  function getFilteredModels() {
    const data = state.data;
    if (!data) return [];
    const provider = ($("modelProviderFilter").value || "").trim();
    const keyword = ($("modelKeywordFilter").value || "").trim().toLowerCase();

    let rows = (data.modelCatalog.all || []).slice();
    if (provider) {
      rows = rows.filter((m) => m.provider === provider);
    }
    if (keyword) {
      rows = rows.filter((m) => `${m.key} ${m.name} ${m.provider}`.toLowerCase().includes(keyword));
    }
    return rows;
  }

  function fillProviderFilterOptions() {
    const cur = $("modelProviderFilter").value;
    const providers = ((state.data.modelCatalog || {}).providers || []).slice();
    const opts = [{ value: "", label: "(全部服务商)" }].concat(providers.map((p) => ({ value: p, label: p })));
    fillSelect($("modelProviderFilter"), opts);
    $("modelProviderFilter").value = providers.includes(cur) ? cur : "";
  }

  function renderInventory() {
    const invBody = $("inventoryRows");
    invBody.innerHTML = "";
    const rows = state.data.inventory.rows || [];
    if (!rows.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="6" class="muted">暂无数据</td>`;
      invBody.appendChild(tr);
      return;
    }
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.provider}</td><td>${row.authCount}</td><td>${row.keyCount}</td><td>${row.modelCount}</td><td>${row.api || "-"}</td><td class="mono">${row.baseUrl || "-"}</td>`;
      invBody.appendChild(tr);
    });
  }

  function renderHealth() {
    const runtime = state.data.runtime || {};
    $("runtimeConfigPath").textContent = runtime.configPath || "-";
    $("runtimeSandbox").textContent = runtime.sandboxEnabled ? "⚠️ 已开启（读 sandbox）" : "✅ 关闭（读真实配置）";
    $("runtimeTokenHint").textContent = runtime.webTokenHint || "-";

    $("dashPrimary").textContent = state.data.globalModel.primary || "(未设置)";
    $("dashFallbacks").textContent = (state.data.globalModel.fallbacks || []).length
      ? state.data.globalModel.fallbacks.join(" -> ")
      : "(未设置)";

    const adapter = state.data.search.adapterConfig || {};
    const searchChain = [adapter.primarySource || "(未设置)"];
    if (Array.isArray(adapter.fallbackSources) && adapter.fallbackSources.length) {
      searchChain.push(...adapter.fallbackSources);
    }
    $("dashSearchProvider").textContent = state.data.search.defaultProvider || "(未设置)";
    $("dashSearchChain").textContent = searchChain.join(" -> ");

    const authRows = $("authRows");
    authRows.innerHTML = "";
    const authProviders = (((state.data.health || {}).status || {}).auth || {}).providers || [];
    if (!authProviders.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4" class="muted">加载中或暂无官方授权</td>`;
      authRows.appendChild(tr);
    } else {
      authProviders.forEach((p) => {
        const tr = document.createElement("tr");
        const provider = p.provider || "unknown";
        const effective = (p.effective || {}).kind || "unknown";
        const count = (p.profiles || {}).count || 0;
        const labels = ((p.profiles || {}).labels || []).join(", ");
        tr.innerHTML = `<td>${provider}</td><td>${effective}</td><td>${count}</td><td>${labels || "-"}</td>`;
        authRows.appendChild(tr);
      });
    }

    const activeRows = $("activeModelRows");
    activeRows.innerHTML = "";
    const activeModels = state.data.health.activeModels || [];
    if (!activeModels.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="3" class="muted">加载中或暂无已激活模型</td>`;
      activeRows.appendChild(tr);
    } else {
      activeModels.forEach((m) => {
        const tr = document.createElement("tr");
        let availText = "?";
        if (m.available === true) availText = "✅ 可用";
        if (m.available === false) availText = "❌ 不可用/下架";
        tr.innerHTML = `<td>${m.isDefault ? "⭐" : ""}</td><td>${m.key}</td><td>${availText}</td>`;
        activeRows.appendChild(tr);
      });
    }

    const usage = (state.data.health || {}).usage || {};
    if (usage.code === 0 && usage.raw) {
      $("usageRaw").textContent = usage.raw;
    } else if (!usage.error) {
      $("usageRaw").textContent = "(加载中...)";
    } else {
      $("usageRaw").textContent = usage.error || "(未获取到用量信息)";
    }
  }

  function renderAgentRows() {
    const agentBody = $("agentRows");
    agentBody.innerHTML = "";
    const rows = state.data.agents || [];
    if (!rows.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4" class="muted">暂无 Agent（可在下方新增）</td>`;
      agentBody.appendChild(tr);
      return;
    }
    rows.forEach((agent) => {
      const tr = document.createElement("tr");
      const modelPolicy = agent.model.overridden ? "独立模型" : "跟随全局";
      tr.innerHTML = `<td>${agent.id}</td><td>${agent.workspace || "(未绑定)"}</td><td>${agent.security.workspaceOnly ? "仅工作区" : "全部"}</td><td>${modelPolicy}</td>`;
      agentBody.appendChild(tr);
    });
  }

  function renderAgentSelectors() {
    const agentOpts = (state.data.agents || []).map((a) => ({ value: a.id, label: a.id }));
    if (!agentOpts.length) {
      agentOpts.push({ value: "", label: "(暂无 Agent)" });
    }
    fillSelect($("agentModelId"), agentOpts);
    fillSelect($("agentOpsId"), agentOpts);
    fillSelect($("dispatchAgentId"), agentOpts);
  }

  function syncAgentDrivenForms() {
    const aid = $("agentModelId").value;
    const agent = (state.data.agents || []).find((x) => x.id === aid);
    fillModelSingleSelect("agentPrimarySelect", agent ? agent.model.primary : "", true);
    fillModelMultiSelect("agentFallbacksSelect", agent ? agent.model.fallbacks : []);

    const aidOps = $("agentOpsId").value;
    const agentOps = (state.data.agents || []).find((x) => x.id === aidOps);
    if (agentOps) {
      $("bindWorkspaceInput").value = agentOps.workspace || "";
      $("workspaceOnlySwitch").checked = !!agentOps.security.workspaceOnly;
      $("controlCapsInput").value = (agentOps.security.controlPlaneCapabilities || []).join(",");
    }

    const aidDispatch = $("dispatchAgentId").value;
    const agentDispatch = (state.data.agents || []).find((x) => x.id === aidDispatch);
    if (agentDispatch) {
      $("dispatchEnabled").checked = !!agentDispatch.subagents.enabled;
      $("dispatchAllowAgents").value = (agentDispatch.subagents.allowAgents || []).join(",");
      $("dispatchMaxConcurrent").value = agentDispatch.subagents.maxConcurrent || "";
    }
  }

  function renderPolicySelectors() {
    fillModelSingleSelect("globalPrimarySelect", (state.data.globalModel || {}).primary || "", true);
    fillModelMultiSelect("globalFallbacksSelect", (state.data.globalModel || {}).fallbacks || []);

    fillModelSingleSelect("spawnPrimarySelect", (state.data.spawnModel || {}).primary || "", true);
    fillModelMultiSelect("spawnFallbacksSelect", (state.data.spawnModel || {}).fallbacks || []);

    syncAgentDrivenForms();
  }

  function renderModelPool() {
    const activeSet = new Set((state.data.modelCatalog.activeKeys || []).filter(Boolean));
    const rows = getFilteredModels().slice(0, 400);
    const body = $("modelPoolRows");
    body.innerHTML = "";

    if (!rows.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="5" class="muted">加载中或未命中筛选条件</td>`;
      body.appendChild(tr);
      return;
    }

    rows.forEach((m) => {
      const tr = document.createElement("tr");
      const available = m.available ? "✅" : "❌";
      const active = activeSet.has(m.key);
      tr.innerHTML = `
        <td>${m.provider}</td>
        <td class="mono">${m.key}</td>
        <td>${available}</td>
        <td>${active ? "✅ 已激活" : "⬜ 未激活"}</td>
        <td>
          <button class="btn tiny subtle" data-action="set-global" data-key="${m.key}">设为主模型</button>
          <button class="btn tiny ${active ? "danger" : ""}" data-action="toggle-model" data-key="${m.key}" data-active="${active ? "1" : "0"}">${active ? "移除" : "激活"}</button>
        </td>
      `;
      body.appendChild(tr);
    });
  }

  function renderProviderApiManager() {
    const options = (state.providerOptions || []).length
      ? state.providerOptions
      : (state.data.officialProviderOptions || []);
    const seen = new Set();
    const officialOpts = [];
    options.forEach((o) => {
      const provider = o.providerId || o.id;
      if (!provider || seen.has(provider)) return;
      seen.add(provider);
      officialOpts.push({
        value: provider,
        label: `${provider} · ${o.label || o.id}`,
      });
    });
    if (!officialOpts.length) {
      officialOpts.push({ value: "", label: "(暂无可配置官方服务商)" });
    }
    fillSelect($("officialProviderForApi"), officialOpts);

    const selectedProtocol = $("customProviderProtocol").value;
    const protocolRaw = (state.data.providerProtocols || []).slice();
    const preferred = ["openai-completions", "anthropic-completions", "openai-chat", "anthropic-messages", "gemini-v1beta"];
    const protocolSorted = preferred.filter((x) => protocolRaw.includes(x)).concat(protocolRaw.filter((x) => !preferred.includes(x)));
    const protocolOpts = protocolSorted.map((p) => ({ value: p, label: p }));
    fillSelect($("customProviderProtocol"), protocolOpts);
    if (selectedProtocol && protocolSorted.includes(selectedProtocol)) {
      $("customProviderProtocol").value = selectedProtocol;
    } else if (protocolSorted.includes("openai-completions")) {
      $("customProviderProtocol").value = "openai-completions";
    }

    const tableBody = $("providerManageRows");
    tableBody.innerHTML = "";
    const rows = state.data.inventory.rows || [];
    if (!rows.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="5" class="muted">暂无服务商</td>`;
      tableBody.appendChild(tr);
      return;
    }
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.provider}</td>
        <td>${row.authCount}</td>
        <td>${row.keyCount}</td>
        <td>${row.modelCount}</td>
        <td>
          <button class="btn tiny subtle" data-action="discover-provider" data-provider="${row.provider}">发现模型</button>
          <button class="btn tiny danger" data-action="delete-provider" data-provider="${row.provider}">删除</button>
        </td>
      `;
      tableBody.appendChild(tr);
    });
  }

  function renderSearchForms() {
    const officialProviders = (state.data.search.officialSupported || []).map((p) => ({
      value: p,
      label: `${p}${(state.data.search.officialConfigured || []).includes(p) ? " (已配置)" : ""}`,
    }));
    fillSelect($("officialSearchProvider"), officialProviders);

    const adapterProviders = Object.keys((state.data.search.adapterConfig || {}).providers || {}).map((p) => ({ value: p, label: p }));
    fillSelect($("adapterProvider"), adapterProviders);

    const sourceOpts = [{ value: "", label: "(不设置)" }].concat(
      (state.data.search.availableUnifiedSources || []).map((s) => ({ value: s, label: s }))
    );
    fillSelect($("searchPrimarySource"), sourceOpts);

    const adapter = state.data.search.adapterConfig || {};
    $("searchPrimarySource").value = adapter.primarySource || "";
    $("searchFallbackSources").value = (adapter.fallbackSources || []).join(",");

    syncAdapterFields();
  }

  function syncAdapterFields() {
    const provider = $("adapterProvider").value;
    const cfg = (((state.data || {}).search || {}).adapterConfig || {}).providers || {};
    const p = cfg[provider] || {};
    $("adapterApiKey").value = p.apiKey || "";
    $("adapterBaseUrl").value = p.baseUrl || "";
    $("adapterModel").value = p.model || "";
    $("adapterTopK").value = p.topK || 5;
    $("adapterCooldown").value = p.cooldownSeconds || 60;
    $("adapterEnabled").checked = !!p.enabled;
  }

  function renderAll() {
    if (!state.data) return;
    fillProviderFilterOptions();
    renderHealth();
    renderInventory();
    renderAgentRows();
    renderAgentSelectors();
    renderPolicySelectors();
    renderModelPool();
    renderProviderApiManager();
    renderSearchForms();
  }

  async function refreshState() {
    const oldCatalog = state.data && state.data.modelCatalog ? state.data.modelCatalog : null;
    const payload = await api("/api/state");
    state.data = payload;
    if (oldCatalog && (!((state.data.modelCatalog || {}).all || []).length)) {
      state.data.modelCatalog = Object.assign({}, oldCatalog, {
        activeKeys: ((payload.modelCatalog || {}).activeKeys || oldCatalog.activeKeys || []),
      });
    }
    renderAll();
    const health = payload.health || {};
    const needHealth =
      !Object.keys((health.status || {})).length ||
      !Array.isArray(health.activeModels) ||
      !health.activeModels.length ||
      !((health.usage || {}).raw);
    if (needHealth) {
      refreshHealthDetails().catch((err) => {
        showNotice(`健康信息加载失败: ${err.message || err}`, true);
      });
    }
    if (!(((state.data.modelCatalog || {}).all || []).length)) {
      refreshModelCatalog().catch((err) => {
        showNotice(`模型目录加载失败: ${err.message || err}`, true);
      });
    }
    if (!(state.providerOptions || []).length && !((payload.officialProviderOptions || []).length)) {
      refreshProviderOptions().catch((err) => {
        showNotice(`服务商选项加载失败: ${err.message || err}`, true);
      });
    }
  }

  async function refreshHealthDetails() {
    const health = await api("/api/health");
    if (!state.data) return;
    state.data.health = health || {};
    renderHealth();
  }

  async function refreshModelCatalog() {
    const payload = await api("/api/models/catalog");
    if (!state.data) return;
    state.data.modelCatalog = payload.modelCatalog || { all: [], providers: [], activeKeys: [] };
    fillProviderFilterOptions();
    renderPolicySelectors();
    renderModelPool();
  }

  async function refreshProviderOptions() {
    const payload = await api("/api/providers/options");
    state.providerOptions = payload.options || [];
    if (state.data) {
      state.data.officialProviderOptions = state.providerOptions.slice();
    }
    renderProviderApiManager();
  }

  async function saveGlobalModel() {
    await api("/api/models/global", {
      method: "POST",
      body: JSON.stringify({
        primary: $("globalPrimarySelect").value,
        fallbacks: selectedMultiValues("globalFallbacksSelect"),
      }),
    });
    await refreshState();
    showNotice("已更新全局模型策略");
  }

  async function saveAgentModel() {
    await api("/api/models/agent", {
      method: "POST",
      body: JSON.stringify({
        agentId: $("agentModelId").value,
        primary: $("agentPrimarySelect").value,
        fallbacks: selectedMultiValues("agentFallbacksSelect"),
      }),
    });
    await refreshState();
    showNotice("已更新 Agent 模型覆盖");
  }

  async function clearAgentModel() {
    await api(`/api/models/agent/${encodeURIComponent($("agentModelId").value)}`, { method: "DELETE" });
    await refreshState();
    showNotice("已清除 Agent 模型覆盖");
  }

  async function saveSpawnModel() {
    await api("/api/models/spawn", {
      method: "POST",
      body: JSON.stringify({
        primary: $("spawnPrimarySelect").value,
        fallbacks: selectedMultiValues("spawnFallbacksSelect"),
      }),
    });
    await refreshState();
    showNotice("已更新 Spawn 模型策略");
  }

  async function clearSpawnModel() {
    await api("/api/models/spawn", { method: "DELETE" });
    await refreshState();
    showNotice("已清除 Spawn 模型覆盖");
  }

  async function toggleModel(key, currentlyActive) {
    await api("/api/models/toggle", {
      method: "POST",
      body: JSON.stringify({ key, activate: !currentlyActive }),
    });
    await refreshState();
    showNotice(currentlyActive ? `已移除模型: ${key}` : `已激活模型: ${key}`);
  }

  async function setGlobalFromPool(key) {
    $("globalPrimarySelect").value = key;
    await saveGlobalModel();
  }

  async function saveOfficialProviderApi() {
    await api("/api/providers/api-key", {
      method: "POST",
      body: JSON.stringify({
        provider: $("officialProviderForApi").value,
        apiKey: $("officialProviderApiKey").value,
        baseUrl: $("officialProviderBaseUrl").value.trim(),
      }),
    });
    await refreshState();
    await refreshProviderOptions();
    $("officialProviderApiKey").value = "";
    showNotice("已保存官方服务商 API 配置");
  }

  async function addCustomProvider() {
    const res = await api("/api/providers/custom", {
      method: "POST",
      body: JSON.stringify({
        provider: $("customProviderName").value.trim(),
        api: $("customProviderProtocol").value,
        baseUrl: $("customProviderBaseUrl").value.trim(),
        apiKey: $("customProviderApiKey").value,
        discoverModels: $("customProviderDiscover").checked,
      }),
    });
    await refreshState();
    await refreshProviderOptions();
    const adapted = res.adaptedApi || {};
    if (adapted.from && adapted.to && adapted.from !== adapted.to) {
      showNotice(`已保存自定义服务商（协议自动兼容：${adapted.from} -> ${adapted.to}）`);
      return;
    }
    showNotice("已保存自定义服务商配置");
  }

  async function deleteProvider(provider) {
    await api(`/api/providers/${encodeURIComponent(provider)}`, { method: "DELETE" });
    await refreshState();
    await refreshProviderOptions();
    showNotice(`已删除服务商: ${provider}`);
  }

  async function discoverProviderModels(provider) {
    const res = await api("/api/providers/discover-models", {
      method: "POST",
      body: JSON.stringify({ provider }),
    });
    await refreshState();
    await refreshProviderOptions();
    showNotice(`已发现 ${res.count || 0} 个模型: ${provider}`);
  }

  async function createAgent() {
    await api("/api/agents", {
      method: "POST",
      body: JSON.stringify({
        agentId: $("newAgentId").value.trim(),
        workspace: $("newAgentWorkspace").value.trim(),
        workspaceOnly: $("newAgentWorkspaceOnly").checked,
      }),
    });
    await refreshState();
    showNotice("已创建 Agent");
  }

  async function bindWorkspace() {
    await api("/api/agents/workspace", {
      method: "POST",
      body: JSON.stringify({
        agentId: $("agentOpsId").value,
        workspace: $("bindWorkspaceInput").value.trim(),
      }),
    });
    await refreshState();
    showNotice("已绑定工作区");
  }

  async function setWorkspaceOnly() {
    await api("/api/agents/security", {
      method: "POST",
      body: JSON.stringify({
        agentId: $("agentOpsId").value,
        workspaceOnly: $("workspaceOnlySwitch").checked,
      }),
    });
    await refreshState();
    showNotice("已更新访问限制");
  }

  async function saveWhitelist(enabled) {
    await api("/api/agents/whitelist", {
      method: "POST",
      body: JSON.stringify({
        agentId: $("agentOpsId").value,
        enabled,
        capabilities: parseCsv($("controlCapsInput").value),
      }),
    });
    await refreshState();
    showNotice(enabled ? "已更新命令白名单" : "已清空命令白名单");
  }

  async function saveDispatch() {
    const maxRaw = $("dispatchMaxConcurrent").value.trim();
    await api("/api/dispatch", {
      method: "POST",
      body: JSON.stringify({
        agentId: $("dispatchAgentId").value,
        enabled: $("dispatchEnabled").checked,
        allowAgents: parseCsv($("dispatchAllowAgents").value),
        maxConcurrent: maxRaw ? parseInt(maxRaw, 10) : null,
        inheritMaxConcurrent: $("dispatchInheritMax").checked,
      }),
    });
    await refreshState();
    showNotice("已更新派发策略");
  }

  async function saveOfficialSearch() {
    await api("/api/search/official", {
      method: "POST",
      body: JSON.stringify({
        provider: $("officialSearchProvider").value,
        apiKey: $("officialSearchApiKey").value,
        activateAsDefault: $("officialActivateDefault").checked,
      }),
    });
    await refreshState();
    showNotice("已更新官方搜索配置");
  }

  async function clearOfficialSearch() {
    const provider = $("officialSearchProvider").value;
    await api(`/api/search/official/${encodeURIComponent(provider)}`, { method: "DELETE" });
    await refreshState();
    showNotice("已清空官方搜索配置");
  }

  async function saveAdapterSearch() {
    await api("/api/search/adapter", {
      method: "POST",
      body: JSON.stringify({
        provider: $("adapterProvider").value,
        enabled: $("adapterEnabled").checked,
        apiKey: $("adapterApiKey").value,
        baseUrl: $("adapterBaseUrl").value.trim(),
        model: $("adapterModel").value.trim(),
        topK: parseInt($("adapterTopK").value || "5", 10),
        cooldownSeconds: parseInt($("adapterCooldown").value || "60", 10),
      }),
    });
    await refreshState();
    showNotice("已更新扩展搜索配置");
  }

  async function saveSearchFailover() {
    await api("/api/search/failover", {
      method: "POST",
      body: JSON.stringify({
        primarySource: $("searchPrimarySource").value,
        fallbackSources: parseCsv($("searchFallbackSources").value),
      }),
    });
    await refreshState();
    showNotice("已更新搜索主备链");
  }

  async function testSearch() {
    const out = $("searchTestOutput");
    out.textContent = "执行中...";
    const res = await api("/api/search/test", {
      method: "POST",
      body: JSON.stringify({ query: "openclaw", count: 3 }),
    });
    out.textContent = JSON.stringify(res, null, 2);
    showNotice("搜索演练完成");
  }

  async function refreshOfficialModelPool() {
    const res = await api("/api/providers/refresh-model-pool", { method: "POST" });
    await refreshState();
    await refreshProviderOptions();
    if (res.ok) {
      showNotice(`官方模型池已刷新，模型数: ${res.message}`);
    } else {
      showNotice(`刷新失败: ${res.message}`, true);
    }
  }

  async function runAction(fn, notifyError = true) {
    try {
      await fn();
    } catch (err) {
      if (notifyError) {
        showNotice(err.message || String(err), true);
      } else {
        throw err;
      }
    }
  }

  function bindEvents() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        updateNav(btn.dataset.target);
        if (btn.dataset.target === "dashboard") {
          runAction(refreshHealthDetails);
        }
      });
    });

    $("saveGlobalModelBtn").addEventListener("click", () => runAction(saveGlobalModel));
    $("saveAgentModelBtn").addEventListener("click", () => runAction(saveAgentModel));
    $("clearAgentModelBtn").addEventListener("click", () => runAction(clearAgentModel));
    $("saveSpawnModelBtn").addEventListener("click", () => runAction(saveSpawnModel));
    $("clearSpawnModelBtn").addEventListener("click", () => runAction(clearSpawnModel));

    $("createAgentBtn").addEventListener("click", () => runAction(createAgent));
    $("bindWorkspaceBtn").addEventListener("click", () => runAction(bindWorkspace));
    $("setWorkspaceOnlyBtn").addEventListener("click", () => runAction(setWorkspaceOnly));
    $("setWhitelistBtn").addEventListener("click", () => runAction(() => saveWhitelist(true)));
    $("clearWhitelistBtn").addEventListener("click", () => runAction(() => saveWhitelist(false)));

    $("saveDispatchBtn").addEventListener("click", () => runAction(saveDispatch));

    $("saveOfficialSearchBtn").addEventListener("click", () => runAction(saveOfficialSearch));
    $("clearOfficialSearchBtn").addEventListener("click", () => runAction(clearOfficialSearch));
    $("saveAdapterBtn").addEventListener("click", () => runAction(saveAdapterSearch));
    $("saveSearchFailoverBtn").addEventListener("click", () => runAction(saveSearchFailover));
    $("testSearchBtn").addEventListener("click", () => runAction(testSearch));

    $("saveOfficialProviderApiBtn").addEventListener("click", () => runAction(saveOfficialProviderApi));
    $("addCustomProviderBtn").addEventListener("click", () => runAction(addCustomProvider));

    $("refreshModelPoolBtn").addEventListener("click", () => runAction(refreshOfficialModelPool));

    $("agentModelId").addEventListener("change", syncAgentDrivenForms);
    $("agentOpsId").addEventListener("change", syncAgentDrivenForms);
    $("dispatchAgentId").addEventListener("change", syncAgentDrivenForms);
    $("adapterProvider").addEventListener("change", syncAdapterFields);

    $("modelProviderFilter").addEventListener("change", () => {
      renderPolicySelectors();
      renderModelPool();
    });
    $("modelKeywordFilter").addEventListener("input", () => {
      renderPolicySelectors();
      renderModelPool();
    });

    $("modelPoolRows").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      const action = btn.dataset.action;
      const key = btn.dataset.key;
      const active = btn.dataset.active === "1";
      if (action === "set-global") {
        runAction(() => setGlobalFromPool(key));
      } else if (action === "toggle-model") {
        runAction(() => toggleModel(key, active));
      }
    });

    $("providerManageRows").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      const provider = btn.dataset.provider;
      if (!provider) return;
      const action = btn.dataset.action;
      if (action === "delete-provider") {
        if (!window.confirm(`确认删除服务商 ${provider}？`)) return;
        runAction(() => deleteProvider(provider));
      } else if (action === "discover-provider") {
        runAction(() => discoverProviderModels(provider));
      }
    });

    $("saveTokenBtn").addEventListener("click", async () => {
      const token = $("tokenInput").value.trim();
      if (!token) {
        showNotice("请输入 token", true);
        return;
      }
      state.token = token;
      setSavedToken(token);
      await runAction(refreshState, false);
      showNotice("Token 已保存并连接成功");
    });
  }

  async function bootstrap() {
    const token = parseTokenFromUrl() || getSavedToken();
    $("tokenInput").value = token;
    state.token = token;

    bindEvents();

    if (!token) {
      showNotice("请先输入 API Token（X-Claw-Token）", true);
      return;
    }

    await runAction(refreshState);
  }

  bootstrap();
})();
