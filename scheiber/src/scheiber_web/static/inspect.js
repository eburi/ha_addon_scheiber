const state = {
  status: "stopped",
  entries: [],
  selectedId: null,        // hex string like "0x023606C0"
  selectedIdInt: null,     // integer
  sortBy: "last_seen",
  sortDir: "desc",
  filterText: "",
  changesOnly: false,
  detail: null,
  startedAt: null,
  pollInterval: null,
  detailInterval: null,
};

// -----------------------------------------------------------------------
// Utilities
// -----------------------------------------------------------------------

function fmtTimestamp(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

function fmtRelative(ts) {
  if (!ts) return "—";
  const diff = (Date.now() / 1000) - ts;
  if (diff < 1) return "< 1s ago";
  if (diff < 60) return `${diff.toFixed(1)}s ago`;
  return `${Math.floor(diff / 60)}m ago`;
}

function fmtDuration(startedAt) {
  if (!startedAt) return "—";
  const secs = Math.floor(Date.now() / 1000 - startedAt);
  const hh = Math.floor(secs / 3600);
  const mm = Math.floor((secs % 3600) / 60);
  const ss = secs % 60;
  if (hh > 0) {
    return `${String(hh).padStart(2,"0")}:${String(mm).padStart(2,"0")}:${String(ss).padStart(2,"0")}`;
  }
  return `${String(mm).padStart(2,"0")}:${String(ss).padStart(2,"0")}`;
}

function hexBytes(data, prevData) {
  if (!data) return "";
  return data
    .map((b, i) => {
      const changed = prevData && i < prevData.length && prevData[i] !== b;
      return `<span class="hex-byte${changed ? " changed" : ""}">${b.toString(16).padStart(2, "0").toUpperCase()}</span>`;
    })
    .join(" ");
}

// -----------------------------------------------------------------------
// Status bar
// -----------------------------------------------------------------------

function updateStatusBar(snapshot) {
  document.getElementById("inspect-status-value").textContent =
    snapshot.status === "running" ? "Running" : "Stopped";
  document.getElementById("inspect-total-msgs").textContent = snapshot.total_messages ?? 0;
  document.getElementById("inspect-unique-ids").textContent = snapshot.unique_ids ?? 0;
  document.getElementById("inspect-duration").textContent = fmtDuration(snapshot.started_at);

  const isRunning = snapshot.status === "running";
  document.getElementById("inspect-start-btn").disabled = isRunning;
  document.getElementById("inspect-stop-btn").disabled = !isRunning;
  document.getElementById("inspect-clear-btn").disabled = !isRunning;
}

// -----------------------------------------------------------------------
// Table
// -----------------------------------------------------------------------

function filteredEntries() {
  let entries = state.entries;
  if (state.filterText) {
    const q = state.filterText.toLowerCase();
    entries = entries.filter((e) => e.arbitration_id.toLowerCase().includes(q));
  }
  if (state.changesOnly) {
    entries = entries.filter((e) => e.data_changed);
  }
  return entries;
}

function sortedEntries() {
  const entries = filteredEntries();
  const key = state.sortBy;
  const dir = state.sortDir === "asc" ? 1 : -1;
  return [...entries].sort((a, b) => {
    const av = a[key] ?? 0;
    const bv = b[key] ?? 0;
    if (av < bv) return -dir;
    if (av > bv) return dir;
    return 0;
  });
}

function renderTable() {
  const tbody = document.getElementById("inspect-tbody");
  const emptyState = document.getElementById("inspect-empty-state");
  const sorted = sortedEntries();

  if (sorted.length === 0) {
    tbody.innerHTML = "";
    emptyState.style.display = "";
    return;
  }
  emptyState.style.display = "none";

  tbody.innerHTML = sorted
    .map((e) => {
      const isSelected = e.arbitration_id_int === state.selectedIdInt;
      return `<tr class="inspect-row${isSelected ? " selected" : ""}" data-id="${e.arbitration_id_int}">
        <td><strong>${e.arbitration_id}</strong></td>
        <td>${e.count}</td>
        <td class="hide-mobile">${e.freq_hz.toFixed(2)}</td>
        <td>${fmtRelative(e.last_seen)}</td>
        <td class="hide-mobile">${e.dlc}</td>
        <td>${hexBytes(e.last_data, e.prev_data)}</td>
      </tr>`;
    })
    .join("");

  // Re-render sort indicators
  document.querySelectorAll(".inspect-table th[data-sort]").forEach((th) => {
    const col = th.dataset.sort;
    const base = th.textContent.replace(/[ ▲▼]/g, "");
    if (col === state.sortBy) {
      th.textContent = base + (state.sortDir === "asc" ? " ▲" : " ▼");
    } else {
      th.textContent = base;
    }
  });
}

// -----------------------------------------------------------------------
// Bit-diff rendering
// -----------------------------------------------------------------------

function renderBitDiff(bitDiff, container) {
  if (!bitDiff || bitDiff.length === 0) {
    container.innerHTML = `<div class="inspect-no-detail">No previous message to compare.</div>`;
    return;
  }

  container.innerHTML = bitDiff
    .map((b) => {
      const prevHex = b.prev_byte.toString(16).padStart(2, "0").toUpperCase();
      const currHex = b.curr_byte.toString(16).padStart(2, "0").toUpperCase();
      const changedClass = b.changed ? " changed" : "";

      const prevBits = b.prev_bits
        .split("")
        .map((bit, i) => {
          const c = b.changed_bit_positions.includes(i) ? " changed" : "";
          return `<span class="bit-cell${c}">${bit}</span>`;
        })
        .join("");

      const currBits = b.curr_bits
        .split("")
        .map((bit, i) => {
          const c = b.changed_bit_positions.includes(i) ? " changed" : "";
          return `<span class="bit-cell${c}">${bit}</span>`;
        })
        .join("");

      const mask = Array.from({ length: 8 }, (_, i) => {
        const c = b.changed_bit_positions.includes(i) ? " changed" : "";
        return `<span class="change-mask-cell${c}">${b.changed_bit_positions.includes(i) ? "^" : "."}</span>`;
      }).join("");

      return `<div class="bit-byte-block${changedClass}">
        <div class="byte-header">B${b.byte_index} 0x${prevHex}→0x${currHex}</div>
        <div class="bit-row prev">${prevBits}</div>
        <div class="bit-row">${currBits}</div>
        <div class="change-mask">${mask}</div>
      </div>`;
    })
    .join("");
}

// -----------------------------------------------------------------------
// Detail panel
// -----------------------------------------------------------------------

function renderDetail(detail) {
  if (!detail) return;

  document.getElementById("inspect-detail-title").textContent = `ID ${detail.arbitration_id}`;

  document.getElementById("inspect-detail-stats").innerHTML = `
    <div class="status-item"><span class="label">Count</span><span class="value">${detail.count}</span></div>
    <div class="status-item"><span class="label">Freq (Hz)</span><span class="value">${detail.freq_hz.toFixed(2)}</span></div>
    <div class="status-item"><span class="label">First seen</span><span class="value">${fmtTimestamp(detail.first_seen)}</span></div>
    <div class="status-item"><span class="label">Last seen</span><span class="value">${fmtTimestamp(detail.last_seen)}</span></div>
  `;

  renderBitDiff(detail.bit_diff, document.getElementById("inspect-bit-diff"));

  const historyContainer = document.getElementById("inspect-history");
  if (!detail.history || detail.history.length === 0) {
    historyContainer.innerHTML = `<div class="inspect-no-detail">No history yet.</div>`;
    return;
  }

  const rows = detail.history
    .map((h, i) => {
      const changedBits = (h.bit_diff || [])
        .filter((b) => b.changed)
        .map((b) => `B${b.byte_index}[${b.changed_bit_positions.join(",")}]`)
        .join(" ");

      return `<tr>
        <td>${detail.history.length - i}</td>
        <td>${fmtTimestamp(h.timestamp)}</td>
        <td>${hexBytes(h.data, h.bit_diff?.map ? h.bit_diff.map((b) => b.prev_byte) : null)}</td>
        <td class="changed-bits-list">${changedBits || "—"}</td>
      </tr>`;
    })
    .join("");

  historyContainer.innerHTML = `<table class="history-table">
    <thead>
      <tr><th>#</th><th>Timestamp</th><th>Data</th><th>Changed bits</th></tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function openDetail(arbIdInt) {
  state.selectedIdInt = arbIdInt;
  document.getElementById("inspect-detail-card").classList.remove("hidden");
  fetchDetail();
  if (!state.detailInterval && state.status === "running") {
    state.detailInterval = setInterval(fetchDetail, 1000);
  }
}

function closeDetail() {
  state.selectedIdInt = null;
  document.getElementById("inspect-detail-card").classList.add("hidden");
  if (state.detailInterval) {
    clearInterval(state.detailInterval);
    state.detailInterval = null;
  }
}

async function fetchDetail() {
  if (state.selectedIdInt === null) return;
  try {
    const hexId = state.selectedIdInt.toString(16).toUpperCase();
    const resp = await fetch(`./api/inspect/detail/${hexId}`);
    if (!resp.ok) return;
    state.detail = await resp.json();
    renderDetail(state.detail);
  } catch (_) {}
}

// -----------------------------------------------------------------------
// Polling
// -----------------------------------------------------------------------

async function fetchSnapshot() {
  try {
    const resp = await fetch("./api/inspect");
    if (!resp.ok) return;
    const data = await resp.json();
    state.status = data.status;
    state.entries = data.entries || [];
    state.startedAt = data.started_at;
    updateStatusBar(data);
    renderTable();
  } catch (_) {}
}

function startPolling() {
  if (state.pollInterval) return;
  state.pollInterval = setInterval(fetchSnapshot, 1000);
}

function stopPolling() {
  if (state.pollInterval) {
    clearInterval(state.pollInterval);
    state.pollInterval = null;
  }
}

// -----------------------------------------------------------------------
// Controls
// -----------------------------------------------------------------------

function hideMessages() {
  document.getElementById("inspect-bridge-warning").classList.add("hidden");
  document.getElementById("inspect-error-msg").classList.add("hidden");
}

async function startCapture() {
  hideMessages();
  try {
    const resp = await fetch("./api/inspect/start", { method: "POST" });
    const payload = await resp.json();
    if (!resp.ok) {
      if (resp.status === 409) {
        document.getElementById("inspect-bridge-warning").classList.remove("hidden");
      } else {
        const el = document.getElementById("inspect-error-msg");
        el.textContent = payload.error || "Failed to start capture";
        el.classList.remove("hidden");
      }
      return;
    }
    state.status = "running";
    state.entries = payload.entries || [];
    state.startedAt = payload.started_at;
    updateStatusBar(payload);
    renderTable();
    startPolling();
  } catch (err) {
    const el = document.getElementById("inspect-error-msg");
    el.textContent = err.message || "Network error";
    el.classList.remove("hidden");
  }
}

async function stopCapture() {
  stopPolling();
  if (state.detailInterval) {
    clearInterval(state.detailInterval);
    state.detailInterval = null;
  }
  try {
    const resp = await fetch("./api/inspect/stop", { method: "POST" });
    const payload = await resp.json();
    state.status = "stopped";
    state.entries = payload.entries || [];
    updateStatusBar(payload);
    renderTable();
  } catch (_) {}
}

async function clearCapture() {
  // Stop then start to reset
  await stopCapture();
  await startCapture();
}

// -----------------------------------------------------------------------
// Sort / filter event wiring
// -----------------------------------------------------------------------

document.querySelectorAll(".inspect-table th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (state.sortBy === col) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortBy = col;
      state.sortDir = col === "last_seen" ? "desc" : "asc";
    }
    renderTable();
  });
});

document.getElementById("inspect-filter").addEventListener("input", (e) => {
  state.filterText = e.target.value.trim();
  renderTable();
});

document.getElementById("inspect-changes-only").addEventListener("change", (e) => {
  state.changesOnly = e.target.checked;
  renderTable();
});

document.getElementById("inspect-tbody").addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-id]");
  if (!row) return;
  const id = parseInt(row.dataset.id, 10);
  if (state.selectedIdInt === id) {
    closeDetail();
  } else {
    openDetail(id);
  }
  renderTable();
});

document.getElementById("inspect-start-btn").addEventListener("click", startCapture);
document.getElementById("inspect-stop-btn").addEventListener("click", stopCapture);
document.getElementById("inspect-clear-btn").addEventListener("click", clearCapture);
document.getElementById("inspect-detail-close").addEventListener("click", () => {
  closeDetail();
  renderTable();
});

// -----------------------------------------------------------------------
// Init: load current snapshot (may already be running)
// -----------------------------------------------------------------------

(async () => {
  try {
    const resp = await fetch("./api/inspect");
    if (resp.ok) {
      const data = await resp.json();
      state.status = data.status;
      state.entries = data.entries || [];
      state.startedAt = data.started_at;
      updateStatusBar(data);
      renderTable();
      if (data.status === "running") startPolling();
    }
  } catch (_) {}
})();
