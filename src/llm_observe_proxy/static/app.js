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
