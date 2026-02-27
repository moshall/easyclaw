(function () {
  const state = {
    token: "",
    data: null,
    providerOptions: [],
    rollbackBackups: [],
    rollbackMeta: { configPath: "", backupDir: "" },
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

  function modelAvailabilityFlag(available) {
    if (available === true) return "✅";
    if (available === false) return "❌";
    return "⚪";
  }

  function modelOptionLabel(m) {
    return `${modelAvailabilityFlag(m.available)} ${m.provider} / ${m.name}`;
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

  function formatBytes(bytes) {
    const n = Number(bytes || 0);
    if (!Number.isFinite(n) || n <= 0) return "0 B";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatEpoch(epoch) {
    const n = Number(epoch || 0);
    if (!Number.isFinite(n) || n <= 0) return "-";
    return new Date(n * 1000).toLocaleString();
  }

  function fillModelSingleSelect(selectId, selectedValue, allowEmpty = true, rows = null) {
    const select = $(selectId);
    const options = [{ value: "", label: "(未设置)" }];
    (rows || getFilteredModels()).forEach((m) => {
      options.push({ value: m.key, label: modelOptionLabel(m) });
    });
    if (!allowEmpty) {
      options.shift();
    }
    fillSelect(select, options);
    select.value = selectedValue || "";
  }

  function fillModelMultiSelect(selectId, selectedValues, rows = null) {
    const select = $(selectId);
    const selectedSet = new Set((selectedValues || []).filter(Boolean));
    select.innerHTML = "";
    (rows || getFilteredModels()).forEach((m) => {
      const el = document.createElement("option");
      el.value = m.key;
      el.textContent = modelOptionLabel(m);
      el.selected = selectedSet.has(m.key);
      select.appendChild(el);
    });
  }

  function ensureModelOption(selectId, key, available = null) {
    const select = $(selectId);
    if (!key) return;
    const exists = Array.from(select.options || []).some((o) => o.value === key);
    if (exists) return;
    const provider = key.includes("/") ? key.split("/", 1)[0] : "other";
    const name = key.includes("/") ? key.split("/", 2)[1] : key;
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = modelOptionLabel({ key, provider, name, available });
    select.appendChild(opt);
  }

  function updateNav(targetId) {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.target === targetId);
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === targetId);
    });
  }

  function updateSubtab(group, targetId) {
    document.querySelectorAll(`.subtab-btn[data-subgroup="${group}"]`).forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.subtarget === targetId);
    });
    document.querySelectorAll(`.subpanel[data-subgroup="${group}"]`).forEach((panel) => {
      panel.classList.toggle("active", panel.id === targetId);
    });
  }

  function getFilteredModels() {
    const data = state.data;
    if (!data) return [];
    const provider = ($("modelProviderFilter").value || "").trim();
    const keyword = ($("modelKeywordFilter").value || "").trim().toLowerCase();
    const authorizedProviders = getAuthorizedProviderSet();

    let rows = (data.modelCatalog.all || []).slice();
    if (authorizedProviders.size) {
      rows = rows.filter((m) => authorizedProviders.has(m.provider));
    } else {
      rows = [];
    }
    if (provider) {
      rows = rows.filter((m) => m.provider === provider);
    }
    if (keyword) {
      rows = rows.filter((m) => `${m.key} ${m.name} ${m.provider}`.toLowerCase().includes(keyword));
    }
    return rows;
  }

  function getAuthorizedProviderSet() {
    if (!state.data) return new Set();
    const set = new Set();
    ((state.data.inventory || {}).rows || []).forEach((row) => {
      if (Number(row.authCount || 0) > 0 || Number(row.keyCount || 0) > 0) {
        set.add(row.provider);
      }
    });
    (((state.data.modelCatalog || {}).activeKeys) || []).forEach((key) => {
      const provider = key.includes("/") ? key.split("/", 1)[0] : "other";
      set.add(provider);
    });
    return set;
  }

  function modelFromKey(mapByKey, key) {
    const k = (key || "").trim();
    if (!k) return null;
    if (mapByKey.has(k)) {
      return mapByKey.get(k);
    }
    const provider = k.includes("/") ? k.split("/", 1)[0] : "other";
    const name = k.includes("/") ? k.slice(provider.length + 1) : k;
    return { key: k, provider, name, available: null };
  }

  function getPolicyModels() {
    const data = state.data;
    if (!data) return [];
    const all = (data.modelCatalog.all || []).slice();
    const mapByKey = new Map(all.map((m) => [m.key, m]));
    const out = [];
    const seen = new Set();

    const pushKey = (key) => {
      const row = modelFromKey(mapByKey, key);
      if (!row || seen.has(row.key)) return;
      seen.add(row.key);
      out.push(row);
    };

    (data.modelCatalog.activeKeys || []).forEach(pushKey);

    if (!out.length) {
      const configuredProviders = new Set(
        (data.inventory.rows || [])
          .filter((r) => Number(r.authCount || 0) > 0 || Number(r.keyCount || 0) > 0)
          .map((r) => r.provider)
      );
      const baseRows = configuredProviders.size
        ? all.filter((m) => configuredProviders.has(m.provider))
        : all;
      baseRows.forEach((m) => pushKey(m.key));
    }

    const gm = data.globalModel || {};
    pushKey(gm.primary || "");
    (gm.fallbacks || []).forEach(pushKey);
    const sm = data.spawnModel || {};
    pushKey(sm.primary || "");
    (sm.fallbacks || []).forEach(pushKey);
    (data.agents || []).forEach((a) => {
      const am = a.model || {};
      pushKey(am.primary || "");
      (am.fallbacks || []).forEach(pushKey);
    });

    return out;
  }

  function fillProviderFilterOptions() {
    const cur = $("modelProviderFilter").value;
    const authorizedProviders = getAuthorizedProviderSet();
    const providers = ((state.data.modelCatalog || {}).providers || []).filter((p) => authorizedProviders.has(p));
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
    const policyRows = getPolicyModels();
    fillModelSingleSelect("agentPrimarySelect", agent ? agent.model.primary : "", true, policyRows);
    fillModelMultiSelect("agentFallbacksSelect", agent ? agent.model.fallbacks : [], policyRows);

    const aidOps = $("agentOpsId").value;
    const agentOps = (state.data.agents || []).find((x) => x.id === aidOps);
    if (agentOps) {
      $("bindWorkspaceInput").value = agentOps.workspace || "";
      $("workspaceOnlySwitch").checked = !!agentOps.security.workspaceOnly;
      $("controlCapsInput").value = (agentOps.security.controlPlaneCapabilities || []).join(",");
    } else {
      $("bindWorkspaceInput").value = "";
      $("workspaceOnlySwitch").checked = false;
      $("controlCapsInput").value = "";
    }

    const aidDispatch = $("dispatchAgentId").value;
    const agentDispatch = (state.data.agents || []).find((x) => x.id === aidDispatch);
    if (agentDispatch) {
      $("dispatchEnabled").checked = !!agentDispatch.subagents.enabled;
      $("dispatchAllowAgents").value = (agentDispatch.subagents.allowAgents || []).join(",");
      $("dispatchMaxConcurrent").value = agentDispatch.subagents.maxConcurrent || "";
      $("dispatchInheritMax").checked = false;
    } else {
      $("dispatchEnabled").checked = false;
      $("dispatchAllowAgents").value = "";
      $("dispatchMaxConcurrent").value = "";
      $("dispatchInheritMax").checked = false;
    }
    renderDispatchOverview();
  }

  function renderDispatchOverview() {
    const agentId = $("dispatchAgentId").value || "(未选择)";
    const agentDispatch = (state.data.agents || []).find((x) => x.id === $("dispatchAgentId").value);
    const allow = (agentDispatch && agentDispatch.subagents && Array.isArray(agentDispatch.subagents.allowAgents))
      ? agentDispatch.subagents.allowAgents
      : [];
    const max = (agentDispatch && agentDispatch.subagents) ? agentDispatch.subagents.maxConcurrent : null;

    $("dispatchCurrentAgent").textContent = agentId;
    $("dispatchCurrentEnabled").textContent = (agentDispatch && agentDispatch.subagents && agentDispatch.subagents.enabled) ? "✅ 已启用" : "❌ 已关闭";
    $("dispatchCurrentAllow").textContent = allow.length ? allow.join(", ") : "(未设置)";
    $("dispatchCurrentMax").textContent = (max === null || max === undefined || max === "") ? "(继承全局)" : String(max);
    $("dispatchGlobalMax").textContent = String((state.data.dispatch || {}).globalMaxConcurrent || 8);
  }

  function renderPolicySelectors() {
    const policyRows = getPolicyModels();
    fillModelSingleSelect("globalPrimarySelect", (state.data.globalModel || {}).primary || "", true, policyRows);
    fillModelMultiSelect("globalFallbacksSelect", (state.data.globalModel || {}).fallbacks || [], policyRows);

    fillModelSingleSelect("spawnPrimarySelect", (state.data.spawnModel || {}).primary || "", true, policyRows);
    fillModelMultiSelect("spawnFallbacksSelect", (state.data.spawnModel || {}).fallbacks || [], policyRows);

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
    const options = ((state.providerOptions || []).length
      ? state.providerOptions
      : (state.data.officialProviderOptions || []))
      .filter((o) => ["OAuth", "API Key"].includes((o.authType || "").trim()));
    const configuredProviders = getAuthorizedProviderSet();
    const seen = new Set();
    const officialOptsRaw = [];
    options.forEach((o) => {
      const provider = (o.providerId || o.id || "").trim();
      const value = String(o.id || provider || "").trim();
      if (!provider || !value || seen.has(value)) return;
      seen.add(value);
      officialOptsRaw.push({
        value,
        provider,
        authType: o.authType || "",
        label: `${provider} · ${(o.authType || "Unknown")} · ${o.label || o.id}`,
      });
    });
    officialOptsRaw.sort((a, b) => {
      const ac = configuredProviders.has(a.provider) ? 1 : 0;
      const bc = configuredProviders.has(b.provider) ? 1 : 0;
      if (ac !== bc) return bc - ac;
      return a.label.localeCompare(b.label);
    });
    const officialOpts = officialOptsRaw.map((x) => ({ value: x.value, label: x.label }));
    if (!officialOpts.length) {
      officialOpts.push({ value: "", label: "(暂无可配置官方服务商)" });
    }
    const currentOpt = $("officialAuthOption").value;
    fillSelect($("officialAuthOption"), officialOpts);
    if (officialOptsRaw.some((x) => x.value === currentOpt)) {
      $("officialAuthOption").value = currentOpt;
    }

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
    const rows = (state.data.inventory.rows || []).slice().sort((a, b) => {
      const as = Number(a.authCount || 0) + Number(a.keyCount || 0);
      const bs = Number(b.authCount || 0) + Number(b.keyCount || 0);
      if (as !== bs) return bs - as;
      return String(a.provider || "").localeCompare(String(b.provider || ""));
    });
    if (!rows.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="5" class="muted">暂无服务商</td>`;
      tableBody.appendChild(tr);
    } else {
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

    syncOfficialAuthMode();
  }

  function getSelectedOfficialAuthOption() {
    const options = ((state.providerOptions || []).length
      ? state.providerOptions
      : (state.data.officialProviderOptions || []));
    const id = $("officialAuthOption").value;
    return options.find((o) => String(o.id || o.providerId || "") === id) || null;
  }

  function syncOfficialAuthMode() {
    const selected = getSelectedOfficialAuthOption();
    const authType = String((selected && selected.authType) || "");
    const provider = String((selected && (selected.providerId || selected.id)) || "");

    $("officialAuthProvider").value = provider || "(未选择)";
    const isOAuth = authType === "OAuth";
    $("officialApiAuthBox").style.display = isOAuth ? "none" : "block";
    $("officialOauthAuthBox").style.display = isOAuth ? "block" : "none";
    if (!isOAuth) {
      $("officialOauthLink").value = "";
      $("officialOauthCode").value = "";
      $("officialOauthRaw").textContent = "";
      $("officialOauthLinkAnchor").style.display = "none";
      $("officialOauthLinkAnchor").href = "#";
    }
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

  function renderRollbackBackups() {
    const meta = state.rollbackMeta || {};
    $("rollbackConfigPath").textContent = meta.configPath || "-";
    $("rollbackBackupDir").textContent = meta.backupDir || "-";

    const items = (state.rollbackBackups || []).slice();
    const options = items.map((b) => ({
      value: b.name,
      label: `${b.name}  (${formatEpoch(b.mtime)})`,
    }));
    if (!options.length) {
      options.push({ value: "", label: "(暂无备份)" });
    }
    fillSelect($("rollbackBackupSelect"), options);

    const body = $("rollbackRows");
    body.innerHTML = "";
    if (!items.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="3" class="muted">暂无备份文件</td>`;
      body.appendChild(tr);
      return;
    }
    items.forEach((b) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="mono">${b.name || "-"}</td><td>${formatEpoch(b.mtime)}</td><td>${formatBytes(b.size)}</td>`;
      body.appendChild(tr);
    });
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
    renderRollbackBackups();
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

  async function refreshRollbackBackups() {
    const payload = await api("/api/config/backups?limit=30");
    state.rollbackMeta = {
      configPath: payload.configPath || "",
      backupDir: payload.backupDir || "",
    };
    state.rollbackBackups = payload.items || [];
    renderRollbackBackups();
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
    ensureModelOption("globalPrimarySelect", key);
    $("globalPrimarySelect").value = key;
    await saveGlobalModel();
  }

  async function saveOfficialProviderApi() {
    const opt = getSelectedOfficialAuthOption();
    if (!opt) {
      throw new Error("请先选择官方认证方式");
    }
    if (String(opt.authType || "") === "OAuth") {
      throw new Error("当前是 OAuth 模式，请使用“获取授权链接”");
    }
    const provider = String(opt.providerId || opt.id || "").trim();
    if (!provider) {
      throw new Error("无效服务商");
    }
    await api("/api/providers/api-key", {
      method: "POST",
      body: JSON.stringify({
        provider,
        apiKey: $("officialProviderApiKey").value,
        baseUrl: "",
      }),
    });
    await refreshState();
    await refreshProviderOptions();
    $("officialProviderApiKey").value = "";
    showNotice("已保存官方服务商 API 配置");
  }

  async function startOfficialOauth() {
    const opt = getSelectedOfficialAuthOption();
    if (!opt) {
      throw new Error("请先选择官方认证方式");
    }
    if (String(opt.authType || "") !== "OAuth") {
      throw new Error("当前是 API Key 模式，请填写 API Key");
    }
    const provider = String(opt.providerId || opt.id || "").trim();
    const optionId = String(opt.id || "").trim();
    const res = await api("/api/providers/oauth/start", {
      method: "POST",
      body: JSON.stringify({ provider, optionId }),
    });
    $("officialOauthLink").value = res.oauthUrl || "";
    $("officialOauthCode").value = res.oauthCode || "";
    $("officialOauthRaw").textContent = res.raw || "";
    const linkAnchor = $("officialOauthLinkAnchor");
    if (res.oauthUrl) {
      linkAnchor.href = res.oauthUrl;
      linkAnchor.style.display = "inline-flex";
    } else {
      linkAnchor.href = "#";
      linkAnchor.style.display = "none";
    }
    if (res.requiresTty) {
      const hint = res.recommendedCommand
        ? `\n\n需要在终端执行:\n${res.recommendedCommand}`
        : "";
      $("officialOauthRaw").textContent = ($("officialOauthRaw").textContent || "") + hint;
      showNotice("该 OAuth 方式要求交互式 TTY，请按下方命令在终端完成授权", true);
      return;
    }
    if (res.ok || res.oauthUrl || res.oauthCode) {
      showNotice("已获取 OAuth 授权信息");
    } else {
      showNotice("OAuth 授权信息未返回链接/授权码，请查看输出详情", true);
    }
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
    const enabled = $("dispatchEnabled").checked;
    let allowAgents = parseCsv($("dispatchAllowAgents").value);
    if (enabled && !allowAgents.length) {
      allowAgents = ["*"];
      $("dispatchAllowAgents").value = "*";
    }
    await api("/api/dispatch", {
      method: "POST",
      body: JSON.stringify({
        agentId: $("dispatchAgentId").value,
        enabled,
        allowAgents,
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

  async function applyConfigRollback() {
    const selected = ($("rollbackBackupSelect").value || "").trim();
    if (!selected) {
      throw new Error("请先选择备份文件");
    }
    if (!window.confirm(`确认回滚到 ${selected}？`)) {
      return;
    }
    const res = await api("/api/config/rollback", {
      method: "POST",
      body: JSON.stringify({ backupName: selected }),
    });
    await refreshState();
    await refreshRollbackBackups();
    $("rollbackResult").textContent = JSON.stringify(
      {
        restored: res.restored || "",
        restoredPath: res.restoredPath || "",
        preBackupPath: res.preBackupPath || "",
      },
      null,
      2
    );
    showNotice(`已回滚到: ${res.restored || selected}`);
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

  async function runActionWithButton(buttonId, fn, pendingText = "处理中...") {
    const btn = $(buttonId);
    if (!btn) return runAction(fn);
    const oldText = btn.textContent;
    const oldDisabled = btn.disabled;
    btn.disabled = true;
    btn.textContent = pendingText;
    try {
      await runAction(fn);
    } finally {
      btn.disabled = oldDisabled;
      btn.textContent = oldText;
    }
  }

  function bindEvents() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        updateNav(btn.dataset.target);
        if (btn.dataset.target === "dashboard") {
          runAction(refreshHealthDetails);
        } else if (btn.dataset.target === "services") {
          runAction(refreshRollbackBackups);
        }
      });
    });
    document.querySelectorAll(".subtab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const group = btn.dataset.subgroup;
        const target = btn.dataset.subtarget;
        if (group && target) {
          updateSubtab(group, target);
        }
      });
    });

    $("saveGlobalModelBtn").addEventListener("click", () => runActionWithButton("saveGlobalModelBtn", saveGlobalModel, "保存中..."));
    $("saveAgentModelBtn").addEventListener("click", () => runActionWithButton("saveAgentModelBtn", saveAgentModel, "保存中..."));
    $("clearAgentModelBtn").addEventListener("click", () => runActionWithButton("clearAgentModelBtn", clearAgentModel, "清除中..."));
    $("saveSpawnModelBtn").addEventListener("click", () => runActionWithButton("saveSpawnModelBtn", saveSpawnModel, "保存中..."));
    $("clearSpawnModelBtn").addEventListener("click", () => runActionWithButton("clearSpawnModelBtn", clearSpawnModel, "清除中..."));

    $("createAgentBtn").addEventListener("click", () => runAction(createAgent));
    $("bindWorkspaceBtn").addEventListener("click", () => runAction(bindWorkspace));
    $("setWorkspaceOnlyBtn").addEventListener("click", () => runAction(setWorkspaceOnly));
    $("setWhitelistBtn").addEventListener("click", () => runAction(() => saveWhitelist(true)));
    $("clearWhitelistBtn").addEventListener("click", () => runAction(() => saveWhitelist(false)));

    $("saveDispatchBtn").addEventListener("click", () => runActionWithButton("saveDispatchBtn", saveDispatch, "保存中..."));

    $("saveOfficialSearchBtn").addEventListener("click", () => runActionWithButton("saveOfficialSearchBtn", saveOfficialSearch, "保存中..."));
    $("clearOfficialSearchBtn").addEventListener("click", () => runActionWithButton("clearOfficialSearchBtn", clearOfficialSearch, "清空中..."));
    $("saveAdapterBtn").addEventListener("click", () => runActionWithButton("saveAdapterBtn", saveAdapterSearch, "保存中..."));
    $("saveSearchFailoverBtn").addEventListener("click", () => runActionWithButton("saveSearchFailoverBtn", saveSearchFailover, "保存中..."));
    $("testSearchBtn").addEventListener("click", () => runActionWithButton("testSearchBtn", testSearch, "测试中..."));
    $("rollbackRefreshBtn").addEventListener("click", () => runActionWithButton("rollbackRefreshBtn", refreshRollbackBackups, "刷新中..."));
    $("rollbackApplyBtn").addEventListener("click", () => runActionWithButton("rollbackApplyBtn", applyConfigRollback, "回滚中..."));

    $("saveOfficialProviderApiBtn").addEventListener("click", () => runActionWithButton("saveOfficialProviderApiBtn", saveOfficialProviderApi, "保存中..."));
    $("startOfficialOauthBtn").addEventListener("click", () => runActionWithButton("startOfficialOauthBtn", startOfficialOauth, "获取中..."));
    $("addCustomProviderBtn").addEventListener("click", () => runActionWithButton("addCustomProviderBtn", addCustomProvider, "保存中..."));

    $("refreshModelPoolBtn").addEventListener("click", () => runAction(refreshOfficialModelPool));

    $("agentModelId").addEventListener("change", syncAgentDrivenForms);
    $("agentOpsId").addEventListener("change", syncAgentDrivenForms);
    $("dispatchAgentId").addEventListener("change", syncAgentDrivenForms);
    $("adapterProvider").addEventListener("change", syncAdapterFields);
    $("officialAuthOption").addEventListener("change", syncOfficialAuthMode);

    $("modelProviderFilter").addEventListener("change", () => {
      renderModelPool();
    });
    $("modelKeywordFilter").addEventListener("input", () => {
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
    await runAction(refreshRollbackBackups);
  }

  bootstrap();
})();
