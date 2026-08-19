document.querySelectorAll("[data-confirm-trim]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const days = form.querySelector("input[name='days']").value;
    const ok = window.confirm(`Delete captured rows older than ${days} days?`);
    if (!ok) {
      event.preventDefault();
    }
  });
});

const fullDateTime = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "medium",
});

const tableDate = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const tableTime = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
});

const mobileDateTime = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
});

document.querySelectorAll("[data-local-time]").forEach((element) => {
  const value = element.getAttribute("datetime");
  if (!value) {
    return;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return;
  }

  const fallback = element.textContent.trim();
  const full = fullDateTime.format(date);
  element.title = fallback ? `${full} (${fallback})` : full;

  if (element.dataset.localTime === "table") {
    element.replaceChildren();
    const dateLine = document.createElement("span");
    dateLine.textContent = tableDate.format(date);
    const timeLine = document.createElement("span");
    timeLine.textContent = tableTime.format(date);
    element.append(dateLine, timeLine);
    return;
  }

  element.textContent = full;
});

const formatDuration = (milliseconds) => {
  const totalMs = Math.max(0, Math.round(milliseconds));
  if (totalMs < 1000) {
    return `${totalMs} ms`;
  }

  if (totalMs < 60000) {
    const seconds = totalMs / 1000;
    return `${Number(seconds.toFixed(2)).toString()} s`;
  }

  const totalSeconds = Math.round(totalMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  }

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  const dayLabel = days === 1 ? "day" : "days";
  return remainingHours ? `${days} ${dayLabel} ${remainingHours}h` : `${days} ${dayLabel}`;
};

const updatePendingElapsed = () => {
  document.querySelectorAll("[data-pending-start]").forEach((element) => {
    const value = element.dataset.pendingStart;
    if (!value) {
      return;
    }

    const started = new Date(value);
    if (Number.isNaN(started.getTime())) {
      return;
    }

    element.textContent = `${formatDuration(Date.now() - started.getTime())} so far`;
  });
};

if (document.querySelector("[data-pending-start]")) {
  updatePendingElapsed();
  window.setInterval(updatePendingElapsed, 1000);
}

const whatIfPanel = document.querySelector("[data-what-if-panel]");

if (whatIfPanel) {
  const apiUrl = whatIfPanel.dataset.apiUrl;
  const form = whatIfPanel.querySelector("[data-what-if-form]");
  const input = whatIfPanel.querySelector("[data-what-if-input]");
  const optionsList = whatIfPanel.querySelector("[data-what-if-options]");
  const scenariosBody = whatIfPanel.querySelector("[data-what-if-scenarios]");
  const count = whatIfPanel.querySelector("[data-what-if-count]");
  const message = whatIfPanel.querySelector("[data-what-if-message]");
  const submitButton = form?.querySelector("button[type='submit']");

  let priceOptions = [];
  let selectedKeys = [];
  let latestScenarios = [];
  let latestBaseline = null;

  const setMessage = (text) => {
    if (!message) {
      return;
    }
    message.textContent = text || "";
    message.hidden = !text;
  };

  const setCount = (text) => {
    if (count) {
      count.textContent = text;
    }
  };

  const optionValue = (option) => `${option.label} (${option.provider_name})`;

  const normalize = (value) => value.trim().toLowerCase();

  const renderOptions = () => {
    if (!optionsList) {
      return;
    }

    optionsList.replaceChildren();
    priceOptions.forEach((item) => {
      const option = document.createElement("option");
      option.value = optionValue(item);
      option.dataset.key = item.key;
      option.label = `${item.provider_name} / ${item.model}`;
      optionsList.append(option);
    });

    if (input) {
      input.disabled = priceOptions.length === 0;
    }
    if (submitButton) {
      submitButton.disabled = priceOptions.length === 0;
    }
  };

  const renderStatusRow = (text, className = "empty") => {
    if (!scenariosBody) {
      return;
    }
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = className;
    cell.colSpan = 12;
    cell.textContent = text;
    row.append(cell);
    scenariosBody.replaceChildren(row);
  };

  const displayValue = (scenario, key) => scenario.display?.[key] || "-";

  const appendCell = (row, text) => {
    const cell = document.createElement("td");
    cell.textContent = text || "-";
    row.append(cell);
  };

  const appendStrongCell = (row, text) => {
    const cell = document.createElement("td");
    const strong = document.createElement("strong");
    strong.textContent = text || "-";
    cell.append(strong);
    row.append(cell);
  };

  const renderScenarios = (scenarios) => {
    if (!scenariosBody) {
      return;
    }
    scenariosBody.replaceChildren();

    if (!scenarios.length) {
      renderStatusRow("No comparison rows selected.");
      return;
    }

    scenarios.forEach((scenario) => {
      const row = document.createElement("tr");
      const scenarioCell = document.createElement("td");
      const scenarioWrap = document.createElement("div");
      scenarioWrap.className = "what-if-scenario";

      const copy = document.createElement("div");
      const label = document.createElement("strong");
      label.textContent = scenario.label;
      const meta = document.createElement("span");
      meta.className = "muted";
      meta.textContent = `${scenario.provider_name} / ${scenario.model}`;
      copy.append(label, meta);

      const remove = document.createElement("button");
      remove.className = "button ghost compact-button what-if-remove";
      remove.type = "button";
      remove.dataset.key = scenario.key;
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", `Remove ${scenario.label}`);

      scenarioWrap.append(copy, remove);
      scenarioCell.append(scenarioWrap);
      row.append(scenarioCell);

      appendCell(row, displayValue(scenario, "input_tokens"));
      appendCell(row, displayValue(scenario, "cached_input_tokens"));
      appendCell(row, displayValue(scenario, "output_tokens"));
      appendCell(row, displayValue(scenario, "input_usd_per_million"));
      appendCell(row, displayValue(scenario, "cached_input_usd_per_million"));
      appendCell(row, displayValue(scenario, "output_usd_per_million"));
      appendCell(row, displayValue(scenario, "input_cost_usd"));
      appendCell(row, displayValue(scenario, "output_cost_usd"));
      appendStrongCell(row, displayValue(scenario, "total_cost_usd"));
      appendCell(row, displayValue(scenario, "included_request_count"));
      appendCell(row, displayValue(scenario, "missing_usage_request_count"));

      scenariosBody.append(row);
    });
  };

  const renderSummary = (scenarios, baseline = latestBaseline) => {
    const summaryList = document.querySelector("[data-what-if-summary]");
    if (!summaryList) {
      return;
    }
    summaryList.replaceChildren();
    if (!baseline && !scenarios.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No comparisons selected.";
      summaryList.append(empty);
      return;
    }
    const baselineValue = baseline ? baseline.total_cost_usd : scenarios[0]?.total_cost_usd;
    const rows = baseline ? [baseline, ...scenarios.slice(0, 2)] : scenarios.slice(0, 3);
    rows.forEach((scenario, index) => {
      const total = scenario.display?.total_cost_usd || "-";
      let delta = index === 0 && baseline ? "Current baseline" : (index === 0 ? "Baseline" : "");
      if (
        index > 0
        && typeof baselineValue === "number"
        && typeof scenario.total_cost_usd === "number"
      ) {
        const amount = scenario.total_cost_usd - baselineValue;
        const percent = baselineValue ? (amount / baselineValue) * 100 : null;
        delta = `${amount >= 0 ? "+" : ""}${amount.toFixed(4)}${percent === null ? "" : ` · ${percent >= 0 ? "+" : ""}${percent.toFixed(1)}%`}`;
      }
      const row = document.createElement("div");
      row.className = `what-if-summary-row${index === 0 && baseline ? " current" : ""}`;
      const labelWrap = document.createElement("span");
      const label = document.createElement("strong");
      label.textContent = scenario.label;
      const meta = document.createElement("small");
      meta.textContent = `${scenario.provider_name} / ${scenario.model}`;
      labelWrap.append(label, meta);
      const totalWrap = document.createElement("span");
      const totalValue = document.createElement("strong");
      totalValue.textContent = total;
      const deltaValue = document.createElement("small");
      deltaValue.textContent = delta;
      totalWrap.append(totalValue, deltaValue);
      row.append(labelWrap, totalWrap);
      summaryList.append(row);
    });
  };
  window.renderWhatIfSummary = () => renderSummary(latestScenarios, latestBaseline);

  const selectedOption = (value) => {
    const needle = normalize(value);
    if (!needle) {
      return null;
    }

    const exact = priceOptions.find((option) => {
      const candidates = [
        optionValue(option),
        option.key,
        option.label,
        option.model,
        option.provider_name,
      ];
      return candidates.some((candidate) => normalize(candidate || "") === needle);
    });
    if (exact) {
      return exact;
    }

    return priceOptions.find((option) => normalize(option.search_text || "").includes(needle));
  };

  const updateFromApi = async (keys = null) => {
    if (!apiUrl) {
      return;
    }

    setCount("Loading");
    setMessage("");
    renderStatusRow("Loading comparisons...");

    const url = new URL(apiUrl, window.location.origin);
    if (keys) {
      keys.forEach((key) => url.searchParams.append("key", key));
    }

    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error(`What-if API returned ${response.status}`);
      }
      const data = await response.json();
      priceOptions = Array.isArray(data.options) ? data.options : [];
      selectedKeys = Array.isArray(data.selected_keys) ? data.selected_keys : [];
      const scenarios = Array.isArray(data.scenarios) ? data.scenarios : [];
      latestScenarios = scenarios;
      latestBaseline = data.baseline || null;
      renderOptions();
      renderScenarios(scenarios);
      renderSummary(scenarios, latestBaseline);
      setCount(`${data.compared_count || 0} compared`);
      setMessage(data.message || "");
    } catch (_error) {
      setCount("Unavailable");
      setMessage("Could not load what-if comparisons.");
      renderStatusRow("What-if comparisons are unavailable.", "empty error-text");
    }
  };

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const option = selectedOption(input?.value || "");
    if (!option) {
      setMessage("Choose an active model price to compare.");
      return;
    }
    if (selectedKeys.includes(option.key)) {
      setMessage(`${option.label} is already compared.`);
      if (input) {
        input.value = "";
      }
      return;
    }
    if (input) {
      input.value = "";
    }
    updateFromApi([...selectedKeys, option.key]);
  });

  scenariosBody?.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest("[data-key]");
    if (!button || !button.classList.contains("what-if-remove")) {
      return;
    }
    const nextKeys = selectedKeys.filter((key) => key !== button.dataset.key);
    selectedKeys = nextKeys;
    setMessage("");
    setCount(`${nextKeys.length} compared`);
    if (!nextKeys.length) {
      renderScenarios([]);
      return;
    }
    updateFromApi(nextKeys);
  });

  updateFromApi();
}

const confirmWithModal = (message) => new Promise((resolve) => {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";

  const modal = document.createElement("div");
  modal.className = "modal";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "confirm-action-title");

  const title = document.createElement("h3");
  title.id = "confirm-action-title";
  title.textContent = "Confirm action";

  const copy = document.createElement("p");
  copy.textContent = message;

  const actions = document.createElement("div");
  actions.className = "modal-actions";

  const cancel = document.createElement("button");
  cancel.className = "button ghost";
  cancel.type = "button";
  cancel.textContent = "Cancel";

  const confirm = document.createElement("button");
  confirm.className = "button danger";
  confirm.type = "button";
  confirm.textContent = "Delete";

  const close = (value) => {
    document.removeEventListener("keydown", onKeyDown);
    overlay.remove();
    resolve(value);
  };

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      close(false);
    }
  };

  cancel.addEventListener("click", () => close(false));
  confirm.addEventListener("click", () => close(true));
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      close(false);
    }
  });
  document.addEventListener("keydown", onKeyDown);

  actions.append(cancel, confirm);
  modal.append(title, copy, actions);
  overlay.append(modal);
  document.body.append(overlay);
  cancel.focus();
});

document.querySelectorAll("[data-confirm-message]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    if (form.dataset.confirmed === "yes") {
      delete form.dataset.confirmed;
      return;
    }
    event.preventDefault();
    const message = form.dataset.confirmMessage || "Continue with this action?";
    if (await confirmWithModal(message)) {
      form.dataset.confirmed = "yes";
      form.submit();
    }
  });
});

document.querySelectorAll("[data-enable-danger]").forEach((checkbox) => {
  const form = checkbox.closest("form");
  const button = form?.querySelector("[data-danger-submit]");
  const update = () => {
    if (button) {
      button.disabled = !checkbox.checked;
    }
  };
  checkbox.addEventListener("change", update);
  update();
});

document.querySelectorAll("[data-fix-picker]").forEach((form) => {
  const target = form.querySelector("[data-fix-target]");
  const manual = form.querySelector("[data-fix-manual]");
  const checkboxes = Array.from(form.querySelectorAll("[data-fix-id]"));

  const syncFromChecks = () => {
    const value = checkboxes
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => checkbox.value)
      .join("\n");
    if (target) {
      target.value = value;
    }
    if (manual) {
      manual.value = value;
    }
  };

  const syncFromManual = () => {
    if (target && manual) {
      target.value = manual.value;
    }
  };

  checkboxes.forEach((checkbox) => checkbox.addEventListener("change", syncFromChecks));
  manual?.addEventListener("input", syncFromManual);
  form.addEventListener("submit", syncFromManual);
});

const applyTableFilters = (tableId) => {
  const table = document.getElementById(tableId);
  if (!table) {
    return;
  }

  const search = document.querySelector(`[data-table-filter="${tableId}"]`)?.value
    .trim()
    .toLowerCase() || "";
  const status = document.querySelector(`[data-table-status-filter="${tableId}"]`)?.value || "";
  const provider = document.querySelector(`[data-table-provider-filter="${tableId}"]`)?.value || "";
  const currency = document.querySelector(`[data-table-currency-filter="${tableId}"]`)?.value || "";

  table.querySelectorAll("tbody tr").forEach((row) => {
    const text = (row.dataset.searchText || row.textContent || "").toLowerCase();
    const matchesSearch = !search || text.includes(search);
    const matchesStatus = !status || row.dataset.status === status;
    const matchesProvider = !provider || row.dataset.provider === provider;
    const matchesCurrency = !currency || row.dataset.currency === currency;
    row.hidden = !(matchesSearch && matchesStatus && matchesProvider && matchesCurrency);
  });
};

document.querySelectorAll("[data-table-filter], [data-table-status-filter], [data-table-provider-filter], [data-table-currency-filter]").forEach((control) => {
  const tableId = control.dataset.tableFilter
    || control.dataset.tableStatusFilter
    || control.dataset.tableProviderFilter
    || control.dataset.tableCurrencyFilter;
  control.addEventListener("input", () => applyTableFilters(tableId));
  control.addEventListener("change", () => applyTableFilters(tableId));
});

document.querySelectorAll("[data-pricing-catalog]").forEach((panel) => {
  const previewUrl = panel.dataset.previewUrl;
  const applyUrl = panel.dataset.applyUrl;
  const form = panel.querySelector("[data-pricing-catalog-form]");
  const tbody = panel.querySelector("[data-pricing-catalog-rows]");
  const message = panel.querySelector("[data-pricing-catalog-message]");
  const applyButton = panel.querySelector("[data-pricing-catalog-apply]");
  let previewItems = [];

  const setCatalogMessage = (text, isError = false) => {
    if (!message) {
      return;
    }
    message.textContent = text || "";
    message.hidden = !text;
    message.classList.toggle("error-text", isError);
  };

  const catalogPayload = () => ({
    source: form?.querySelector("[name='source']")?.value || "huggingface-router",
    search: form?.querySelector("[name='search']")?.value || "",
    limit: form?.querySelector("[name='limit']")?.value || "25",
    include_base_rows: Boolean(form?.querySelector("[name='include_base_rows']")?.checked),
    include_provider_rows: Boolean(form?.querySelector("[name='include_provider_rows']")?.checked),
    reprice_missing: Boolean(form?.querySelector("[name='reprice_missing']")?.checked),
  });

  const selectedCatalogKeys = () => Array.from(
    panel.querySelectorAll("[data-pricing-catalog-key]:checked"),
  ).map((checkbox) => checkbox.value);

  const updateCatalogApplyState = () => {
    if (applyButton) {
      applyButton.disabled = selectedCatalogKeys().length === 0;
    }
  };

  const appendCatalogCell = (row, text) => {
    const cell = document.createElement("td");
    cell.textContent = text || "-";
    row.append(cell);
    return cell;
  };

  const renderCatalogStatus = (row, status) => {
    const cell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `status-badge status-${(status || "unknown").replaceAll("_", "-")}`;
    badge.textContent = status || "unknown";
    cell.append(badge);
    row.append(cell);
  };

  const renderCatalogRows = (items) => {
    if (!tbody) {
      return;
    }
    tbody.replaceChildren();
    previewItems = Array.isArray(items) ? items : [];
    if (!previewItems.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.className = "empty";
      cell.colSpan = 10;
      cell.textContent = "No catalog pricing rows matched.";
      row.append(cell);
      tbody.append(row);
      updateCatalogApplyState();
      return;
    }

    previewItems.forEach((item) => {
      const row = document.createElement("tr");
      const selectCell = document.createElement("td");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = item.key || "";
      checkbox.checked = Boolean(item.selected);
      checkbox.dataset.pricingCatalogKey = item.key || "";
      checkbox.setAttribute("aria-label", `Apply ${item.display_name || item.model}`);
      checkbox.addEventListener("change", updateCatalogApplyState);
      selectCell.append(checkbox);
      row.append(selectCell);

      renderCatalogStatus(row, item.status);

      const modelCell = document.createElement("td");
      const model = document.createElement("code");
      model.textContent = item.model || "-";
      const name = document.createElement("small");
      name.textContent = item.display_name || "";
      modelCell.append(model, name);
      row.append(modelCell);

      appendCatalogCell(row, item.external_provider || item.row_kind);
      appendCatalogCell(row, item.display?.input_usd_per_million);
      appendCatalogCell(row, item.display?.cached_input_usd_per_million);
      appendCatalogCell(row, item.display?.output_usd_per_million);
      appendCatalogCell(row, item.display?.context_length);
      appendCatalogCell(row, item.display?.supports_tools);
      appendCatalogCell(row, item.checked_at);
      tbody.append(row);
    });
    updateCatalogApplyState();
  };

  const postCatalog = async (url, payload) => {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Pricing catalog returned ${response.status}`);
    }
    return data;
  };

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!previewUrl) {
      return;
    }
    setCatalogMessage("Loading catalog...");
    renderCatalogRows([]);
    try {
      const data = await postCatalog(previewUrl, catalogPayload());
      renderCatalogRows(data.items || []);
      setCatalogMessage(
        `${data.total || 0} rows: ${data.counts?.new || 0} new, ${data.counts?.update || 0} updates, ${data.counts?.unchanged || 0} unchanged.`,
      );
    } catch (error) {
      renderCatalogRows([]);
      setCatalogMessage(error.message || "Catalog preview failed.", true);
    }
  });

  applyButton?.addEventListener("click", async () => {
    if (!applyUrl) {
      return;
    }
    const keys = selectedCatalogKeys();
    if (!keys.length) {
      setCatalogMessage("Choose at least one catalog row to apply.", true);
      return;
    }
    const payload = { ...catalogPayload(), keys };
    applyButton.disabled = true;
    setCatalogMessage("Applying selected rows...");
    try {
      const data = await postCatalog(applyUrl, payload);
      renderCatalogRows(data.preview?.items || previewItems);
      setCatalogMessage(
        `${data.applied || 0} applied: ${data.created || 0} created, ${data.updated || 0} updated, ${data.unchanged || 0} unchanged. ${data.repriced_missing || 0} missing-cost requests repriced.`,
      );
      window.dispatchEvent(new Event("settings:refresh"));
    } catch (error) {
      setCatalogMessage(error.message || "Catalog apply failed.", true);
      updateCatalogApplyState();
    }
  });

  updateCatalogApplyState();
});

const closeEnhancedSelects = (except = null) => {
  document.querySelectorAll(".enhanced-select").forEach((wrapper) => {
    if (wrapper === except) {
      return;
    }
    const button = wrapper.querySelector(".enhanced-select-button");
    const menu = wrapper.querySelector(".enhanced-select-menu");
    button?.setAttribute("aria-expanded", "false");
    if (menu) {
      menu.hidden = true;
      menu.classList.remove("opens-up");
    }
  });
};

const activeEnhancedOption = (wrapper) => wrapper.querySelector(".enhanced-select-option.is-active");

const setEnhancedActiveOption = (wrapper, index) => {
  const options = Array.from(wrapper.querySelectorAll(".enhanced-select-option"));
  if (!options.length) {
    return;
  }
  const nextIndex = Math.max(0, Math.min(index, options.length - 1));
  options.forEach((option) => option.classList.remove("is-active"));
  options[nextIndex].classList.add("is-active");
  options[nextIndex].scrollIntoView({ block: "nearest" });
};

const updateEnhancedSelectLabel = (wrapper) => {
  const select = wrapper.querySelector("select");
  const label = wrapper.querySelector(".button-label");
  if (!select || !label) {
    return;
  }
  label.textContent = select.selectedOptions[0]?.textContent?.trim() || "Select provider";
  wrapper.querySelectorAll(".enhanced-select-option").forEach((option) => {
    const selected = option.dataset.value === select.value;
    option.setAttribute("aria-selected", selected ? "true" : "false");
    option.classList.toggle("is-active", selected);
  });
};

const openEnhancedSelect = (wrapper) => {
  closeEnhancedSelects(wrapper);
  const button = wrapper.querySelector(".enhanced-select-button");
  const menu = wrapper.querySelector(".enhanced-select-menu");
  if (!button || !menu) {
    return;
  }
  menu.hidden = false;
  button.setAttribute("aria-expanded", "true");
  const buttonRect = button.getBoundingClientRect();
  const roomBelow = window.innerHeight - buttonRect.bottom;
  menu.classList.toggle("opens-up", roomBelow < Math.min(260, menu.scrollHeight + 20));
  if (!activeEnhancedOption(wrapper)) {
    setEnhancedActiveOption(wrapper, 0);
  }
};

const closeEnhancedSelect = (wrapper, focusButton = false) => {
  const button = wrapper.querySelector(".enhanced-select-button");
  const menu = wrapper.querySelector(".enhanced-select-menu");
  button?.setAttribute("aria-expanded", "false");
  if (menu) {
    menu.hidden = true;
    menu.classList.remove("opens-up");
  }
  if (focusButton) {
    button?.focus();
  }
};

const selectEnhancedOption = (wrapper, option) => {
  const select = wrapper.querySelector("select");
  if (!select || !option) {
    return;
  }
  select.value = option.dataset.value || "";
  select.dispatchEvent(new Event("change", { bubbles: true }));
  updateEnhancedSelectLabel(wrapper);
  closeEnhancedSelect(wrapper, true);
};

const moveEnhancedSelect = (wrapper, direction) => {
  const options = Array.from(wrapper.querySelectorAll(".enhanced-select-option"));
  const current = options.indexOf(activeEnhancedOption(wrapper));
  const fallback = direction > 0 ? -1 : options.length;
  setEnhancedActiveOption(wrapper, (current === -1 ? fallback : current) + direction);
};

const rebuildEnhancedSelectMenu = (wrapper) => {
  const select = wrapper.querySelector("select");
  const menu = wrapper.querySelector(".enhanced-select-menu");
  if (!select || !menu) {
    return;
  }
  menu.replaceChildren();
  Array.from(select.options).forEach((nativeOption) => {
    const option = document.createElement("button");
    option.type = "button";
    option.className = "enhanced-select-option";
    option.setAttribute("role", "option");
    option.dataset.value = nativeOption.value;
    option.textContent = nativeOption.textContent.trim();
    option.addEventListener("click", () => selectEnhancedOption(wrapper, option));
    option.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveEnhancedSelect(wrapper, 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        moveEnhancedSelect(wrapper, -1);
      } else if (event.key === "Home") {
        event.preventDefault();
        setEnhancedActiveOption(wrapper, 0);
      } else if (event.key === "End") {
        event.preventDefault();
        setEnhancedActiveOption(
          wrapper,
          menu.querySelectorAll(".enhanced-select-option").length - 1,
        );
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectEnhancedOption(wrapper, activeEnhancedOption(wrapper) || option);
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeEnhancedSelect(wrapper, true);
      }
    });
    menu.append(option);
  });
  updateEnhancedSelectLabel(wrapper);
};

document.querySelectorAll("select[data-enhanced-select]").forEach((select, index) => {
  const wrapper = document.createElement("div");
  wrapper.className = "enhanced-select";
  wrapper.dataset.enhancedSelectFor = select.name || `enhanced-select-${index}`;
  select.parentNode.insertBefore(wrapper, select);
  wrapper.append(select);
  select.classList.add("native-select");

  const button = document.createElement("button");
  const menu = document.createElement("div");
  const label = document.createElement("span");
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  const menuId = `enhanced-select-menu-${index}`;

  button.type = "button";
  button.className = "enhanced-select-button";
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", menuId);
  label.className = "button-label";
  icon.setAttribute("class", "ui-icon");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("fill", "none");
  icon.setAttribute("stroke", "currentColor");
  icon.setAttribute("stroke-width", "2");
  icon.setAttribute("stroke-linecap", "round");
  icon.setAttribute("stroke-linejoin", "round");
  icon.setAttribute("aria-hidden", "true");
  path.setAttribute("d", "m6 9 6 6 6-6");
  icon.append(path);
  button.append(label, icon);

  menu.id = menuId;
  menu.className = "enhanced-select-menu";
  menu.setAttribute("role", "listbox");
  menu.setAttribute("aria-label", select.dataset.enhancedSelectLabel || select.name || "Options");
  menu.hidden = true;

  button.addEventListener("click", () => {
    if (menu.hidden) {
      openEnhancedSelect(wrapper);
      return;
    }
    closeEnhancedSelect(wrapper);
  });
  button.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && !menu.hidden) {
      event.preventDefault();
      selectEnhancedOption(wrapper, activeEnhancedOption(wrapper));
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      openEnhancedSelect(wrapper);
      moveEnhancedSelect(wrapper, 1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openEnhancedSelect(wrapper);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openEnhancedSelect(wrapper);
      moveEnhancedSelect(wrapper, -1);
    } else if (event.key === "Escape") {
      closeEnhancedSelect(wrapper);
    }
  });
  select.addEventListener("change", () => updateEnhancedSelectLabel(wrapper));
  wrapper.append(button, menu);
  rebuildEnhancedSelectMenu(wrapper);
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".enhanced-select")) {
    closeEnhancedSelects();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeEnhancedSelects();
  }
});

const setFieldValue = (form, selector, value) => {
  const field = form.querySelector(selector);
  if (!field) {
    return;
  }
  if (field.type === "checkbox") {
    field.checked = value === "yes" || value === "true" || value === true;
    return;
  }
  field.value = value || "";
};

document.querySelectorAll("[data-route-row]").forEach((row) => {
  row.addEventListener("click", (event) => {
    if (event.target.closest("button, a, form, input, select, textarea")) {
      return;
    }
    const form = document.querySelector("[data-route-editor]");
    if (!form || !row.dataset.routeId) {
      return;
    }
    document.querySelectorAll("[data-route-row]").forEach((item) => item.classList.remove("is-selected"));
    row.classList.add("is-selected");
    setFieldValue(form, "[data-route-editor-field='route_id']", row.dataset.routeId);
    setFieldValue(form, "[data-route-editor-field='model']", row.dataset.routeModel);
    setFieldValue(form, "[data-route-editor-field='match_type']", row.dataset.routeMatchType);
    setFieldValue(form, "[data-route-editor-field='upstream_url']", row.dataset.routeUpstreamUrl);
    setFieldValue(form, "[data-route-editor-field='upstream_model']", row.dataset.routeUpstreamModel);
    setFieldValue(form, "[data-route-editor-field='provider_slug']", row.dataset.routeProvider);
    setFieldValue(form, "[data-route-editor-field='api_key_env']", row.dataset.routeApiKeyEnv);
    setFieldValue(form, "[data-route-editor-field='fixes']", row.dataset.routeFixes);
    setFieldValue(form, "[data-route-editor-field='priority']", row.dataset.routePriority || "50");
    setFieldValue(form, "[data-route-editor-field='active']", row.dataset.routeActive);
    setFieldValue(form, "[data-route-editor-field='override_fallback']", row.dataset.routeOverrideFallback);
  });
});

document.querySelector("[data-clear-route-editor]")?.addEventListener("click", () => {
  const form = document.querySelector("[data-route-editor]");
  if (!form) {
    return;
  }
  form.reset();
  setFieldValue(form, "[data-route-editor-field='route_id']", "");
  setFieldValue(form, "[data-route-editor-field='priority']", "50");
  document.querySelectorAll("[data-route-row]").forEach((item) => item.classList.remove("is-selected"));
});

document.querySelectorAll("[data-provider-row]").forEach((row) => {
  row.addEventListener("click", (event) => {
    if (event.target.closest("button, a, form, input, select, textarea")) {
      return;
    }
    const form = document.querySelector("[data-provider-editor]");
    if (!form) {
      return;
    }
    document.querySelectorAll("[data-provider-row]").forEach((item) => item.classList.remove("is-selected"));
    row.classList.add("is-selected");
    setFieldValue(form, "[data-provider-editor-field='slug']", row.dataset.providerSlug);
    setFieldValue(form, "[data-provider-editor-field='name']", row.dataset.providerName);
    setFieldValue(form, "[data-provider-editor-field='upstream_url']", row.dataset.providerUrl);
    setFieldValue(form, "[data-provider-editor-field='currency']", row.dataset.providerCurrency || "USD");
    setFieldValue(form, "[data-provider-editor-field='api_key_env']", row.dataset.providerApiKeyEnv);
    setFieldValue(form, "[data-provider-editor-field='active']", row.dataset.providerActive);
    setFieldValue(form, "[data-provider-editor-field='is_default_fallback']", row.dataset.providerDefault);
    setFieldValue(form, "[data-provider-editor-field='capability_text']", row.dataset.providerText);
    setFieldValue(form, "[data-provider-editor-field='capability_vision']", row.dataset.providerVision);
    setFieldValue(form, "[data-provider-editor-field='capability_tool_calling']", row.dataset.providerToolCalling);
  });
});

document.querySelector("[data-clear-provider-editor]")?.addEventListener("click", () => {
  const form = document.querySelector("[data-provider-editor]");
  if (!form) {
    return;
  }
  form.reset();
  document.querySelectorAll("[data-provider-row]").forEach((item) => item.classList.remove("is-selected"));
});

document.querySelectorAll("[data-route-simulator]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = form.parentElement.querySelector("[data-route-simulator-result]");
    const sampleResult = form.parentElement.querySelector("[data-route-sample-result]");
    const model = form.querySelector("input[name='model']")?.value || "";
    if (result) {
      result.textContent = "Running simulation...";
    }
    if (sampleResult) {
      sampleResult.textContent = "Building sample request...";
    }
    try {
      const response = await fetch("/admin/api/routes/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ model }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Simulation returned ${response.status}`);
      }
      if (result) {
        result.replaceChildren();
        const status = document.createElement("strong");
        status.textContent = data.status || "unknown";
        const route = document.createElement("span");
        route.textContent = `Route: ${data.matched_route || (data.upstream_model ? "model fallback" : "pass-through upstream")}`;
        const upstream = document.createElement("code");
        upstream.textContent = `${data.upstream_url || "-"} -> ${data.upstream_model || "-"}`;
        const provider = document.createElement("span");
        provider.textContent = `Provider: ${data.provider_name || data.provider_slug || "-"}`;
        result.append(status, route, upstream, provider);
      }
      if (sampleResult) {
        sampleResult.replaceChildren();
        const title = document.createElement("strong");
        title.textContent = "Sample request";
        const curl = document.createElement("pre");
        curl.textContent = data.sample_request?.curl || "No sample available.";
        const preview = document.createElement("pre");
        preview.textContent = JSON.stringify(data.sample_request?.upstream_preview || {}, null, 2);
        sampleResult.append(title, curl, preview);
      }
    } catch (error) {
      if (result) {
        result.textContent = error.message || "Simulation failed.";
      }
      if (sampleResult) {
        sampleResult.textContent = "";
      }
    }
  });
});

document.querySelectorAll("[data-model-route-lookup]").forEach((form) => {
  const input = form.querySelector("[data-model-lookup-input]");
  const options = form.querySelector("[data-model-lookup-options]");
  const result = form.parentElement.querySelector("[data-model-lookup-result]");
  let suggestionTimer = null;

  const renderLookup = (data) => {
    if (!result) {
      return;
    }
    result.replaceChildren();
    const status = document.createElement("strong");
    status.textContent = data.status || "unknown";
    const route = document.createElement("span");
    route.textContent = `Route: ${data.route || (data.upstream_model ? "model fallback" : "pass-through upstream")}`;
    const upstream = document.createElement("code");
    upstream.textContent = `${data.upstream_url || "-"} -> ${data.upstream_model || "-"}`;
    const provider = document.createElement("span");
    provider.textContent = `Provider: ${data.provider_name || data.provider_slug || "-"}`;
    const keyState = document.createElement("span");
    keyState.textContent = `API key: ${data.api_key_state || "-"}`;
    const sample = document.createElement("pre");
    sample.textContent = data.sample_request?.curl || "No sample request available.";
    result.append(status, route, upstream, provider, keyState, sample);
  };

  const refreshSuggestions = async () => {
    if (!input || !options) {
      return;
    }
    const query = input.value.trim();
    if (!query) {
      options.replaceChildren();
      return;
    }
    try {
      const response = await fetch(`/api/models/suggest?q=${encodeURIComponent(query)}&limit=10`, {
        headers: { Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Suggestions returned ${response.status}`);
      }
      options.replaceChildren();
      (data.items || []).forEach((item) => {
        const option = document.createElement("option");
        option.value = item.client_model || item.model || "";
        option.label = [item.provider_name || item.provider_slug, item.source].filter(Boolean).join(" / ");
        options.append(option);
      });
    } catch {
      options.replaceChildren();
    }
  };

  input?.addEventListener("input", () => {
    window.clearTimeout(suggestionTimer);
    suggestionTimer = window.setTimeout(refreshSuggestions, 160);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const model = input?.value.trim() || "";
    if (!model) {
      return;
    }
    if (result) {
      result.textContent = "Looking up route...";
    }
    try {
      const response = await fetch(`/api/models/lookup?model=${encodeURIComponent(model)}`, {
        headers: { Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Lookup returned ${response.status}`);
      }
      renderLookup(data);
    } catch (error) {
      if (result) {
        result.textContent = error.message || "Lookup failed.";
      }
    }
  });
});

document.querySelectorAll("[data-default-routes]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const action = submitter?.dataset.defaultRouteAction || "preview";
    const result = form.parentElement.querySelector("[data-default-routes-result]");
    const provider = form.querySelector("select[name='provider_slug']")?.value || "";
    const mode = form.querySelector("select[name='mode']")?.value || "missing_only";
    if (result) {
      result.textContent = action === "apply" ? "Applying default routes..." : "Previewing default routes...";
    }
    try {
      const response = await fetch(`/admin/api/routes/defaults/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ provider_slug: provider, mode }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Default route ${action} returned ${response.status}`);
      }
      if (result) {
        result.replaceChildren();
        const status = document.createElement("strong");
        status.textContent = action === "apply" ? "Default routes applied" : "Default route preview";
        const counts = document.createElement("span");
        counts.textContent = [
          `${data.total_candidates || 0} candidates`,
          `${data.inserted || 0} insert`,
          `${data.updated || 0} update`,
          `${data.skipped_existing || 0} existing`,
          `${data.skipped_user || 0} user-owned`,
        ].join(" · ");
        const note = document.createElement("span");
        note.className = "muted";
        note.textContent = data.truncated ? "Showing first 200 route decisions." : "Route decisions are complete.";
        result.append(status, counts, note);
      }
      if (action === "apply") {
        window.dispatchEvent(new Event("settings:refresh"));
      }
    } catch (error) {
      if (result) {
        result.textContent = error.message || "Default route action failed.";
      }
    }
  });
});

document.querySelectorAll("[data-provider-health]").forEach((button) => {
  button.addEventListener("click", async () => {
    const tables = document.querySelectorAll("[data-provider-health-table] tbody");
    const originalMarkup = button.innerHTML;
    button.disabled = true;
    button.textContent = "Checking...";
    try {
      const response = await fetch("/admin/api/providers/health-checks", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      const rows = await response.json();
      if (!response.ok) {
        throw new Error(`Health checks returned ${response.status}`);
      }
      tables.forEach((tbody) => {
        tbody.replaceChildren();
        rows.forEach((item) => {
          const row = document.createElement("tr");
          [item.provider_slug, item.checked_at || "now", item.latency_ms ?? "-", item.auth_state || "-", item.status || "-"].forEach((value) => {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.append(cell);
          });
          tbody.append(row);
        });
      });
      window.dispatchEvent(new Event("settings:refresh"));
    } catch (_error) {
      window.alert("Provider health checks are unavailable.");
    } finally {
      button.disabled = false;
      button.innerHTML = originalMarkup;
    }
  });
});

const liveRoot = document.querySelector("[data-live-page]");

const valueOrDash = (value) => {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
};

const createNode = (tagName, attributes = {}, children = []) => {
  const element = document.createElement(tagName);
  Object.entries(attributes).forEach(([key, value]) => {
    if (value === false || value === null || value === undefined) {
      return;
    }
    if (key === "className") {
      element.className = value;
      return;
    }
    if (key === "textContent") {
      element.textContent = value;
      return;
    }
    if (key === "html") {
      element.innerHTML = value;
      return;
    }
    element.setAttribute(key, value === true ? "" : value);
  });
  children.forEach((child) => {
    if (child === null || child === undefined) {
      return;
    }
    if (typeof child === "string" || typeof child === "number") {
      element.append(document.createTextNode(String(child)));
      return;
    }
    element.append(child);
  });
  return element;
};

const setLiveStatus = (root, text, isError = false) => {
  const status = root?.querySelector("[data-live-status]");
  if (!status) {
    return;
  }
  status.textContent = text || "";
  status.classList.toggle("error-text", isError);
  status.hidden = !text;
};

const localTimeNode = (isoValue, fallback, mode = "full") => {
  const time = createNode("time", {
    className: mode === "table" ? "local-time table-time muted" : "local-time",
    datetime: isoValue || "",
    "data-local-time": mode,
    textContent: fallback || "-",
  });
  if (!isoValue) {
    return time;
  }
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) {
    return time;
  }
  const full = fullDateTime.format(date);
  time.title = fallback ? `${full} (${fallback})` : full;
  if (mode === "table") {
    time.replaceChildren(
      createNode("span", { textContent: tableDate.format(date) }),
      createNode("span", { textContent: tableTime.format(date) }),
    );
    return time;
  }
  if (mode === "mobile") {
    time.textContent = mobileDateTime.format(date);
    return time;
  }
  time.textContent = full;
  return time;
};

const tableCell = (row, content, className = "") => {
  const cell = createNode("td", className ? { className } : {});
  if (Array.isArray(content)) {
    content.forEach((item) => cell.append(item));
  } else if (content instanceof Node) {
    cell.append(content);
  } else {
    cell.textContent = valueOrDash(content);
  }
  row.append(cell);
  return cell;
};

const renderStatusPill = (statusLabel) => createNode("span", {
  className: `pill status-${statusLabel || "pending"}`,
  textContent: statusLabel || "pending",
});

const signalDefinitions = [
  ["stream", "Stream"],
  ["tool", "Tool"],
  ["image", "Image"],
  ["error", "Error"],
  ["slow", "Slow >10s"],
  ["large", "Large"],
];

const renderSignals = (item) => {
  const wrap = createNode("div", { className: "signals" });
  signalDefinitions.forEach(([key, label]) => {
    if (item.signals?.[key]) {
      wrap.append(createNode("span", { className: `signal-${key}`, textContent: label }));
    }
  });
  if (!wrap.children.length) {
    wrap.append(createNode("span", { className: "signal-muted", textContent: "—" }));
  }
  return wrap;
};

const renderTokenTriplet = (tokens) => {
  const wrap = createNode("div", { className: "token-triplet" });
  [
    ["input", tokens?.input_display, tokens?.input_estimated ? "Est. input" : "Input"],
    ["output", tokens?.output_display, "Output"],
    ["total", tokens?.total_display, "Total"],
  ].forEach(([key, display, label]) => {
    const span = createNode("span", {
      className: key === "input" && tokens?.input_estimated ? "estimated-token" : "",
    });
    span.append(
      createNode("strong", {
        textContent: `${key === "input" && tokens?.input_estimated ? "~" : ""}${valueOrDash(display)}`,
      }),
      createNode("small", { textContent: label }),
    );
    wrap.append(span);
  });
  return wrap;
};

const renderCostCell = (item) => {
  const wrap = createNode("div", { className: "cost-cell" });
  wrap.append(createNode("strong", { textContent: valueOrDash(item.cost_display) }));
  if (item.provider_name || item.billing_provider) {
    wrap.append(createNode("span", { className: "muted", textContent: item.provider_name || item.billing_provider }));
  }
  return wrap;
};

const renderRequestSummary = (item) => createNode("div", { className: "request-summary" }, [
  createNode("span", { textContent: item.semantic_summary || item.preview || "—" }),
]);

const renderRequestRows = (tbody, items, showRun, options = {}) => {
  const showSignals = options.showSignals !== false;
  const showSummary = options.showSummary !== false;
  tbody.replaceChildren();
  if (!items.length) {
    const row = createNode("tr");
    const columnCount = 6 + (showRun ? 1 : 0) + (showSignals ? 1 : 0) + (showSummary ? 1 : 0);
    tableCell(row, "No captured requests yet.", "empty").colSpan = columnCount;
    tbody.append(row);
    return;
  }
  items.forEach((item) => {
    const row = createNode("tr", {
      className: "request-row",
      tabindex: "0",
      "data-request-row": true,
      "data-request-id": item.id,
    });
    if (item.signals?.error) {
      row.classList.add("has-error");
    }
    if (item.signals?.slow) {
      row.classList.add("is-slow");
    }
    const requestCell = createNode("td", { className: "request-cell" });
    requestCell.append(
      createNode("strong", { textContent: `#${item.id}` }),
      localTimeNode(item.created_at, item.created_at_table_fallback, "table"),
      createNode("span", { className: "request-endpoint" }, [
        createNode("span", { className: "method", textContent: item.method }),
        createNode("code", { textContent: item.endpoint }),
      ]),
    );
    row.append(requestCell);

    const modelCell = createNode("td", { className: "request-model" });
    modelCell.append(createNode("strong", { textContent: valueOrDash(item.model) }));
    if (item.provider_name || item.billing_provider) {
      modelCell.append(createNode("span", { className: "muted", textContent: item.provider_name || item.billing_provider }));
    }
    if (item.route_name) {
      modelCell.append(createNode("span", { className: "route-badge", textContent: item.route_name }));
    }
    row.append(modelCell);

    if (showRun) {
      const runCell = createNode("td");
      if (item.task_run) {
        runCell.append(createNode("a", {
          className: "run-badge",
          href: `/admin/runs/${item.task_run.id}`,
          textContent: item.task_run.name,
          title: item.task_run.name,
        }));
      } else {
        runCell.append(createNode("span", { className: "muted", textContent: "-" }));
      }
      row.append(runCell);
    }

    tableCell(row, renderStatusPill(item.status_label));
    const duration = item.duration_is_elapsed
      ? createNode("span", {
        className: "elapsed-duration",
        "data-pending-start": item.created_at,
        textContent: `${valueOrDash(item.duration_display)} so far`,
      })
      : item.duration_display;
    tableCell(row, createNode("div", { className: "performance-cell" }, [
      createNode("strong", {}, [duration instanceof Node ? duration : valueOrDash(duration)]),
      createNode("span", { className: "muted", textContent: `${valueOrDash(item.tokens_per_second_display)} TPS` }),
    ]), "numeric");
    tableCell(row, renderTokenTriplet(item.tokens));
    tableCell(row, renderCostCell(item), "numeric");
    if (showSignals) {
      tableCell(row, renderSignals(item), "signals");
    }
    if (showSummary) {
      tableCell(row, renderRequestSummary(item), "request-preview");
    }
    tbody.append(row);
  });
};

const renderPagination = (container, pagination, position = "bottom") => {
  if (!pagination) {
    return;
  }
  const bar = createNode("div", { className: `pagination-bar pagination-${position}` });
  const summary = createNode("span");
  summary.append(
    "Showing ",
    createNode("strong", {
      textContent: `${pagination.display?.start || "0"}-${pagination.display?.end || "0"}`,
    }),
    " of ",
    createNode("strong", { textContent: pagination.display?.total || "0" }),
    createNode("small", { textContent: `${pagination.per_page} per page` }),
  );
  const nav = createNode("nav", {
    className: "pagination-links",
    "aria-label": "Request table pages",
  });
  const pageLink = (label, page, disabled = false, active = false) => {
    const attrs = {
      className: `button ghost compact-button${disabled ? " disabled" : ""}${active ? " active" : ""}`,
      textContent: label,
    };
    if (!disabled) {
      attrs.href = "#";
      attrs["data-live-page-number"] = page;
    }
    return createNode(disabled ? "span" : "a", attrs);
  };
  nav.append(pageLink("Previous", pagination.page - 1, !pagination.has_previous));
  (pagination.pages || []).forEach((page) => {
    nav.append(pageLink(String(page.number), page.number, false, page.current));
  });
  nav.append(pageLink("Next", pagination.page + 1, !pagination.has_next));
  bar.append(summary, nav);
  container.append(bar);
};

const renderMobileRequestList = (items, showRun) => {
  const list = createNode("div", { className: "request-mobile-list" });
  if (!items.length) {
    list.append(createNode("div", { className: "empty-state", textContent: "No captured requests yet." }));
    return list;
  }
  items.forEach((item) => {
    const signalText = signalDefinitions
      .filter(([key]) => item.signals?.[key])
      .map(([, label]) => label.replace(" >10s", "").replace("Large", "Large"))
      .join(" · ");
    const row = createNode("a", { className: "request-mobile-card", href: `/admin/requests/${item.id}` }, [
      createNode("span", { className: "mobile-card-main" }, [
        createNode("span", {}, [
          createNode("strong", { textContent: `#${item.id}` }),
          createNode("span", { textContent: " · " }),
          localTimeNode(item.created_at, item.created_at_table_fallback, "mobile"),
        ]),
        renderStatusPill(item.status_label),
      ]),
      createNode("span", { className: "mobile-card-model" }, [
        createNode("strong", { textContent: valueOrDash(item.model) }),
        createNode("small", { textContent: item.provider_name || item.billing_provider || item.route_name || "-" }),
      ]),
      createNode("span", { className: "mobile-card-metrics" }, [
        createNode("span", { textContent: valueOrDash(item.duration_display) }),
        createNode("span", { textContent: `${valueOrDash(item.tokens_per_second_display)} TPS` }),
        createNode("span", { textContent: valueOrDash(item.cost_display) }),
      ]),
      createNode("span", { className: "mobile-card-foot" }, [
        createNode("span", {
          textContent: `${valueOrDash(item.tokens?.input_display)} in · ${valueOrDash(item.tokens?.output_display)} out · ${valueOrDash(item.tokens?.total_display)} total`,
        }),
        createNode("span", { textContent: signalText || "›" }),
      ]),
    ]);
    if (showRun && item.task_run) {
      row.title = item.task_run.name;
    }
    if (item.signals?.error) {
      row.classList.add("has-error");
    }
    list.append(row);
  });
  return list;
};

const renderRequestsTable = (container, items, pagination, showRun, options = {}) => {
  container.replaceChildren();
  const showSignals = options.showSignals !== false;
  const showSummary = options.showSummary !== false;
  if (!options.compact) {
    container.append(createNode("div", { className: "request-table-controls" }, [
      createNode("button", {
        className: "button ghost compact-button columns-button",
        type: "button",
        textContent: "Columns",
        "aria-disabled": "true",
        title: "Column presets will be added in a future pass.",
      }),
    ]));
    renderPagination(container, pagination, "top");
  }
  const table = createNode("table", { className: "requests-table" });
  const colgroup = createNode("colgroup");
  [
    "col-request",
    "col-model-provider",
    ...(showRun ? ["col-run"] : []),
    "col-status",
    "col-performance",
    "col-tokens",
    "col-cost",
    ...(showSignals ? ["col-signals"] : []),
    ...(showSummary ? ["col-summary"] : []),
  ].forEach((className) => colgroup.append(createNode("col", { className })));
  const thead = createNode("thead");
  const headRow = createNode("tr");
  [
    "Request",
    "Model / Provider",
    ...(showRun ? ["Run"] : []),
    "Status",
    "Performance",
    "Tokens",
    "Cost",
    ...(showSignals ? ["Signals"] : []),
    ...(showSummary ? ["Summary"] : []),
  ]
    .forEach((heading) => headRow.append(createNode("th", { textContent: heading })));
  thead.append(headRow);
  const tbody = createNode("tbody");
  renderRequestRows(tbody, items, showRun, { showSignals, showSummary });
  table.append(colgroup, thead, tbody);
  container.append(table);
  container.append(renderMobileRequestList(items, showRun));
  if (!options.compact) {
    renderPagination(container, pagination);
  }
  updatePendingElapsed();
};

const requestDetailCache = new Map();

const copyText = async (text) => {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.append(area);
  area.select();
  document.execCommand("copy");
  area.remove();
};

const requestDetailForCopy = async (requestId) => {
  if (requestDetailCache.has(requestId)) {
    return requestDetailCache.get(requestId);
  }
  const response = await fetch(`/admin/api/requests/${requestId}?mode=text`, {
    headers: { Accept: "application/json" },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `Request API returned ${response.status}`);
  }
  requestDetailCache.set(requestId, data);
  return data;
};

const shellQuote = (value) => `'${String(value).replaceAll("'", "'\\''")}'`;

const curlFromRequestDetail = (detail) => {
  const record = detail.record;
  const url = new URL(record.path + (record.query_string ? `?${record.query_string}` : ""), window.location.origin);
  const lines = [`curl -X ${shellQuote(record.method || "POST")} ${shellQuote(url.toString())}`];
  let headers = {};
  try {
    headers = JSON.parse(record.request_headers_json || "{}");
  } catch {
    headers = {};
  }
  Object.entries(headers).forEach(([key, value]) => {
    const lower = key.toLowerCase();
    if (["host", "content-length"].includes(lower)) {
      return;
    }
    lines.push(`  -H ${shellQuote(`${key}: ${value}`)}`);
  });
  if (detail.request_render?.text) {
    lines.push(`  --data-binary ${shellQuote(detail.request_render.text)}`);
  }
  return lines.join(" \\\n");
};

const inspectorActionButton = (action, label) => createNode("button", {
  className: "button ghost compact-button",
  type: "button",
  "data-inspector-copy": action,
  textContent: label,
});

const renderRequestInspector = (container, item) => {
  if (!container) {
    return;
  }
  container.replaceChildren();
  if (!item) {
    container.append(createNode("div", { className: "empty-state", textContent: "Select a request to inspect it." }));
    return;
  }
  const signals = renderSignals(item);
  const stats = createNode("div", { className: "inspector-stats" });
  [
    ["Input tokens", item.tokens?.input_display],
    ["Output tokens", item.tokens?.output_display],
    ["Total tokens", item.tokens?.total_display],
    ["Model", item.model],
    ["Provider", item.provider_name || item.billing_provider],
  ].forEach(([label, value]) => {
    stats.append(createNode("span", {}, [
      createNode("small", { textContent: label }),
      createNode("strong", { textContent: valueOrDash(value) }),
    ]));
  });
  const actions = createNode("div", { className: "inspector-actions" }, [
    createNode("a", {
      className: "button primary compact-button",
      href: `/admin/requests/${item.id}`,
      textContent: "Open full details",
    }),
    inspectorActionButton("id", "Copy ID"),
    inspectorActionButton("request", "Copy request JSON"),
    inspectorActionButton("response", "Copy response"),
    inspectorActionButton("curl", "Copy as curl"),
  ]);
  container.append(
    createNode("header", { className: "request-inspector-header" }, [
      createNode("div", {}, [
        createNode("h2", { textContent: `Request #${item.id}` }),
        renderStatusPill(item.status_label),
      ]),
      actions,
    ]),
    createNode("div", { className: "inspector-tabs", "aria-label": "Request inspector sections" }, [
      createNode("span", { className: "active", textContent: "Overview" }),
      createNode("span", { textContent: "Route / Provider" }),
      createNode("span", { textContent: "Tokens" }),
      createNode("span", { textContent: "Preview" }),
    ]),
    createNode("dl", { className: "inspector-fields" }, [
      createNode("dt", { textContent: "Time" }),
      createNode("dd", {}, [localTimeNode(item.created_at, item.created_at_fallback, "full")]),
      createNode("dt", { textContent: "Method" }),
      createNode("dd", { textContent: item.method }),
      createNode("dt", { textContent: "Endpoint" }),
      createNode("dd", { textContent: item.endpoint }),
      createNode("dt", { textContent: "Provider" }),
      createNode("dd", { textContent: item.provider_name || item.billing_provider || "-" }),
      createNode("dt", { textContent: "Route" }),
      createNode("dd", {
        textContent: item.route_name
          || item.model_route
          || (item.upstream_model ? "model fallback" : "pass-through upstream"),
      }),
      createNode("dt", { textContent: "Upstream" }),
      createNode("dd", { textContent: item.upstream_url || "-" }),
      createNode("dt", { textContent: "Forwarded model" }),
      createNode("dd", { textContent: item.upstream_model || item.model || "-" }),
      createNode("dt", { textContent: "Compatibility" }),
      createNode("dd", { textContent: item.compatibility_label || "none" }),
      createNode("dt", { textContent: "Run" }),
      createNode("dd", { textContent: item.task_run?.name || "-" }),
      createNode("dt", { textContent: "Duration" }),
      createNode("dd", { textContent: item.duration_display }),
      createNode("dt", { textContent: "TPS" }),
      createNode("dd", { textContent: item.tokens_per_second_display }),
      createNode("dt", { textContent: "Cost" }),
      createNode("dd", { textContent: `${item.cost_display} (${item.provider_name || item.billing_provider || "no provider"})` }),
    ]),
    createNode("section", { className: "inspector-card" }, [
      createNode("h3", { textContent: "Signals" }),
      signals,
    ]),
    createNode("section", { className: "inspector-card" }, [
      createNode("h3", { textContent: "Summary" }),
      createNode("p", { textContent: item.semantic_summary || item.preview || "-" }),
    ]),
    createNode("section", { className: "inspector-card" }, [
      createNode("h3", { textContent: "Quick stats" }),
      stats,
    ]),
  );
};

const markSelectedRequest = (root, requestId) => {
  root.querySelectorAll("[data-request-row]").forEach((row) => {
    row.classList.toggle("is-selected", String(row.dataset.requestId) === String(requestId));
  });
};

const renderRequestStats = (root, stats) => {
  const container = root.querySelector("[data-live-request-stats]");
  if (!container) {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const chips = [
    ["total", "Total", stats.total?.display],
    ["stream", "Streams", stats.streams?.display],
    ["image", "Images", stats.images?.display],
    ["tool", "Tools", stats.tools?.display],
    ["error", "Errors", stats.errors?.display],
    ["slow", "Slow >10s", stats.slow?.display],
    ["large", "Large >10k tok", stats.large?.display],
  ];
  container.replaceChildren();
  chips.forEach(([key, label, value]) => {
    const active = key !== "total" && params.get(key) === "1";
    container.append(createNode("button", {
      className: `stat-chip${active ? " active" : ""} stat-${key}`,
      type: "button",
      "data-stat-filter": key,
    }, [
      createNode("strong", { textContent: valueOrDash(value) }),
      label,
    ]));
  });
};

const renderRunControl = (container, activeRun, includeNotes) => {
  if (!container) {
    return;
  }
  container.replaceChildren();
  if (activeRun) {
    const copy = createNode("div");
    copy.append(
      createNode("p", { className: "eyebrow", textContent: "Run in progress" }),
      createNode("h2", {}, [
        createNode("a", { href: `/admin/runs/${activeRun.id}`, textContent: activeRun.name }),
      ]),
      createNode("p", {
        className: "muted",
        textContent: `${activeRun.request_count_display} request${activeRun.request_count === 1 ? "" : "s"} · ${activeRun.open_duration_display} open`,
      }),
    );
    const actions = createNode("div", { className: "run-control-actions" });
    actions.append(createNode("a", {
      className: "button ghost compact-button",
      href: `/admin/runs/${activeRun.id}`,
      textContent: "Open",
    }));
    actions.append(createNode("form", {
      method: "post",
      action: "/admin/runs/pause",
      "data-live-run-pause": true,
      "data-api-url": "/admin/api/runs/pause",
    }, [
      createNode("button", {
        className: "button ghost compact-button",
        type: "submit",
        textContent: "Pause",
      }),
    ]));
    const form = createNode("form", {
      method: "post",
      action: "/admin/runs/end",
      "data-live-run-end": true,
      "data-api-url": "/admin/api/runs/end",
    });
    form.append(createNode("button", {
      className: "button danger",
      type: "submit",
      textContent: "End run",
    }));
    actions.append(form);
    container.append(copy, actions);
    return;
  }
  const form = createNode("form", {
    className: "run-start-form",
    method: "post",
    action: "/admin/runs/start",
    "data-live-run-start": true,
    "data-api-url": "/admin/api/runs/start",
  });
  form.append(createNode("label", {}, [
    "Run name",
    createNode("input", {
      name: "name",
      placeholder: "Video processing benchmark",
      required: true,
      "data-live-pause-poll": true,
    }),
  ]));
  if (includeNotes) {
    form.append(createNode("label", {}, [
      "Notes",
      createNode("input", { name: "notes", placeholder: "Optional context", "data-live-pause-poll": true }),
    ]));
  }
  form.append(createNode("button", {
    className: "button primary",
    type: "submit",
    textContent: "Start run",
  }));
  container.append(form);
};

const updateRequestFilterOptions = (root, data) => {
  const modelSelect = root.querySelector("select[name='model']");
  const providerSelect = root.querySelector("select[name='provider']");
  const routeSelect = root.querySelector("select[name='route']");
  const runSelect = root.querySelector("select[name='run']");
  const endpoints = root.querySelector("#endpoints");
  const currentModel = modelSelect?.value || "";
  const currentProvider = providerSelect?.value || "";
  const currentRoute = routeSelect?.value || "";
  const currentRun = runSelect?.value || "";
  if (modelSelect) {
    modelSelect.replaceChildren(createNode("option", { value: "", textContent: "Any model" }));
    (data.models || []).forEach((model) => {
      modelSelect.append(createNode("option", {
        value: model,
        textContent: model,
        selected: model === currentModel,
      }));
    });
  }
  if (providerSelect) {
    providerSelect.replaceChildren(createNode("option", { value: "", textContent: "Any provider" }));
    (data.provider_options || []).forEach((provider) => {
      providerSelect.append(createNode("option", {
        value: provider.value,
        textContent: provider.label,
        selected: provider.value === currentProvider,
      }));
    });
  }
  if (routeSelect) {
    routeSelect.replaceChildren(createNode("option", { value: "", textContent: "Any route" }));
    (data.route_options || []).forEach((route) => {
      routeSelect.append(createNode("option", {
        value: route,
        textContent: route,
        selected: route === currentRoute,
      }));
    });
  }
  if (runSelect) {
    runSelect.replaceChildren(createNode("option", { value: "", textContent: "Any run" }));
    (data.run_options || []).forEach((run) => {
      runSelect.append(createNode("option", {
        value: run.id,
        textContent: run.name,
        selected: String(run.id) === String(currentRun),
      }));
    });
  }
  if (endpoints) {
    endpoints.replaceChildren();
    (data.endpoints || []).forEach((endpoint) => {
      endpoints.append(createNode("option", { value: endpoint }));
    });
  }
};

const syncRequestFormFromUrl = (root) => {
  const form = root.querySelector("[data-live-request-filters]");
  if (!form) {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  ["endpoint", "model", "provider", "route", "run", "status"].forEach((name) => {
    const field = form.elements[name];
    if (field) {
      field.value = params.get(name) || "";
    }
  });
  ["stream", "image", "tool", "error", "slow", "large"].forEach((name) => {
    const field = form.elements[name];
    if (field) {
      field.checked = params.get(name) === "1";
    }
  });
};

const requestQueryFromForm = (form) => {
  const params = new URLSearchParams();
  ["endpoint", "model", "provider", "route", "run", "status"].forEach((name) => {
    const value = form.elements[name]?.value?.trim();
    if (value) {
      params.set(name, value);
    }
  });
  ["stream", "image", "tool", "error", "slow", "large"].forEach((name) => {
    if (form.elements[name]?.checked) {
      params.set(name, "1");
    }
  });
  return params;
};

const apiUrlWithCurrentQuery = (root) => {
  const url = new URL(root.dataset.apiUrl, window.location.origin);
  const params = new URLSearchParams(window.location.search);
  params.forEach((value, key) => url.searchParams.set(key, value));
  return url;
};

const startLivePoller = (root, load) => {
  const interval = Number(root.dataset.pollInterval || "1000");
  let controller = null;
  let inFlight = false;
  let timer = null;

  const schedule = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(refresh, interval);
  };

  const refresh = async ({ replace = false } = {}) => {
    if (document.hidden) {
      schedule();
      return;
    }

    // Pause polling while user is typing in an input that would be destroyed by re-render
    if (document.activeElement?.closest("[data-live-pause-poll]")) {
      schedule();
      return;
    }

    if (inFlight && !replace) {
      return;
    }
    if (inFlight && replace && controller) {
      controller.abort();
    }

    const currentController = new AbortController();
    controller = currentController;
    inFlight = true;
    try {
      await load(currentController.signal);
      setLiveStatus(root, "Live");
    } catch (error) {
      if (error.name !== "AbortError") {
        setLiveStatus(root, "Update failed; showing last data.", true);
      }
    } finally {
      if (controller === currentController) {
        controller = null;
        inFlight = false;
        schedule();
      }
    }
  };
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      refresh({ replace: true });
    }
  });
  window.addEventListener("live:refresh", () => refresh({ replace: true }));
  refresh();
};

const settingsNumber = (value) => new Intl.NumberFormat().format(Number(value || 0));

const settingsMoney = (value) => {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return `$${Number(value).toFixed(6).replace(/0+$/, "").replace(/\.$/, "")}`;
};

const settingsFormPayload = (form, submitter = null) => {
  const payload = {};
  new FormData(form).forEach((value, key) => {
    payload[key] = value;
  });
  if (submitter?.name) {
    payload[submitter.name] = submitter.value;
  }
  return payload;
};

const setSettingsFormMessage = (form, text, isError = false) => {
  const message = form?.querySelector("[data-form-message]");
  if (!message) {
    return;
  }
  message.textContent = text || "";
  message.classList.toggle("error-text", isError);
};

const fillSettingsForm = (form, values) => {
  if (!form || form.dataset.dirty === "yes") {
    return;
  }
  Object.entries(values || {}).forEach(([name, value]) => {
    const fields = [...form.querySelectorAll(`[name="${name}"]`)];
    const checkbox = fields.find((field) => field.type === "checkbox");
    if (checkbox) {
      checkbox.checked = Boolean(value);
      return;
    }
    const field = fields.find((item) => item.type !== "hidden") || fields[0];
    if (field) {
      field.value = value ?? "";
      const wrapper = field.closest?.(".enhanced-select");
      if (wrapper) {
        updateEnhancedSelectLabel(wrapper);
      }
    }
  });
  form.dataset.dirty = "no";
};

const replaceSettingsOptions = (select, rows, emptyLabel = null) => {
  if (!select) {
    return;
  }
  const selected = select.value;
  select.replaceChildren();
  if (emptyLabel !== null) {
    select.append(createNode("option", { value: "", textContent: emptyLabel }));
  }
  (rows || []).forEach((row) => {
    select.append(createNode("option", {
      value: row.slug || row.value || "",
      textContent: row.name || row.label || row.slug || row.value || "",
    }));
  });
  if ([...select.options].some((option) => option.value === selected)) {
    select.value = selected;
  }
  const wrapper = select.closest(".enhanced-select");
  if (wrapper) {
    rebuildEnhancedSelectMenu(wrapper);
  }
};

const appendSettingsCells = (row, values) => {
  values.forEach((value) => row.append(createNode("td", {
    textContent: value === null || value === undefined || value === "" ? "-" : String(value),
  })));
};

const renderSettingsPagination = (root, pagination) => {
  const container = root.querySelector("[data-settings-pagination]");
  if (!container) {
    return;
  }
  container.replaceChildren();
  if (!pagination || pagination.total_pages <= 1) {
    return;
  }
  const previous = createNode("button", {
    className: "button ghost compact-button",
    type: "button",
    "data-settings-page": pagination.page - 1,
    textContent: "Previous",
  });
  previous.disabled = !pagination.has_previous;
  const next = createNode("button", {
    className: "button ghost compact-button",
    type: "button",
    "data-settings-page": pagination.page + 1,
    textContent: "Next",
  });
  next.disabled = !pagination.has_next;
  container.append(createNode("div", { className: "pagination-bar" }, [
    createNode("span", {
      textContent: `Page ${pagination.page} of ${pagination.total_pages} · ${settingsNumber(pagination.total)} rows`,
    }),
    createNode("div", { className: "button-row" }, [previous, next]),
  ]));
};

const renderSettingsSummary = (root, payload) => {
  const container = root.querySelector("[data-settings-summary]");
  if (!container) {
    return;
  }
  const summary = payload.summary || {};
  const upstream = summary.upstream || {};
  const cards = [
    ["IN", "Proxy listener", `${summary.listener?.host || "-"}:${summary.listener?.port || "-"}`, "Admin and proxy port"],
    ["FB", "Model fallback", `${upstream.default_provider_name || "No provider"} / ${upstream.default_model || "No model"}`, "Used for unmatched models"],
    ["RT", "Active routes", settingsNumber(summary.active_routes), `${settingsNumber(summary.active_providers)} active providers`],
    ["DB", "Stored rows", settingsNumber(summary.stored_rows), `${settingsNumber(summary.rows_older_than_retention)} older than ${summary.retention_days} days`],
  ];
  container.replaceChildren(...cards.map(([badge, label, value, detail]) => (
    createNode("article", { className: "summary-card" }, [
      createNode("span", { className: "summary-icon", textContent: badge }),
      createNode("div", { className: "summary-body" }, [
        createNode("span", { className: "summary-label", textContent: label }),
        createNode("strong", { className: "summary-value", textContent: value }),
        createNode("span", { className: "summary-helper", textContent: detail }),
      ]),
    ])
  )));
  const stored = root.querySelector("[data-settings-stored-rows]");
  if (stored) {
    stored.textContent = `${settingsNumber(summary.stored_rows)} stored rows`;
  }
};

const renderSettingsHealth = (root, providers, healthResults) => {
  root.querySelectorAll("[data-settings-provider-health]").forEach((tbody) => {
    tbody.replaceChildren();
    (providers || []).forEach((provider) => {
      const health = healthResults?.[provider.slug] || {};
      const row = createNode("tr");
      appendSettingsCells(row, [
        provider.name,
        health.checked_at || "Not checked",
        health.latency_ms === null || health.latency_ms === undefined
          ? "-"
          : `${health.latency_ms} ms`,
        health.auth_state || provider.api_key_env || "not configured",
        health.status || "warning",
      ]);
      tbody.append(row);
    });
    if (!providers?.length) {
      tbody.append(createNode("tr", {}, [
        createNode("td", {
          className: "empty",
          colspan: "5",
          textContent: "No providers are configured.",
        }),
      ]));
    }
  });
};

const renderSettingsDiagnosticResult = (root, result) => {
  const container = root.querySelector("[data-settings-diagnostic-result]");
  if (!container || !result) {
    return;
  }
  container.replaceChildren(
    createNode("strong", {
      textContent: result.ok ? "Diagnostic succeeded" : "Diagnostic failed",
    }),
    createNode("span", {
      textContent: `${result.kind || "test"} · ${result.status_code || "error"} · ${result.duration_ms || 0} ms`,
    }),
    createNode("code", { textContent: result.url || "-" }),
    result.error
      ? createNode("p", { className: "error-text", textContent: result.error })
      : createNode("pre", { className: "code compact-code", textContent: result.body || "" }),
  );
};

const initSettingsLivePage = (root) => {
  const status = root.querySelector("[data-settings-status]");
  const tab = root.dataset.settingsTab;
  let latest = null;
  let controller = null;
  let reading = false;
  let mutating = false;
  let selectedRouteId = null;
  let selectedProviderSlug = null;
  const openPriceIds = new Set();

  const setStatus = (text, isError = false) => {
    if (!status) {
      return;
    }
    status.textContent = text || "";
    status.classList.toggle("error-text", isError);
  };

  const hasDirtyForm = () => Boolean(root.querySelector("[data-settings-action][data-dirty='yes']"));

  const currentApiUrl = () => {
    const url = new URL(root.dataset.apiUrl, window.location.origin);
    new URLSearchParams(window.location.search).forEach((value, key) => {
      url.searchParams.set(key, value);
    });
    return url;
  };

  const renderProviderOptions = (payload) => {
    const providers = payload.options?.providers || [];
    root.querySelectorAll("[data-provider-options]").forEach((select) => {
      const allLabel = select.closest("[data-default-routes]") ? "All providers" : (
        select.name === "provider_slug" && select.closest("#price-editor")
          ? "Choose provider"
          : select.name === "provider_slug" && select.closest("#route-editor")
            ? "Auto by URL"
            : "No provider"
      );
      replaceSettingsOptions(select, providers, allLabel);
    });
    root.querySelectorAll("[data-provider-filter-options]").forEach((select) => {
      replaceSettingsOptions(select, providers, "All providers");
    });
    root.querySelectorAll("[data-currency-options]").forEach((select) => {
      replaceSettingsOptions(
        select,
        (payload.options?.currencies || []).map((currency) => ({
          value: currency,
          label: currency,
        })),
        "All currencies",
      );
    });
  };

  const renderFallbackForms = (payload) => {
    const fallback = payload.data?.fallback || {};
    root.querySelectorAll("[data-settings-action='upstream-defaults']").forEach((form) => {
      fillSettingsForm(form, {
        upstream_url: payload.data?.upstream_url || payload.summary?.upstream?.url || "",
        default_provider_slug: fallback.provider_slug || "",
        default_model: fallback.model || "",
        fallback_enabled: Boolean(fallback.enabled),
      });
    });
  };

  const renderServer = (payload) => {
    fillSettingsForm(root.querySelector("[data-settings-action='listener']"), {
      incoming_port: payload.data.listener?.port,
      expose_all_ips: payload.data.listener?.expose_all_ips,
    });
    const warning = root.querySelector("[data-settings-network-warning]");
    if (warning) {
      warning.hidden = !payload.data.listener?.expose_all_ips;
    }
    renderFallbackForms(payload);
    const fixesForm = root.querySelector("[data-settings-action='compat-fixes']");
    if (fixesForm && fixesForm.dataset.dirty !== "yes") {
      const selected = new Set(payload.data.compatibility_fixes || []);
      const list = fixesForm.querySelector("[data-settings-compat-fixes]");
      list?.replaceChildren(...(payload.options?.compatibility_fixes || []).map((fix) => (
        createNode("label", { className: "check fix-option" }, [
          createNode("input", {
            type: "checkbox",
            value: fix.id,
            "data-fix-id": true,
            checked: selected.has(fix.id),
          }),
          createNode("span", {}, [
            createNode("strong", { textContent: fix.id }),
            createNode("small", { textContent: fix.description }),
          ]),
        ])
      )));
      const text = [...selected].join("\n");
      const target = fixesForm.querySelector("[data-fix-target]");
      const manual = fixesForm.querySelector("[data-fix-manual]");
      if (target) target.value = text;
      if (manual) manual.value = text;
    }
    const routesBody = root.querySelector("[data-settings-recent-routes]");
    routesBody?.replaceChildren();
    (payload.data.recent_routes || []).forEach((route) => {
      const row = createNode("tr");
      appendSettingsCells(row, [
        route.model,
        settingsNumber(route.requests),
        route.matched_route || (route.upstream_model ? "model fallback" : "pass-through"),
        route.provider_name || route.provider_slug || "Auto",
        route.status,
      ]);
      routesBody?.append(row);
    });
    if (routesBody && !payload.data.recent_routes?.length) {
      routesBody.append(createNode("tr", {}, [
        createNode("td", { className: "empty", colspan: "5", textContent: "No recent model traffic." }),
      ]));
    }
    renderRetention(payload);
  };

  const renderRetention = (payload) => {
    const retention = payload.data?.retention;
    if (!retention) {
      return;
    }
    root.querySelectorAll("[data-settings-action='trim']").forEach((form) => {
      fillSettingsForm(form, { days: retention.days });
    });
    root.querySelectorAll("[data-settings-retention-preview]").forEach((copy) => {
      copy.textContent = `Older than ${retention.days} days: ${settingsNumber(retention.rows)} rows will be deleted.`;
    });
  };

  const renderRoutes = (payload) => {
    renderFallbackForms(payload);
    const body = root.querySelector("[data-settings-routes]");
    body?.replaceChildren();
    (payload.data.routes || []).forEach((route) => {
      const row = createNode("tr", {
        className: String(route.id) === String(selectedRouteId) ? "is-selected" : "",
        "data-settings-route-row": route.id || "",
      });
      appendSettingsCells(row, [
        route.model,
        route.match_type,
        route.upstream_url,
        route.upstream_model,
        route.provider_name || route.provider_slug || "Auto",
        route.priority,
        route.status,
      ]);
      const action = createNode("td");
      if (route.editable) {
        action.append(createNode("button", {
          className: "button danger compact-button",
          type: "button",
          "data-settings-delete": "route",
          "data-delete-id": route.id,
          "data-delete-label": route.model,
          textContent: "Delete",
        }));
      } else {
        action.textContent = "Locked";
      }
      row.append(action);
      body?.append(row);
    });
    if (body && !payload.data.routes?.length) {
      body.append(createNode("tr", {}, [
        createNode("td", { className: "empty", colspan: "8", textContent: "No routes matched." }),
      ]));
    }
    const usageBody = root.querySelector("[data-settings-route-usage]");
    usageBody?.replaceChildren();
    (payload.data.usage || []).forEach((item) => {
      const row = createNode("tr");
      appendSettingsCells(row, [item.route, settingsNumber(item.requests_today), item.last_matched_at]);
      usageBody?.append(row);
    });
    if (usageBody && !payload.data.usage?.length) {
      usageBody.append(createNode("tr", {}, [
        createNode("td", { className: "empty", colspan: "3", textContent: "No route matches today." }),
      ]));
    }
  };

  const renderProviders = (payload) => {
    renderFallbackForms(payload);
    const usageBySlug = Object.fromEntries(
      (payload.data.usage || []).map((item) => [item.provider_slug, item]),
    );
    const body = root.querySelector("[data-settings-providers]");
    body?.replaceChildren();
    (payload.data.providers || []).forEach((provider) => {
      const usage = usageBySlug[provider.slug] || {};
      const row = createNode("tr", {
        className: provider.slug === selectedProviderSlug ? "is-selected" : "",
        "data-settings-provider-row": provider.slug,
      });
      appendSettingsCells(row, [
        provider.name,
        provider.slug,
        provider.upstream_url,
        provider.currency,
        provider.status,
        `${settingsNumber(provider.model_count)} models / ${settingsNumber(usage.active_routes || provider.route_count)} routes`,
      ]);
      row.append(createNode("td", {}, [
        createNode("button", {
          className: "button danger compact-button",
          type: "button",
          "data-settings-delete": "provider",
          "data-delete-id": provider.slug,
          "data-delete-label": provider.name,
          textContent: "Delete",
        }),
      ]));
      body?.append(row);
    });
    if (body && !payload.data.providers?.length) {
      body.append(createNode("tr", {}, [
        createNode("td", { className: "empty", colspan: "7", textContent: "No providers matched." }),
      ]));
    }
    renderSettingsHealth(root, payload.options?.providers, payload.data.health_results);
  };

  const tierForm = (price) => createNode("form", {
    className: "tier-form",
    method: "post",
    action: "/admin/settings/model-price-tiers",
    "data-settings-action": "tier-save",
  }, [
    createNode("input", { type: "hidden", name: "price_id", value: price.id }),
    createNode("label", {}, [createNode("span", { textContent: "Label" }), createNode("input", { name: "label" })]),
    createNode("label", {}, [createNode("span", { textContent: "Min tokens" }), createNode("input", { name: "min_input_tokens", type: "number", min: "0" })]),
    createNode("label", {}, [createNode("span", { textContent: "Max tokens" }), createNode("input", { name: "max_input_tokens", type: "number", min: "1" })]),
    createNode("label", {}, [createNode("span", { textContent: "Input / 1M" }), createNode("input", { name: "input_usd_per_million", type: "number", min: "0", step: "0.000001", required: true })]),
    createNode("label", {}, [createNode("span", { textContent: "Cached / 1M" }), createNode("input", { name: "cached_input_usd_per_million", type: "number", min: "0", step: "0.000001" })]),
    createNode("label", {}, [createNode("span", { textContent: "Output / 1M" }), createNode("input", { name: "output_usd_per_million", type: "number", min: "0", step: "0.000001", required: true })]),
    createNode("button", { className: "button ghost compact-button", type: "submit", textContent: "Add tier" }),
    createNode("p", { className: "form-message", "data-form-message": true, "aria-live": "polite" }),
  ]);

  const renderPrices = (payload) => {
    const body = root.querySelector("[data-settings-prices]");
    body?.replaceChildren();
    (payload.data.prices || []).forEach((price) => {
      const row = createNode("tr", { "data-settings-price-row": price.id });
      appendSettingsCells(row, [
        price.provider_name,
        price.model,
        price.display_name,
        settingsMoney(price.input_usd_per_million),
        settingsMoney(price.cached_input_usd_per_million),
        settingsMoney(price.output_usd_per_million),
        (price.aliases || []).join(", "),
      ]);
      const tierCell = createNode("td");
      const details = createNode("details", {
        className: "tier-drawer",
        "data-price-details": price.id,
      });
      details.open = openPriceIds.has(String(price.id));
      details.append(createNode("summary", {
        textContent: `${price.tiers?.length || 0} tier${price.tiers?.length === 1 ? "" : "s"}`,
      }));
      (price.tiers || []).forEach((tier) => {
        details.append(createNode("div", { className: "tier-row" }, [
          createNode("span", {
            textContent: `${tier.label || tier.range}: ${settingsMoney(tier.input_usd_per_million)} / ${settingsMoney(tier.output_usd_per_million)}`,
          }),
          createNode("button", {
            className: "button danger compact-button",
            type: "button",
            "data-settings-delete": "tier",
            "data-delete-id": tier.id,
            "data-delete-label": tier.label || tier.range,
            textContent: "Delete",
          }),
        ]));
      });
      details.append(tierForm(price));
      tierCell.append(details);
      row.append(tierCell);
      appendSettingsCells(row, [price.status]);
      row.append(createNode("td", {}, [
        createNode("button", {
          className: "button danger compact-button",
          type: "button",
          "data-settings-delete": "price",
          "data-delete-id": price.id,
          "data-delete-label": `${price.provider_name}/${price.model}`,
          textContent: "Delete",
        }),
      ]));
      body?.append(row);
    });
    if (body && !payload.data.prices?.length) {
      body.append(createNode("tr", {}, [
        createNode("td", { className: "empty", colspan: "10", textContent: "No pricing rows matched." }),
      ]));
    }
  };

  const renderData = (payload) => {
    const storage = payload.data.storage || {};
    const container = root.querySelector("[data-settings-storage]");
    container?.replaceChildren(...[
      ["Total stored rows", payload.summary.stored_rows],
      ["Database file size", storage.database_file_size === null ? "-" : `${settingsNumber(storage.database_file_size)} bytes`],
      ["Oldest record date", storage.oldest_record_at || "-"],
      ["Newest record date", storage.newest_record_at || "-"],
    ].map(([label, value]) => createNode("div", {}, [
      createNode("span", { textContent: label }),
      createNode("strong", { textContent: String(value) }),
    ])));
    const path = root.querySelector("[data-settings-database-path]");
    if (path) {
      path.textContent = storage.database_path || "";
    }
    renderRetention(payload);
  };

  const render = (payload) => {
    latest = payload;
    renderSettingsSummary(root, payload);
    renderProviderOptions(payload);
    if (tab === "server") renderServer(payload);
    if (tab === "routing") renderRoutes(payload);
    if (tab === "providers") renderProviders(payload);
    if (tab === "pricing") renderPrices(payload);
    if (tab === "diagnostics") {
      renderSettingsHealth(root, payload.data.providers, payload.data.health_results);
      fillSettingsForm(root.querySelector("[data-settings-action='diagnostics']"), payload.data.test_defaults);
    }
    if (tab === "data") renderData(payload);
    renderSettingsPagination(root, payload.pagination);
  };

  const load = async ({ preserveStatus = false } = {}) => {
    if (reading) {
      controller?.abort();
    }
    controller = new AbortController();
    reading = true;
    if (!preserveStatus) {
      setStatus(latest ? "Refreshing settings…" : "Loading settings…");
    }
    try {
      const response = await fetch(currentApiUrl(), {
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Settings API returned ${response.status}`);
      }
      render(payload);
      setStatus("Settings are current");
    } catch (error) {
      if (error.name !== "AbortError") {
        setStatus(
          latest
            ? `Refresh failed; showing last data. ${error.message || ""}`
            : `Settings failed to load. ${error.message || ""}`,
          true,
        );
      }
    } finally {
      reading = false;
    }
  };

  const requestJson = async (url, options) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(options?.headers || {}),
      },
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `Request returned ${response.status}`);
    }
    return payload;
  };

  const mutationForForm = (form, submitter) => {
    const action = form.dataset.settingsAction;
    const payload = settingsFormPayload(form, submitter);
    if (action === "listener") {
      return ["/admin/api/settings/listener", "POST", {
        port: payload.incoming_port,
        expose_all_ips: payload.expose_all_ips === "yes",
      }];
    }
    if (action === "upstream-defaults") {
      return ["/admin/api/settings/upstream-defaults", "POST", {
        upstream_url: payload.upstream_url,
        default_provider_slug: payload.default_provider_slug,
        default_model: payload.default_model,
        fallback_enabled: payload.fallback_enabled === "yes",
      }];
    }
    if (action === "compat-fixes") {
      return ["/admin/api/settings/compat-fixes", "POST", { fixes: payload.fixes || "" }];
    }
    if (action === "diagnostics") {
      return ["/admin/api/diagnostics/upstream-test", "POST", payload];
    }
    if (action === "trim") {
      return ["/admin/api/settings/trim", "POST", {
        days: payload.days,
        confirm: payload.confirm === "yes",
      }];
    }
    if (action === "route-save") {
      const routeId = payload.route_id;
      return [
        routeId ? `/admin/api/routes/${routeId}` : "/admin/api/routes",
        routeId ? "PUT" : "POST",
        {
          incoming_model: payload.model,
          match_type: payload.match_type,
          upstream_url: payload.upstream_url,
          upstream_model: payload.upstream_model,
          provider_slug: payload.provider_slug,
          api_key_env: payload.api_key_env,
          compatibility_fixes: payload.fixes,
          override_fallback: payload.override_fallback === "yes",
          priority: payload.priority,
          active: payload.active === "yes",
        },
      ];
    }
    if (action === "provider-save") {
      const original = payload.original_slug;
      return [
        original ? `/admin/api/providers/${encodeURIComponent(original)}` : "/admin/api/providers",
        original ? "PUT" : "POST",
        {
          slug: payload.slug,
          name: payload.name,
          upstream_url: payload.upstream_url,
          currency: payload.currency,
          api_key_env: payload.api_key_env,
          active: payload.active === "yes",
          is_default_fallback: payload.is_default_fallback === "yes",
          capabilities: {
            text: payload.capability_text === "yes",
            vision: payload.capability_vision === "yes",
            tool_calling: payload.capability_tool_calling === "yes",
          },
        },
      ];
    }
    if (action === "price-save") {
      const priceId = payload.price_id;
      return [
        priceId ? `/admin/api/model-prices/${priceId}` : "/admin/api/model-prices",
        priceId ? "PUT" : "POST",
        {
          ...payload,
          active: payload.active === "yes",
        },
      ];
    }
    if (action === "tier-save") {
      return [
        `/admin/api/model-prices/${payload.price_id}/tiers`,
        "POST",
        payload,
      ];
    }
    return null;
  };

  root.addEventListener("input", (event) => {
    const form = event.target.closest("[data-settings-action]");
    if (form) {
      form.dataset.dirty = "yes";
    }
    const fixForm = event.target.closest("[data-fix-picker]");
    if (fixForm && event.target.matches("[data-fix-id]")) {
      const value = [...fixForm.querySelectorAll("[data-fix-id]:checked")]
        .map((item) => item.value)
        .join("\n");
      const target = fixForm.querySelector("[data-fix-target]");
      const manual = fixForm.querySelector("[data-fix-manual]");
      if (target) target.value = value;
      if (manual) manual.value = value;
    }
  });
  root.addEventListener("change", (event) => {
    const form = event.target.closest("[data-settings-action]");
    if (form) {
      form.dataset.dirty = "yes";
    }
  });
  root.addEventListener("toggle", (event) => {
    const details = event.target.closest("[data-price-details]");
    if (!details) {
      return;
    }
    const key = details.dataset.priceDetails;
    if (details.open) openPriceIds.add(key);
    else openPriceIds.delete(key);
  }, true);
  root.addEventListener("reset", (event) => {
    const form = event.target.closest("[data-settings-action]");
    window.setTimeout(() => {
      if (form) form.dataset.dirty = "no";
    }, 0);
  });
  root.addEventListener("submit", async (event) => {
    const filters = event.target.closest("[data-settings-filters]");
    if (filters) {
      event.preventDefault();
      const params = new URLSearchParams(window.location.search);
      const values = settingsFormPayload(filters);
      ["search", "status", "provider", "currency"].forEach((key) => {
        const value = String(values[key] || "");
        if (value && value !== "all") params.set(key, value);
        else params.delete(key);
      });
      params.delete("page");
      history.pushState({}, "", `${window.location.pathname}?${params}`);
      load();
      return;
    }
    const form = event.target.closest("[data-settings-action]");
    if (!form) {
      return;
    }
    event.preventDefault();
    if (mutating) {
      setSettingsFormMessage(form, "Another settings update is still running.", true);
      return;
    }
    const mutation = mutationForForm(form, event.submitter);
    if (!mutation) {
      return;
    }
    if (form.dataset.settingsAction === "trim") {
      const confirmed = await confirmWithModal(
        `Delete captured rows older than ${form.elements.days.value} days?`,
      );
      if (!confirmed) {
        return;
      }
    }
    const [url, method, payload] = mutation;
    mutating = true;
    if (event.submitter) event.submitter.disabled = true;
    setSettingsFormMessage(form, "Saving…");
    try {
      const result = await requestJson(url, {
        method,
        body: JSON.stringify(payload),
      });
      form.dataset.dirty = "no";
      setSettingsFormMessage(form, "Saved.");
      if (form.dataset.settingsAction === "diagnostics") {
        renderSettingsDiagnosticResult(root, result);
      }
      if (form.dataset.settingsAction === "trim") {
        const confirmation = form.querySelector("input[name='confirm']");
        if (confirmation) confirmation.checked = false;
      }
      await load({ preserveStatus: true });
      setStatus("Settings updated");
    } catch (error) {
      setSettingsFormMessage(form, error.message || "Update failed.", true);
      setStatus("Settings update failed", true);
    } finally {
      mutating = false;
      if (event.submitter) event.submitter.disabled = false;
    }
  });
  root.addEventListener("click", async (event) => {
    const refresh = event.target.closest("[data-settings-refresh]");
    if (refresh) {
      event.preventDefault();
      load();
      return;
    }
    const pageButton = event.target.closest("[data-settings-page]");
    if (pageButton) {
      const params = new URLSearchParams(window.location.search);
      params.set("page", pageButton.dataset.settingsPage);
      history.pushState({}, "", `${window.location.pathname}?${params}`);
      load();
      return;
    }
    const routeRow = event.target.closest("[data-settings-route-row]");
    if (routeRow && !event.target.closest("button, a, input, select, textarea")) {
      const route = latest?.data.routes.find(
        (item) => String(item.id) === String(routeRow.dataset.settingsRouteRow),
      );
      const form = root.querySelector("[data-route-editor]");
      if (route && form) {
        selectedRouteId = route.id;
        form.dataset.dirty = "no";
        fillSettingsForm(form, {
          route_id: route.id,
          model: route.model,
          match_type: route.match_type,
          upstream_url: route.upstream_url,
          upstream_model: route.upstream_model,
          provider_slug: route.provider_slug,
          api_key_env: route.api_key_env,
          fixes: (route.compatibility_fixes || []).join("\n"),
          priority: route.priority,
          active: route.active,
          override_fallback: route.override_fallback,
        });
        renderRoutes(latest);
      }
      return;
    }
    const providerRow = event.target.closest("[data-settings-provider-row]");
    if (providerRow && !event.target.closest("button, a, input, select, textarea")) {
      const provider = latest?.data.providers.find(
        (item) => item.slug === providerRow.dataset.settingsProviderRow,
      );
      const form = root.querySelector("[data-provider-editor]");
      if (provider && form) {
        selectedProviderSlug = provider.slug;
        form.dataset.dirty = "no";
        fillSettingsForm(form, {
          original_slug: provider.slug,
          slug: provider.slug,
          name: provider.name,
          upstream_url: provider.upstream_url,
          currency: provider.currency,
          api_key_env: provider.api_key_env,
          active: provider.active,
          is_default_fallback: provider.is_default_fallback,
          capability_text: provider.capabilities?.text,
          capability_vision: provider.capabilities?.vision,
          capability_tool_calling: provider.capabilities?.tool_calling,
        });
        renderProviders(latest);
      }
      return;
    }
    const priceRow = event.target.closest("[data-settings-price-row]");
    if (priceRow && !event.target.closest("button, a, input, select, textarea, details")) {
      const price = latest?.data.prices.find(
        (item) => String(item.id) === String(priceRow.dataset.settingsPriceRow),
      );
      const form = root.querySelector("[data-settings-action='price-save']");
      if (price && form) {
        form.dataset.dirty = "no";
        fillSettingsForm(form, {
          price_id: price.id,
          provider_slug: price.provider_slug,
          model: price.model,
          display_name: price.display_name,
          input_usd_per_million: price.input_usd_per_million,
          cached_input_usd_per_million: price.cached_input_usd_per_million,
          output_usd_per_million: price.output_usd_per_million,
          aliases: (price.aliases || []).join(", "),
          notes: price.notes,
          active: price.active,
        });
      }
      return;
    }
    const deletion = event.target.closest("[data-settings-delete]");
    if (deletion) {
      const kind = deletion.dataset.settingsDelete;
      const id = deletion.dataset.deleteId;
      if (!await confirmWithModal(`Delete ${deletion.dataset.deleteLabel || kind}?`)) {
        return;
      }
      const urls = {
        route: `/admin/api/routes/${id}`,
        provider: `/admin/api/providers/${encodeURIComponent(id)}`,
        price: `/admin/api/model-prices/${id}`,
        tier: `/admin/api/model-price-tiers/${id}`,
      };
      mutating = true;
      deletion.disabled = true;
      try {
        await requestJson(urls[kind], { method: "DELETE" });
        await load({ preserveStatus: true });
        setStatus("Settings updated");
      } catch (error) {
        setStatus(error.message || "Delete failed.", true);
      } finally {
        mutating = false;
        deletion.disabled = false;
      }
      return;
    }
    const providerTest = event.target.closest("[data-run-provider-test]");
    if (providerTest) {
      const form = providerTest.closest("[data-provider-editor]");
      const slug = form?.elements.original_slug?.value || form?.elements.slug?.value;
      const result = root.querySelector("[data-provider-test-result]");
      if (!slug || !result) {
        setSettingsFormMessage(form, "Choose or save a provider first.", true);
        return;
      }
      providerTest.disabled = true;
      result.hidden = false;
      result.textContent = "Testing provider…";
      try {
        const data = await requestJson(
          `/admin/api/providers/${encodeURIComponent(slug)}/test`,
          { method: "POST" },
        );
        result.textContent = `${data.status}: ${data.message || ""}`;
      } catch (error) {
        result.textContent = error.message || "Provider test failed.";
      } finally {
        providerTest.disabled = false;
      }
    }
  });

  window.addEventListener("popstate", load);
  window.addEventListener("settings:refresh", () => load({ preserveStatus: true }));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && !hasDirtyForm() && !mutating) {
      load({ preserveStatus: true });
    }
  });

  const filterForm = root.querySelector("[data-settings-filters]");
  if (filterForm) {
    const params = new URLSearchParams(window.location.search);
    ["search", "status", "provider", "currency"].forEach((name) => {
      if (filterForm.elements[name] && params.has(name)) {
        filterForm.elements[name].value = params.get(name);
      }
    });
  }
  load();
};

const initRequestsLivePage = (root) => {
  const table = root.querySelector("[data-live-requests-table]");
  const inspector = root.querySelector("[data-live-request-inspector]");
  const runControl = root.querySelector("[data-live-run-control]");
  const form = root.querySelector("[data-live-request-filters]");
  let latestItems = [];
  let selectedRequestId = null;

  syncRequestFormFromUrl(root);

  const load = async (signal) => {
    const response = await fetch(apiUrlWithCurrentQuery(root), {
      headers: { Accept: "application/json" },
      signal,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Requests API returned ${response.status}`);
    }
    updateRequestFilterOptions(root, data);
    syncRequestFormFromUrl(root);
    latestItems = data.items || [];
    renderRequestStats(root, data.stats || {});
    renderRunControl(runControl, data.active_run, false);
    renderRequestsTable(table, latestItems, data.pagination, true, {
      showSignals: false,
      showSummary: false,
    });
    if (!latestItems.some((item) => String(item.id) === String(selectedRequestId))) {
      selectedRequestId = latestItems[0]?.id || null;
    }
    renderRequestInspector(
      inspector,
      latestItems.find((item) => String(item.id) === String(selectedRequestId)),
    );
    markSelectedRequest(root, selectedRequestId);
  };

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = requestQueryFromForm(form).toString();
    history.pushState({}, "", query ? `/admin?${query}` : "/admin");
    window.dispatchEvent(new Event("live:refresh"));
  });
  root.querySelector("[data-live-reset]")?.addEventListener("click", (event) => {
    event.preventDefault();
    history.pushState({}, "", "/admin");
    syncRequestFormFromUrl(root);
    window.dispatchEvent(new Event("live:refresh"));
  });
  table?.addEventListener("click", (event) => {
    const requestRow = event.target.closest("[data-request-row]");
    const link = event.target.closest("[data-live-page-number]");
    if (link) {
      event.preventDefault();
      const params = new URLSearchParams(window.location.search);
      params.set("page", link.dataset.livePageNumber);
      history.pushState({}, "", `/admin?${params}`);
      window.dispatchEvent(new Event("live:refresh"));
      return;
    }
    if (!requestRow || event.target.closest("a, button")) {
      return;
    }
    const requestId = requestRow.dataset.requestId;
    if (window.matchMedia("(max-width: 760px)").matches) {
      window.location.href = `/admin/requests/${requestId}`;
      return;
    }
    selectedRequestId = requestId;
    renderRequestInspector(
      inspector,
      latestItems.find((item) => String(item.id) === String(selectedRequestId)),
    );
    markSelectedRequest(root, selectedRequestId);
  });
  table?.addEventListener("dblclick", (event) => {
    const requestRow = event.target.closest("[data-request-row]");
    if (requestRow) {
      window.location.href = `/admin/requests/${requestRow.dataset.requestId}`;
    }
  });
  table?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }
    const requestRow = event.target.closest("[data-request-row]");
    if (requestRow) {
      window.location.href = `/admin/requests/${requestRow.dataset.requestId}`;
    }
  });
  inspector?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-inspector-copy]");
    if (!button || !selectedRequestId) {
      return;
    }
    event.preventDefault();
    const action = button.dataset.inspectorCopy;
    try {
      let text = "";
      if (action === "id") {
        text = String(selectedRequestId);
      } else {
        const detail = await requestDetailForCopy(selectedRequestId);
        if (action === "request") {
          text = detail.request_render?.text || "";
        } else if (action === "response") {
          text = detail.response_render?.text || "";
        } else if (action === "curl") {
          text = curlFromRequestDetail(detail);
        }
      }
      await copyText(text);
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = {
          id: "Copy ID",
          request: "Copy request JSON",
          response: "Copy response",
          curl: "Copy as curl",
        }[action] || "Copy";
      }, 1200);
    } catch (error) {
      window.alert(error.message || "Copy failed.");
    }
  });
  root.querySelector("[data-mobile-filter-toggle]")?.addEventListener("click", () => {
    form?.classList.toggle("is-expanded");
  });
  root.querySelector("[data-live-request-stats]")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-stat-filter]");
    if (!chip) {
      return;
    }
    const key = chip.dataset.statFilter;
    const params = new URLSearchParams(window.location.search);
    ["stream", "image", "tool", "error", "slow", "large"].forEach((name) => {
      if (key === "total" || name === key) {
        params.delete(name);
      }
    });
    if (key !== "total" && !chip.classList.contains("active")) {
      params.set(key, "1");
    }
    params.delete("page");
    history.pushState({}, "", params.toString() ? `/admin?${params}` : "/admin");
    syncRequestFormFromUrl(root);
    window.dispatchEvent(new Event("live:refresh"));
  });
  window.addEventListener("popstate", () => {
    syncRequestFormFromUrl(root);
    window.dispatchEvent(new Event("live:refresh"));
  });

  startLivePoller(root, load);
};

const renderRunsTable = (container, items) => {
  container.replaceChildren();
  const table = createNode("table", { className: "runs-table" });
  const thead = createNode("thead");
  const headRow = createNode("tr");
  ["Run", "Status", "Requests", "LLM Wall Time", "Total Tokens", "Cost", "Output tok/s", "Signals"]
    .forEach((heading) => headRow.append(createNode("th", { textContent: heading })));
  thead.append(headRow);
  const tbody = createNode("tbody");
  if (!items.length) {
    const row = createNode("tr");
    tableCell(row, "No runs yet.", "empty").colSpan = 8;
    tbody.append(row);
  }
  items.forEach((run) => {
    const row = createNode("tr");
    const runCell = createNode("td");
    runCell.append(
      createNode("a", { href: `/admin/runs/${run.id}` }, [
        createNode("strong", { textContent: run.name }),
      ]),
      localTimeNode(run.started_at, run.started_at_table_fallback, "table"),
    );
    row.append(runCell);
    tableCell(row, renderStatusPill(run.status_label || (run.is_active ? "active" : "complete")));
    tableCell(row, run.request_count_display);
    tableCell(row, run.llm_wall_time_display);
    tableCell(row, run.total_tokens_display);
    tableCell(row, run.total_cost_display);
    tableCell(row, run.output_tokens_per_second_display);
    const signals = createNode("div", { className: "signals" });
    [
      ["streams", "Stream"],
      ["images", "Image"],
      ["tools", "Tool"],
      ["errors", "Error"],
    ].forEach(([key, label]) => {
      const value = run.signals?.[key]?.value || 0;
      if (value) {
        signals.append(createNode("span", { textContent: `${run.signals[key].display} ${label}` }));
      }
    });
    tableCell(row, signals, "signals");
    tbody.append(row);
  });
  table.append(thead, tbody);
  container.append(table);
  container.append(renderRunCardsMobile(items));
};

const runActionForm = (run, kind) => {
  const isResume = kind === "resume";
  const isPause = kind === "pause";
  return createNode("form", {
    method: "post",
    action: isResume ? `/admin/runs/${run.id}/resume` : (isPause ? "/admin/runs/pause" : "/admin/runs/end"),
    "data-live-run-resume": isResume ? true : null,
    "data-live-run-pause": isPause ? true : null,
    "data-live-run-end": !isResume && !isPause ? true : null,
    "data-api-url": isResume ? `/admin/api/runs/${run.id}/resume` : (isPause ? "/admin/api/runs/pause" : "/admin/api/runs/end"),
  }, [
    createNode("button", {
      className: isResume ? "button primary compact-button" : (isPause ? "button ghost compact-button" : "button danger compact-button"),
      type: "submit",
      textContent: isResume ? "Resume" : (isPause ? "Pause" : "End"),
    }),
  ]);
};

const renderRunCardsMobile = (items) => {
  const list = createNode("div", { className: "run-mobile-list" });
  if (!items.length) {
    list.append(createNode("div", { className: "empty-state", textContent: "No runs yet." }));
    return list;
  }
  items.forEach((run) => {
    const actions = createNode("span", { className: "run-card-actions" }, [
      createNode("a", {
        className: "button ghost compact-button",
        href: `/admin/runs/${run.id}`,
        textContent: "Open",
      }),
    ]);
    if (run.is_active) {
      actions.append(runActionForm(run, "pause"));
      actions.append(runActionForm(run, "end"));
    } else if (run.is_paused) {
      actions.append(runActionForm(run, "resume"));
    }
    const card = createNode("article", { className: `run-mobile-card run-${run.status_label || "complete"}` }, [
      createNode("span", { className: "mobile-card-main" }, [
        createNode("strong", { textContent: run.name }),
        renderStatusPill(run.status_label || (run.is_active ? "active" : "complete")),
      ]),
      localTimeNode(run.started_at, run.started_at_table_fallback, "mobile"),
      createNode("span", {
        className: "mobile-card-metrics",
        textContent: `${run.request_count_display} requests · ${run.total_tokens_display} tokens · ${run.total_cost_display}`,
      }),
      createNode("span", { className: "mobile-card-foot" }, [
        createNode("span", { textContent: `LLM wall time ${run.llm_wall_time_display}` }),
        actions,
      ]),
    ]);
    list.append(card);
  });
  return list;
};

const initRunsLivePage = (root) => {
  const table = root.querySelector("[data-live-runs-table]");
  const stats = root.querySelector("[data-live-run-stats]");
  const runControl = root.querySelector("[data-live-run-control]");

  const load = async (signal) => {
    const response = await fetch(root.dataset.apiUrl, {
      headers: { Accept: "application/json" },
      signal,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Runs API returned ${response.status}`);
    }
    if (stats) {
      stats.replaceChildren(
        createNode("span", {}, [createNode("strong", { textContent: data.stats.shown_display }), "Shown"]),
        createNode("span", {}, [createNode("strong", { textContent: String(data.stats.active) }), "Active"]),
        createNode("span", {}, [createNode("strong", { textContent: String(data.stats.paused || 0) }), "Paused"]),
        createNode("span", {}, [createNode("strong", { textContent: data.stats.total_requests_display || "0" }), "Requests"]),
        createNode("span", {}, [createNode("strong", { textContent: data.stats.total_tokens_display || "0" }), "Tokens"]),
        createNode("span", {}, [createNode("strong", { textContent: data.stats.total_cost_display || "$0.00" }), "Cost"]),
      );
    }
    renderRunControl(runControl, data.active_run, true);
    renderRunsTable(table, data.items || []);
  };

  startLivePoller(root, load);
};

const renderRenderedPayload = (container, rendered) => {
  if (!container) {
    return;
  }
  container.replaceChildren();
  if (!rendered) {
    container.append(createNode("pre", { className: "code", textContent: "" }));
    return;
  }
  if (rendered.mode === "markdown" && rendered.html) {
    container.append(createNode("div", { className: "markdown-body", html: rendered.html }));
    return;
  }
  if (rendered.mode === "tool" && rendered.tool_blocks?.length) {
    const list = createNode("div", { className: "tool-list" });
    rendered.tool_blocks.forEach((block) => {
      list.append(createNode("section", { className: "tool-block" }, [
        createNode("strong", { textContent: block.kind }),
        createNode("pre", {
          className: "code",
          textContent: JSON.stringify(block.payload, null, 2),
        }),
      ]));
    });
    container.append(list);
    return;
  }
  container.append(createNode("pre", { className: "code", textContent: rendered.text || "" }));
};

const metaSpan = (label, content) => {
  const span = createNode("span");
  span.append(`${label} `, createNode("strong", {}, [content instanceof Node ? content : valueOrDash(content)]));
  return span;
};

const requestImageIdentity = (images) => JSON.stringify((images || []).map((image) => [
  image.source || "",
  image.mime_type || "",
  image.kind || "",
]));

const createRequestImageFigure = (image, index) => {
  const imageNumber = index + 1;
  const label = `Request image ${imageNumber}`;
  const figure = createNode("figure", { className: "request-image-card" });
  const button = createNode("button", {
    className: "image-thumbnail-button",
    type: "button",
    "data-image-preview": true,
    "data-image-source": image.source || "",
    "data-image-label": label,
    "data-image-type": image.mime_type || image.kind || "image",
    "aria-label": `Preview ${label.toLowerCase()}`,
  });
  const thumbnail = createNode("img", { alt: label });
  const dimensions = createNode("span", {
    className: "image-caption-dimensions",
    textContent: "Loading dimensions…",
  });
  const caption = createNode("figcaption", {}, [
    createNode("span", {
      className: "image-caption-type",
      textContent: image.mime_type || image.kind || "image",
    }),
    dimensions,
  ]);

  const setDimensions = () => {
    const width = thumbnail.naturalWidth;
    const height = thumbnail.naturalHeight;
    if (!width || !height) {
      return;
    }
    button.dataset.imageWidth = String(width);
    button.dataset.imageHeight = String(height);
    dimensions.textContent = `${width} × ${height} px`;
    figure.classList.remove("is-unavailable");
  };

  thumbnail.addEventListener("load", setDimensions);
  thumbnail.addEventListener("error", () => {
    dimensions.textContent = "Dimensions unavailable";
    figure.classList.add("is-unavailable");
    button.disabled = true;
    button.setAttribute("aria-label", `${label} unavailable`);
  });
  button.append(thumbnail);
  figure.append(button, caption);
  thumbnail.src = image.source || "";
  if (thumbnail.complete) {
    setDimensions();
  }
  return figure;
};

const renderRequestImages = (root, imageData) => {
  const container = root.querySelector("[data-live-images-section]");
  if (!container) {
    return;
  }
  const images = Array.isArray(imageData) ? imageData : [];
  const identity = requestImageIdentity(images);
  if (container.dataset.imageIdentity === identity) {
    return;
  }
  container.dataset.imageIdentity = identity;
  container.replaceChildren();
  if (!images.length) {
    return;
  }

  const grid = createNode("div", { className: "image-grid" });
  images.forEach((image, index) => {
    grid.append(createRequestImageFigure(image, index));
  });
  container.append(createNode("section", { className: "panel" }, [
    createNode("header", {}, [
      createNode("h2", { textContent: "Images Sent" }),
      createNode("span", { textContent: `${images.length} image${images.length === 1 ? "" : "s"}` }),
    ]),
    grid,
  ]));
};

const initRequestImagePreview = (root) => {
  const overlay = createNode("div", {
    className: "modal-overlay image-preview-overlay",
    hidden: true,
  });
  const dialog = createNode("div", {
    className: "image-preview-modal",
    role: "dialog",
    "aria-modal": "true",
    "aria-labelledby": "request-image-preview-title",
    "aria-describedby": "request-image-preview-meta",
  });
  const title = createNode("h2", {
    id: "request-image-preview-title",
    textContent: "Request image",
  });
  const metadata = createNode("p", {
    id: "request-image-preview-meta",
    className: "muted",
    textContent: "Loading dimensions…",
  });
  const actualSize = createNode("button", {
    className: "button ghost image-preview-size",
    type: "button",
    "aria-pressed": "false",
    textContent: "Actual size",
  });
  const closeButton = createNode("button", {
    className: "button ghost image-preview-close",
    type: "button",
    "aria-label": "Close image preview",
    textContent: "Close",
  });
  const viewport = createNode("div", {
    className: "image-preview-viewport",
    tabindex: "0",
  });
  const preview = createNode("img", { alt: "" });
  const header = createNode("header", { className: "image-preview-header" }, [
    createNode("div", { className: "image-preview-heading" }, [title, metadata]),
    createNode("div", { className: "image-preview-actions" }, [actualSize, closeButton]),
  ]);
  viewport.append(preview);
  dialog.append(header, viewport);
  overlay.append(dialog);
  document.body.append(overlay);

  let opener = null;
  let isActualSize = false;
  let previousModalOpen = false;

  const setActualSize = (enabled) => {
    isActualSize = Boolean(enabled) && !actualSize.disabled;
    dialog.classList.toggle("is-actual-size", isActualSize);
    actualSize.setAttribute("aria-pressed", String(isActualSize));
    actualSize.textContent = isActualSize ? "Fit to window" : "Actual size";
  };

  const setDimensions = (width, height, type) => {
    if (width > 0 && height > 0) {
      metadata.textContent = `${type} · ${width} × ${height} px`;
      actualSize.disabled = false;
      preview.dataset.imageWidth = String(width);
      preview.dataset.imageHeight = String(height);
      return;
    }
    metadata.textContent = `${type} · Dimensions unavailable`;
    actualSize.disabled = true;
    setActualSize(false);
  };

  const close = () => {
    if (overlay.hidden) {
      return;
    }
    overlay.hidden = true;
    setActualSize(false);
    preview.removeAttribute("src");
    if (!previousModalOpen) {
      document.body.classList.remove("modal-open");
    }
    const restoreTarget = opener;
    opener = null;
    if (restoreTarget?.isConnected && !restoreTarget.disabled) {
      restoreTarget.focus();
    }
  };

  const open = (button) => {
    const source = button.dataset.imageSource || "";
    const label = button.dataset.imageLabel || "Request image";
    const type = button.dataset.imageType || "image";
    const knownWidth = Number(button.dataset.imageWidth || "0");
    const knownHeight = Number(button.dataset.imageHeight || "0");
    opener = button;
    title.textContent = label;
    preview.alt = `${label} preview`;
    preview.classList.remove("is-unavailable");
    actualSize.disabled = !(knownWidth && knownHeight);
    setActualSize(false);
    setDimensions(knownWidth, knownHeight, type);
    previousModalOpen = document.body.classList.contains("modal-open");
    document.body.classList.add("modal-open");
    overlay.hidden = false;
    preview.src = source;
    closeButton.focus();
  };

  preview.addEventListener("load", () => {
    const width = preview.naturalWidth;
    const height = preview.naturalHeight;
    const type = opener?.dataset.imageType || "image";
    setDimensions(width, height, type);
    if (opener && width && height) {
      opener.dataset.imageWidth = String(width);
      opener.dataset.imageHeight = String(height);
      const caption = opener.closest("figure")?.querySelector(".image-caption-dimensions");
      if (caption) {
        caption.textContent = `${width} × ${height} px`;
      }
    }
  });
  preview.addEventListener("error", () => {
    preview.classList.add("is-unavailable");
    setDimensions(0, 0, opener?.dataset.imageType || "image");
  });
  actualSize.addEventListener("click", () => setActualSize(!isActualSize));
  closeButton.addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      close();
    }
  });
  overlay.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    const focusable = [...dialog.querySelectorAll(
      "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), "
      + "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
    )];
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  root.querySelector("[data-live-images-section]")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-image-preview]");
    if (button && !button.disabled) {
      open(button);
    }
  });

  return { close };
};

const renderRequestDetail = (root, data) => {
  const record = data.record;
  document.title = `Request #${record.id} - LLM Observe Proxy`;
  const header = root.querySelector("[data-live-request-detail-header]");
  if (header) {
    const meta = createNode("div", { className: "detail-meta" });
    meta.append(
      metaSpan("Status", record.status_label),
      metaSpan("Duration", record.duration_is_elapsed
        ? createNode("span", {
          className: "elapsed-duration",
          "data-pending-start": record.created_at,
          textContent: `${record.duration_display} so far`,
        })
        : record.duration_display),
      metaSpan("Created", localTimeNode(record.created_at, record.created_at_fallback, "full")),
    );
    if (record.completed_at) {
      meta.append(metaSpan("Completed", localTimeNode(record.completed_at, record.completed_at_fallback, "full")));
    }
    meta.append(
      metaSpan("Cost", record.billing_total_cost_display),
      metaSpan("Model", record.model || "unknown"),
    );
    if (record.upstream_model) {
      meta.append(metaSpan("Upstream Model", record.upstream_model));
    }
    if (record.model_route) {
      meta.append(metaSpan("Route", record.model_route));
    }
    if (record.task_run) {
      meta.append(metaSpan("Run", createNode("a", {
        href: `/admin/runs/${record.task_run.id}`,
        textContent: record.task_run.name,
      })));
    }
    if (record.response_was_rewritten) {
      meta.append(metaSpan("Compatibility", "rewritten"));
    } else if (record.compat_fix_errors_json) {
      meta.append(metaSpan("Compatibility", "warned"));
    }
    header.replaceChildren(
      createNode("div", {}, [
        createNode("p", { className: "eyebrow", textContent: `${record.method} ${record.endpoint}` }),
        createNode("h1", { textContent: `Request #${record.id}` }),
      ]),
      meta,
    );
  }

  const alert = root.querySelector("[data-live-request-alert]");
  alert?.replaceChildren();
  if (record.error && alert) {
    alert.append(createNode("div", { className: "alert", textContent: record.error }));
  }

  const contentType = root.querySelector("[data-live-request-content-type]");
  if (contentType) {
    contentType.textContent = record.request_content_type || "body";
  }
  const requestBody = root.querySelector("[data-live-request-body]");
  if (requestBody) {
    requestBody.textContent = data.request_render?.text || "";
  }
  renderRenderedPayload(root.querySelector("[data-live-response-body]"), data.response_render);

  root.querySelectorAll("[data-live-mode-tabs] a").forEach((link) => {
    link.classList.toggle("active", link.dataset.mode === data.mode);
  });

  const compat = root.querySelector("[data-live-compat-section]");
  compat?.replaceChildren();
  if (compat && (record.compat_fixes_json || record.compat_fix_errors_json)) {
    compat.append(createNode("section", { className: "split" }, [
      createNode("article", { className: "panel" }, [
        createNode("header", {}, [createNode("h2", { textContent: "Compatibility Fixes" })]),
        createNode("pre", { className: "code compact-code", textContent: record.compat_fixes_json || "{}" }),
      ]),
      createNode("article", { className: "panel" }, [
        createNode("header", {}, [createNode("h2", { textContent: "Compatibility Warnings" })]),
        createNode("pre", { className: "code compact-code", textContent: record.compat_fix_errors_json || "{}" }),
      ]),
    ]));
  }

  const raw = root.querySelector("[data-live-raw-response-section]");
  raw?.replaceChildren();
  if (raw && data.raw_response_render) {
    const body = createNode("div");
    renderRenderedPayload(body, data.raw_response_render);
    raw.append(createNode("section", { className: "panel" }, [
      createNode("header", {}, [
        createNode("h2", { textContent: "Raw Upstream Response" }),
        createNode("span", { textContent: "Before compatibility fixes" }),
      ]),
      body,
    ]));
  }

  renderRequestImages(root, data.images);

  const cost = root.querySelector("[data-live-cost-section]");
  cost?.replaceChildren();
  if (cost) {
    const breakdown = createNode("div", { className: "breakdown-list" });
    [
      [record.display_input_tokens_display, "Input tokens"],
      [record.display_cached_input_tokens_display, "Cached input tokens"],
      [record.display_output_tokens_display, "Output tokens"],
      [record.display_total_tokens_display, "Total tokens"],
      [record.billing_total_cost_display, "Estimated cost"],
      [record.billing_model || "-", "Billing model"],
    ].forEach(([value, label]) => {
      breakdown.append(createNode("span", {}, [
        createNode("strong", { textContent: valueOrDash(value) }),
        label,
      ]));
    });
    if (!record.completed_at && record.display_input_tokens === null && record.estimated_input_tokens) {
      breakdown.append(createNode("span", { className: "estimated-token" }, [
        createNode("strong", { textContent: `~${record.estimated_input_tokens_display}` }),
        "Est. input tokens",
      ]));
    }
    if (record.estimated_input_tokenizer) {
      breakdown.append(createNode("span", {}, [
        createNode("strong", { textContent: record.estimated_input_tokenizer }),
        "Estimate tokenizer",
      ]));
    }
    cost.append(createNode("section", { className: "split" }, [
      createNode("article", { className: "panel" }, [
        createNode("header", {}, [
          createNode("h2", { textContent: "Cost Estimate" }),
          createNode("span", { textContent: record.billing_provider_name || record.billing_provider_slug || "no provider" }),
        ]),
        breakdown,
      ]),
      createNode("article", { className: "panel" }, [
        createNode("header", {}, [createNode("h2", { textContent: "Pricing Snapshot" })]),
        createNode("pre", { className: "code compact-code", textContent: record.pricing_snapshot_json || "{}" }),
      ]),
    ]));
  }

  const headers = root.querySelector("[data-live-headers-section]");
  headers?.replaceChildren();
  headers?.append(createNode("section", { className: "split" }, [
    createNode("article", { className: "panel" }, [
      createNode("header", {}, [createNode("h2", { textContent: "Request Headers" })]),
      createNode("pre", { className: "code", textContent: record.request_headers_json || "{}" }),
    ]),
    createNode("article", { className: "panel" }, [
      createNode("header", {}, [createNode("h2", { textContent: "Response Headers" })]),
      createNode("pre", { className: "code", textContent: record.response_headers_json || "{}" }),
    ]),
  ]));

  const upstream = root.querySelector("[data-live-upstream-section]");
  upstream?.replaceChildren();
  upstream?.append(createNode("section", { className: "panel" }, [
    createNode("header", {}, [
      createNode("h2", { textContent: "Upstream" }),
      createNode("span", {
        textContent: record.model_route
          || (record.upstream_model ? "model fallback" : "pass-through upstream"),
      }),
    ]),
    createNode("code", { textContent: record.upstream_url }),
  ]));
  updatePendingElapsed();
};

const initRequestDetailLivePage = (root) => {
  initRequestImagePreview(root);
  const modeFromUrl = () => new URLSearchParams(window.location.search).get("mode")
    || root.dataset.renderMode
    || "auto";
  let mode = modeFromUrl();
  const load = async (signal) => {
    const url = new URL(root.dataset.apiUrl, window.location.origin);
    url.searchParams.set("mode", mode);
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Request API returned ${response.status}`);
    }
    renderRequestDetail(root, data);
  };
  root.querySelector("[data-live-mode-tabs]")?.addEventListener("click", (event) => {
    const link = event.target.closest("[data-mode]");
    if (!link) {
      return;
    }
    event.preventDefault();
    mode = link.dataset.mode || "auto";
    history.pushState({}, "", `/admin/requests/${root.dataset.recordId}?mode=${mode}`);
    window.dispatchEvent(new Event("live:refresh"));
  });
  window.addEventListener("popstate", () => {
    mode = modeFromUrl();
    window.dispatchEvent(new Event("live:refresh"));
  });
  startLivePoller(root, load);
};

const breakdownPanel = (title, rows, emptyText) => {
  const list = createNode("div", { className: "breakdown-list" });
  if (!rows.length) {
    list.append(createNode("p", { className: "muted", textContent: emptyText }));
  } else {
    rows.forEach((row) => {
      list.append(createNode("span", {}, [
        createNode("strong", { textContent: row.count_display }),
        row.label,
      ]));
    });
  }
  return createNode("article", { className: "panel" }, [
    createNode("header", {}, [createNode("h2", { textContent: title })]),
    list,
  ]);
};

const renderMetricRows = (rows) => createNode("div", { className: "metric-rows" }, rows.map(([label, value, className = ""]) => (
  createNode("span", { className }, [
    createNode("small", { textContent: label }),
    createNode("strong", { textContent: valueOrDash(value) }),
  ])
)));

const runStatusChip = (text, className = "") => createNode("span", {
  className: `run-chip ${className}`.trim(),
  textContent: text,
});

const statTile = (label, value, detail = "", className = "", title = "") => createNode("span", {
  className: `run-stat-tile ${className}`.trim(),
  title,
}, [
  createNode("small", { textContent: label }),
  createNode("strong", { textContent: valueOrDash(value) }),
  detail ? createNode("em", { textContent: detail }) : null,
]);

const countRows = (rows, limit = 3) => (rows || []).slice(0, limit).map((row) => [
  row.label,
  row.count_display,
]);

const renderRunOverview = (root, data) => {
  const container = root.querySelector("[data-live-run-overview]");
  if (!container) {
    return;
  }
  const stats = data.stats;
  const firstStatus = (stats.statuses || [])[0];
  container.replaceChildren(
    createNode("article", { className: "panel overview-card" }, [
      createNode("header", {}, [
        createNode("h2", { textContent: "Run health" }),
        createNode("span", { className: "success-badge", textContent: stats.success_rate_display }),
      ]),
      renderMetricRows([
        ["Success rate", stats.success_rate_display, "ok-text"],
        ["Stream count", stats.signals.streams.display],
        ["Tool calls", stats.signals.tools.display],
        ["Image requests", stats.signals.images.display],
        ["Last activity", stats.last_activity ? "Live" : "-"],
      ]),
    ]),
    createNode("article", { className: "panel overview-card" }, [
      createNode("header", {}, [createNode("h2", { textContent: "Top models" })]),
      renderMetricRows(countRows(stats.models, 4)),
    ]),
    createNode("article", { className: "panel overview-card" }, [
      createNode("header", {}, [createNode("h2", { textContent: "Status codes" })]),
      renderMetricRows(countRows(stats.statuses, 4)),
    ]),
    createNode("article", { className: "panel overview-card" }, [
      createNode("header", {}, [createNode("h2", { textContent: "Signals" })]),
      renderMetricRows([
        ["Streams", stats.signals.streams.display],
        ["Tools", stats.signals.tools.display],
        ["Images", stats.signals.images.display],
        ["Errors", stats.signals.errors.display, stats.error_count ? "error-text" : ""],
      ]),
    ]),
    createNode("article", { className: "panel overview-card what-if-summary-card" }, [
      createNode("header", {}, [createNode("h2", { textContent: "What-if cost" })]),
      createNode("div", { className: "what-if-summary-list", "data-what-if-summary": true }, [
        createNode("p", { className: "muted", textContent: "Loading comparisons..." }),
      ]),
    ]),
    createNode("article", { className: "panel overview-card run-insights" }, [
      createNode("header", {}, [
        createNode("h2", { textContent: "Run insights" }),
        createNode("span", {
          className: data.run.is_active ? "live-dot" : (data.run.is_paused ? "pause-dot" : "muted"),
          textContent: data.run.is_active ? "Live" : (data.run.is_paused ? "Paused" : "Complete"),
        }),
      ]),
      renderMetricRows([
        ["Active route", firstStatus ? `${firstStatus.label} · ${firstStatus.count_display}` : "-"],
        ["Top provider", data.items?.[0]?.provider_name || data.items?.[0]?.billing_provider || "-"],
        ["Busiest model", stats.models?.[0] ? `${stats.models[0].label} · ${stats.models[0].count_display}` : "-"],
        ["Error rate", stats.error_rate_display, stats.error_count ? "error-text" : ""],
      ]),
      createNode("p", { className: "muted live-copy", textContent: "Live updates every 1s" }),
    ]),
  );
  window.renderWhatIfSummary?.();
};

const renderRunSupplementalTabs = (root, data) => {
  const models = root.querySelector("[data-live-run-models]");
  models?.replaceChildren(
    createNode("section", { className: "split" }, [
      breakdownPanel("Models", data.stats.models || [], "No model usage yet."),
      breakdownPanel("Endpoints", data.stats.endpoints || [], "No endpoint usage yet."),
    ]),
  );
  const diagnostics = root.querySelector("[data-live-run-diagnostics]");
  diagnostics?.replaceChildren(
    createNode("section", { className: "split" }, [
      breakdownPanel("Status Codes", data.stats.statuses || [], "No status codes yet."),
      createNode("article", { className: "panel" }, [
        createNode("header", {}, [createNode("h2", { textContent: "Diagnostics" })]),
        renderMetricRows([
          ["Errors", data.stats.error_count_display],
          ["Error rate", data.stats.error_rate_display],
          ["Pending", data.stats.pending_count_display],
          ["Slow threshold", "10 s"],
          ["Large threshold", "10k tokens"],
        ]),
      ]),
    ]),
  );
};

const renderRunDetail = (root, data) => {
  const run = data.run;
  document.title = `Run: ${run.name} - LLM Observe Proxy`;
  const header = root.querySelector("[data-live-run-detail-header]");
  if (header) {
    const meta = createNode("div", { className: "detail-meta run-meta" });
    const statusLabel = run.status_label || (run.is_active ? "active" : "complete");
    meta.append(
      runStatusChip(`Started ${run.started_at_fallback}`),
      runStatusChip(`Open for ${run.open_duration_display}`),
      runStatusChip(`Status ${statusLabel}`, run.is_active ? "ok-chip" : (run.is_paused ? "pause-chip" : "")),
    );
    if (run.is_paused && run.paused_at_fallback) {
      meta.append(runStatusChip(`Paused ${run.paused_at_fallback}`, "pause-chip"));
    }
    if (data.stats.error_count) {
      meta.append(runStatusChip(`${data.stats.error_count_display} errors`, "error-chip"));
    }
    const side = createNode("div", { className: "run-summary-side" }, [meta]);
    if (run.is_active) {
      side.append(createNode("div", { className: "run-summary-actions" }, [
        runActionForm(run, "pause"),
        runActionForm(run, "end"),
      ]));
    } else if (run.is_paused) {
      side.append(createNode("div", { className: "run-summary-actions" }, [
        runActionForm(run, "resume"),
      ]));
    }
    const topline = createNode("div", { className: "run-summary-topline" }, [
      createNode("div", { className: "run-summary-title" }, [
        createNode("p", {
          className: "eyebrow",
          textContent: run.is_active ? "Run in progress" : (run.is_paused ? "Paused run" : "Completed run"),
        }),
        createNode("div", { className: "run-title-line" }, [
          createNode("h1", { textContent: `Run: ${run.name}` }),
          runStatusChip(run.is_active ? "LIVE" : (run.is_paused ? "PAUSED" : "DONE"), run.is_active ? "live-chip" : (run.is_paused ? "pause-chip" : "")),
        ]),
        run.notes ? createNode("p", { className: "muted", textContent: run.notes }) : null,
        meta,
      ]),
      side,
    ]);
    const strip = createNode("div", { className: "run-stat-strip", "data-live-run-stat-strip": true });
    [
      ["Requests", data.stats.request_count_display],
      ["Success", data.stats.success_count_display, data.stats.success_rate_display, "ok-text"],
      ["Errors", data.stats.error_count_display, data.stats.error_rate_display, data.stats.error_count ? "error-text" : ""],
      ["Run open", data.stats.run_open_duration_display, "", "", "Clock time since the run started."],
      ["LLM wall time", data.stats.llm_wall_time_display, "", "", "First request timestamp to latest completed request timestamp."],
      ["Input tokens", data.stats.tokens.input.display],
      ["Output tokens", data.stats.tokens.output.display],
      ["Total tokens", data.stats.tokens.total.display],
      ["Estimated cost", data.stats.cost_display, "USD"],
      ["Output tok/s", data.stats.throughput.output_observed.display, "avg", "", "Output tokens divided by total observed request duration."],
    ].forEach(([label, value, detail, className, title]) => {
      strip.append(statTile(label, value, detail, className, title));
    });
    header.replaceChildren(topline, strip);
  }

  renderRunOverview(root, data);
  renderRunSupplementalTabs(root, data);
  renderRequestsTable(
    root.querySelector("[data-live-recent-traffic]"),
    (data.items || []).slice(0, 6),
    null,
    false,
    { compact: true },
  );
  renderRequestsTable(
    root.querySelector("[data-live-requests-table]"),
    data.items || [],
    data.pagination,
    false,
  );
};

const initRunDetailLivePage = (root) => {
  const activateTab = (tabName) => {
    root.querySelectorAll("[data-run-tab]").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.runTab === tabName);
    });
    root.querySelectorAll("[data-run-tab-panel]").forEach((panel) => {
      const active = panel.dataset.runTabPanel === tabName;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
  };
  const apiUrlForQuery = () => {
    const url = new URL(root.dataset.apiUrl, window.location.origin);
    const params = new URLSearchParams(window.location.search);
    params.forEach((value, key) => url.searchParams.set(key, value));
    return url;
  };
  const load = async (signal) => {
    const response = await fetch(apiUrlForQuery(), {
      headers: { Accept: "application/json" },
      signal,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Run API returned ${response.status}`);
    }
    renderRunDetail(root, data);
  };
  root.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-run-tab], [data-run-tab-jump]");
    if (tab) {
      activateTab(tab.dataset.runTab || tab.dataset.runTabJump);
      return;
    }
    const link = event.target.closest("[data-live-page-number]");
    if (!link) {
      return;
    }
    event.preventDefault();
    const params = new URLSearchParams(window.location.search);
    params.set("page", link.dataset.livePageNumber);
    history.pushState({}, "", `/admin/runs/${root.dataset.runId}?${params}`);
    window.dispatchEvent(new Event("live:refresh"));
  });
  window.addEventListener("popstate", () => window.dispatchEvent(new Event("live:refresh")));
  startLivePoller(root, load);
};

document.addEventListener("submit", async (event) => {
  const startForm = event.target.closest("[data-live-run-start]");
  const endForm = event.target.closest("[data-live-run-end]");
  const pauseForm = event.target.closest("[data-live-run-pause]");
  const resumeForm = event.target.closest("[data-live-run-resume]");
  if (!startForm && !endForm && !pauseForm && !resumeForm) {
    return;
  }
  event.preventDefault();
  const form = startForm || endForm || pauseForm || resumeForm;
  const payload = startForm
    ? {
      name: form.elements.name?.value || "",
      notes: form.elements.notes?.value || "",
    }
    : {};
  try {
    const response = await fetch(form.dataset.apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Run action returned ${response.status}`);
    }
    if (startForm && data.run?.id) {
      window.location.href = `/admin/runs/${data.run.id}`;
      return;
    }
    window.dispatchEvent(new Event("live:refresh"));
  } catch (error) {
    window.alert(error.message || "Run action failed.");
  }
});

if (liveRoot?.dataset.livePage === "requests") {
  initRequestsLivePage(liveRoot);
} else if (liveRoot?.dataset.livePage === "runs") {
  initRunsLivePage(liveRoot);
} else if (liveRoot?.dataset.livePage === "request-detail") {
  initRequestDetailLivePage(liveRoot);
} else if (liveRoot?.dataset.livePage === "run-detail") {
  initRunDetailLivePage(liveRoot);
} else if (liveRoot?.dataset.livePage === "settings") {
  initSettingsLivePage(liveRoot);
}
