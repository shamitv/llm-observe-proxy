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
      renderOptions();
      renderScenarios(Array.isArray(data.scenarios) ? data.scenarios : []);
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
