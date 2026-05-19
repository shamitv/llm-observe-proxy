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
