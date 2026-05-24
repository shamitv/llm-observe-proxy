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

  const renderSummary = (scenarios) => {
    const summaryList = document.querySelector("[data-what-if-summary]");
    if (!summaryList) {
      return;
    }
    summaryList.replaceChildren();
    if (!scenarios.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No comparisons selected.";
      summaryList.append(empty);
      return;
    }
    const baseline = scenarios[0]?.total_cost_usd;
    scenarios.slice(0, 3).forEach((scenario, index) => {
      const total = scenario.display?.total_cost_usd || "-";
      let delta = index === 0 ? "Baseline" : "";
      if (index > 0 && typeof baseline === "number" && typeof scenario.total_cost_usd === "number") {
        const amount = scenario.total_cost_usd - baseline;
        const percent = baseline ? (amount / baseline) * 100 : null;
        delta = `${amount >= 0 ? "+" : ""}${amount.toFixed(4)}${percent === null ? "" : ` · ${percent >= 0 ? "+" : ""}${percent.toFixed(1)}%`}`;
      }
      const row = document.createElement("div");
      row.className = `what-if-summary-row${index === 0 ? " current" : ""}`;
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
  window.renderWhatIfSummary = () => renderSummary(latestScenarios);

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
      renderOptions();
      renderScenarios(scenarios);
      renderSummary(scenarios);
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
        setEnhancedActiveOption(wrapper, menu.querySelectorAll(".enhanced-select-option").length - 1);
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
  updateEnhancedSelectLabel(wrapper);
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
    const model = form.querySelector("input[name='model']")?.value || "";
    if (result) {
      result.textContent = "Running simulation...";
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
        route.textContent = `Route: ${data.matched_route || "global fallback or no match"}`;
        const upstream = document.createElement("code");
        upstream.textContent = `${data.upstream_url || "-"} -> ${data.upstream_model || "-"}`;
        const provider = document.createElement("span");
        provider.textContent = `Provider: ${data.provider_name || data.provider_slug || "-"}`;
        result.append(status, route, upstream, provider);
      }
    } catch (error) {
      if (result) {
        result.textContent = error.message || "Simulation failed.";
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
    wrap.append(createNode("span", { className: "signal-muted", textContent: "None" }));
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
  createNode("span", { textContent: item.semantic_summary || item.preview || "" }),
  createNode("a", {
    className: "request-row-link",
    href: `/admin/requests/${item.id}`,
    textContent: "View full details",
    "aria-label": `View full details for request #${item.id}`,
  }),
]);

const renderRequestRows = (tbody, items, showRun) => {
  tbody.replaceChildren();
  if (!items.length) {
    const row = createNode("tr");
    tableCell(row, "No captured requests yet.", "empty").colSpan = showRun ? 9 : 8;
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
      createNode("a", { href: `/admin/requests/${item.id}`, textContent: `#${item.id}` }),
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
    tableCell(row, renderSignals(item), "signals");
    tableCell(row, renderRequestSummary(item), "request-preview");
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
    const row = createNode("a", { className: "request-mobile-row", href: `/admin/requests/${item.id}` }, [
      createNode("span", { className: "mobile-dot" }),
      createNode("span", {}, [
        createNode("strong", { textContent: `#${item.id}` }),
        localTimeNode(item.created_at, item.created_at_table_fallback, "table"),
      ]),
      createNode("span", {}, [
        createNode("strong", { textContent: valueOrDash(item.model) }),
        createNode("small", { textContent: item.provider_name || item.billing_provider || item.route_name || "-" }),
      ]),
      renderStatusPill(item.status_label),
      createNode("span", {}, [
        createNode("strong", { textContent: valueOrDash(item.duration_display) }),
        createNode("small", { textContent: `${valueOrDash(item.tokens_per_second_display)} TPS` }),
      ]),
      renderCostCell(item),
      createNode("span", { className: "mobile-chevron", textContent: "›" }),
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
    "col-signals",
    "col-summary",
  ].forEach((className) => colgroup.append(createNode("col", { className })));
  const thead = createNode("thead");
  const headRow = createNode("tr");
  ["Request", "Model / Provider", ...(showRun ? ["Run"] : []), "Status", "Performance", "Tokens", "Cost", "Signals", "Summary"]
    .forEach((heading) => headRow.append(createNode("th", { textContent: heading })));
  thead.append(headRow);
  const tbody = createNode("tbody");
  renderRequestRows(tbody, items, showRun);
  table.append(colgroup, thead, tbody);
  container.append(table);
  container.append(renderMobileRequestList(items, showRun));
  if (!options.compact) {
    renderPagination(container, pagination);
  }
  updatePendingElapsed();
};

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
  container.append(
    createNode("header", { className: "request-inspector-header" }, [
      createNode("div", {}, [
        createNode("h2", { textContent: `Request #${item.id}` }),
        renderStatusPill(item.status_label),
      ]),
      createNode("a", {
        className: "button ghost compact-button",
        href: `/admin/requests/${item.id}`,
        textContent: "Open",
      }),
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
    createNode("a", {
      className: "button ghost inspector-detail-link",
      href: `/admin/requests/${item.id}`,
      textContent: "View full details →",
    }),
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
    container.append(copy, form);
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
    }),
  ]));
  if (includeNotes) {
    form.append(createNode("label", {}, [
      "Notes",
      createNode("input", { name: "notes", placeholder: "Optional context" }),
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
    renderRequestsTable(table, latestItems, data.pagination, true);
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
  table?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }
    const requestRow = event.target.closest("[data-request-row]");
    if (requestRow) {
      window.location.href = `/admin/requests/${requestRow.dataset.requestId}`;
    }
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
    tableCell(row, renderStatusPill(run.is_active ? "active" : "complete"));
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

  const images = root.querySelector("[data-live-images-section]");
  images?.replaceChildren();
  if (images && data.images?.length) {
    const grid = createNode("div", { className: "image-grid" });
    data.images.forEach((image, index) => {
      grid.append(createNode("figure", {}, [
        createNode("img", { src: image.source, alt: `Request image ${index + 1}` }),
        createNode("figcaption", { textContent: image.mime_type || image.kind }),
      ]));
    });
    images.append(createNode("section", { className: "panel" }, [
      createNode("header", {}, [
        createNode("h2", { textContent: "Images Sent" }),
        createNode("span", { textContent: `${data.images.length} image${data.images.length === 1 ? "" : "s"}` }),
      ]),
      grid,
    ]));
  }

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
      createNode("span", { textContent: record.model_route || "global fallback" }),
    ]),
    createNode("code", { textContent: record.upstream_url }),
  ]));
  updatePendingElapsed();
};

const initRequestDetailLivePage = (root) => {
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
        createNode("span", { className: data.run.is_active ? "live-dot" : "muted", textContent: data.run.is_active ? "Live" : "Complete" }),
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
    meta.append(
      runStatusChip(`Started ${run.started_at_fallback}`),
      runStatusChip(`Open for ${run.open_duration_display}`),
      runStatusChip(`Status ${run.is_active ? "active" : "complete"}`, run.is_active ? "ok-chip" : ""),
    );
    if (data.stats.error_count) {
      meta.append(runStatusChip(`${data.stats.error_count_display} errors`, "error-chip"));
    }
    const side = createNode("div", { className: "run-summary-side" }, [meta]);
    if (run.is_active) {
      side.append(createNode("form", {
        className: "run-summary-action",
        method: "post",
        action: "/admin/runs/end",
        "data-live-run-end": true,
        "data-api-url": "/admin/api/runs/end",
      }, [
        createNode("button", { className: "button danger", type: "submit", textContent: "End run" }),
      ]));
    }
    const topline = createNode("div", { className: "run-summary-topline" }, [
      createNode("div", { className: "run-summary-title" }, [
        createNode("p", { className: "eyebrow", textContent: run.is_active ? "Run in progress" : "Completed run" }),
        createNode("div", { className: "run-title-line" }, [
          createNode("h1", { textContent: `Run: ${run.name}` }),
          runStatusChip(run.is_active ? "LIVE" : "DONE", run.is_active ? "live-chip" : ""),
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
  if (!startForm && !endForm) {
    return;
  }
  event.preventDefault();
  const form = startForm || endForm;
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
}
