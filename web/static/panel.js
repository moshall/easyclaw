(function () {
  const tokenInput = document.getElementById("tokenInput");
  const saveTokenBtn = document.getElementById("saveTokenBtn");
  const notice = document.getElementById("notice");

  const state = {
    token: "",
    data: null,
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
    notice.className = "notice " + (isError ? "err" : "ok");
    notice.textContent = msg;
    window.setTimeout(() => {
      notice.className = "notice";
      notice.textContent = "";
    }, 3000);
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

  function fillSelect(select, options, valueField = "value", labelField = "label") {
    select.innerHTML = "";
    options.forEach((opt) => {
      const el = document.createElement("option");
      el.value = opt[valueField];
      el.textContent = opt[labelField];
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

  function renderState() {
    const data = state.data;
    if (!data) return;

    $("dashPrimary").textContent = data.globalModel.primary || "(未设置)";
    $("dashFallbacks").textContent = data.globalModel.fallbacks.length ? data.globalModel.fallbacks.join(" -> ") : "(未设置)";

    const adapter = data.search.adapterConfig || {};
    const searchChain = [adapter.primarySource || "(未设置)"];
    if (Array.isArray(adapter.fallbackSources) && adapter.fallbackSources.length) {
      searchChain.push(...adapter.fallbackSources);
    }
    $("dashSearchProvider").textContent = data.search.defaultProvider || "(未设置)";
    $("dashSearchChain").textContent = searchChain.join(" -> ");

    const invBody = $("inventoryRows");
    invBody.innerHTML = "";
    (data.inventory.rows || []).forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.provider}</td><td>${row.authCount}</td><td>${row.keyCount}</td><td>${row.modelCount}</td>`;
      invBody.appendChild(tr);
    });

    $("globalPrimary").value = data.globalModel.primary || "";
    $("globalFallbacks").value = (data.globalModel.fallbacks || []).join(",");

    const agentOpts = (data.agents || []).map((a) => ({ value: a.id, label: a.id }));
    if (!agentOpts.length) {
      agentOpts.push({ value: "", label: "(暂无 Agent)" });
    }
    fillSelect($("agentModelId"), agentOpts);
    fillSelect($("agentOpsId"), agentOpts);
    fillSelect($("dispatchAgentId"), agentOpts);

    const agentBody = $("agentRows");
    agentBody.innerHTML = "";
    (data.agents || []).forEach((agent) => {
      const tr = document.createElement("tr");
      const modelPolicy = agent.model.overridden ? "独立模型" : "跟随全局";
      tr.innerHTML = `<td>${agent.id}</td><td>${agent.workspace || "(未绑定)"}</td><td>${agent.security.workspaceOnly ? "仅工作区" : "全部"}</td><td>${modelPolicy}</td>`;
      agentBody.appendChild(tr);
    });

    $("spawnPrimary").value = data.spawnModel.primary || "";
    $("spawnFallbacks").value = (data.spawnModel.fallbacks || []).join(",");

    const officialProviders = (data.search.officialSupported || []).map((p) => ({ value: p, label: `${p}${(data.search.officialConfigured || []).includes(p) ? " (已配置)" : ""}` }));
    fillSelect($("officialSearchProvider"), officialProviders);

    const adapterProviders = Object.keys((data.search.adapterConfig || {}).providers || {}).map((p) => ({ value: p, label: p }));
    fillSelect($("adapterProvider"), adapterProviders);

    const sourceOpts = [{ value: "", label: "(不设置)" }].concat((data.search.availableUnifiedSources || []).map((s) => ({ value: s, label: s })));
    fillSelect($("searchPrimarySource"), sourceOpts);
    $("searchPrimarySource").value = adapter.primarySource || "";
    $("searchFallbackSources").value = (adapter.fallbackSources || []).join(",");

    syncAgentDrivenForms();
    syncAdapterFields();
  }

  function syncAgentDrivenForms() {
    const aid = $("agentModelId").value;
    const agent = (state.data.agents || []).find((x) => x.id === aid);
    if (agent) {
      $("agentModelPrimary").value = agent.model.primary || "";
      $("agentModelFallbacks").value = (agent.model.fallbacks || []).join(",");
    }

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

  async function refreshState() {
    const payload = await api("/api/state");
    state.data = payload;
    renderState();
  }

  async function saveGlobalModel() {
    await api("/api/models/global", {
      method: "POST",
      body: JSON.stringify({
        primary: $("globalPrimary").value.trim(),
        fallbacks: parseCsv($("globalFallbacks").value),
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
        primary: $("agentModelPrimary").value.trim(),
        fallbacks: parseCsv($("agentModelFallbacks").value),
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
        primary: $("spawnPrimary").value.trim(),
        fallbacks: parseCsv($("spawnFallbacks").value),
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
    if (res.ok) {
      showNotice(`官方模型池已刷新，模型数: ${res.message}`);
    } else {
      showNotice(`刷新失败: ${res.message}`, true);
    }
  }

  function bindEvents() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => updateNav(btn.dataset.target));
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
    $("refreshModelPoolBtn").addEventListener("click", () => runAction(refreshOfficialModelPool));

    $("agentModelId").addEventListener("change", syncAgentDrivenForms);
    $("agentOpsId").addEventListener("change", syncAgentDrivenForms);
    $("dispatchAgentId").addEventListener("change", syncAgentDrivenForms);
    $("adapterProvider").addEventListener("change", syncAdapterFields);

    saveTokenBtn.addEventListener("click", async () => {
      const token = tokenInput.value.trim();
      if (!token) {
        showNotice("请输入 token", true);
        return;
      }
      state.token = token;
      setSavedToken(token);
      await runAction(refreshState, false);
      showNotice("Token 已保存");
    });
  }

  async function runAction(fn, notifyError = true) {
    try {
      await fn();
    } catch (err) {
      if (notifyError) showNotice(err.message || String(err), true);
      else throw err;
    }
  }

  async function bootstrap() {
    const token = parseTokenFromUrl() || getSavedToken();
    tokenInput.value = token;
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
