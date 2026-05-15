const state = {
  config: { schema_version: 1, devices: [] },
  baseRevision: null,
  editingIndex: null,
  diagnostics: { errors: [], warnings: [] },
  discovery: { status: "idle", candidates: [] },
};

const outputs = ["s1", "s2", "s3", "s4", "s5", "s6"];

function blankOutput() {
  return {
    enabled: false,
    role: null,
    name: "",
    entity_id: "",
    initial_brightness: null,
  };
}

function blankDevice() {
  return {
    type: "bloc9",
    bus_id: "",
    name: "",
    description: "",
    outputs: Object.fromEntries(outputs.map((name) => [name, blankOutput()])),
  };
}

function showMessage(message, level = "success") {
  const el = document.getElementById("flash-message");
  el.textContent = message;
  el.className = `flash-message ${level}`;
}

function clearMessage() {
  const el = document.getElementById("flash-message");
  el.textContent = "";
  el.className = "flash-message hidden";
}

function renderStatus(runtime, config) {
  const runtimeStatus = document.getElementById("runtime-status");
  runtimeStatus.innerHTML = `
    <div class="status-item"><span class="label">Bridge</span><span class="value">${runtime.running ? "Running" : "Stopped"}</span></div>
    <div class="status-item"><span class="label">CAN interface</span><span class="value">${runtime.can_interface}</span></div>
    <div class="status-item"><span class="label">MQTT</span><span class="value">${runtime.mqtt_host}:${runtime.mqtt_port}</span></div>
    <div class="status-item"><span class="label">Config file</span><span class="value">${runtime.config_path}</span></div>
    <div class="status-item"><span class="label">Last error</span><span class="value">${runtime.last_error || "None"}</span></div>
  `;

  const configStatus = document.getElementById("config-status");
  configStatus.innerHTML = `
    <div class="status-item"><span class="label">Config status</span><span class="value">${config.status}</span></div>
    <div class="status-item"><span class="label">Revision</span><span class="value">${config.revision || "Not saved yet"}</span></div>
  `;
}

function renderDiagnostics() {
  const container = document.getElementById("diagnostics");
  const parts = [];
  for (const warning of state.diagnostics.warnings || []) {
    parts.push(`<div class="diagnostic-item warning">${warning}</div>`);
  }
  for (const error of state.diagnostics.errors || []) {
    parts.push(`<div class="diagnostic-item error">${error.message}</div>`);
  }
  container.innerHTML = parts.join("");
}

function summarizeOutputs(outputsMap) {
  const rows = [];
  for (const [name, output] of Object.entries(outputsMap)) {
    if (!output.enabled || !output.role) continue;
    rows.push(`
      <div class="status-item">
        <div><strong>${name.toUpperCase()}</strong> <span class="pill secondary">${output.role}</span></div>
        <div class="muted">${output.name} &middot; ${output.entity_id}</div>
      </div>
    `);
  }
  return rows.length ? rows.join("") : `<div class="muted">No outputs configured.</div>`;
}

function renderDevices() {
  const container = document.getElementById("devices-list");
  const count = state.config.devices.length;
  document.getElementById("device-count").textContent = `${count} device${count === 1 ? "" : "s"}`;

  if (!count) {
    container.className = "device-list empty-state";
    container.textContent = "No devices configured yet.";
    return;
  }

  container.className = "device-list";
  container.innerHTML = state.config.devices
    .map((device, index) => `
      <article class="device-card">
        <div class="device-card-header">
          <div>
            <h3>Bloc9 #${device.bus_id}</h3>
            <div class="muted">${device.name || "Unnamed device"}</div>
          </div>
          <div class="inline-actions">
            <button data-action="edit-device" data-index="${index}">Edit</button>
            <button data-action="delete-device" data-index="${index}">Delete</button>
          </div>
        </div>
        <div class="muted">${device.description || "No description"}</div>
        <div class="output-summary">${summarizeOutputs(device.outputs)}</div>
      </article>
    `)
    .join("");
}

function renderOutputEditor(device) {
  const container = document.getElementById("outputs-editor");
  container.innerHTML = outputs
    .map((name) => {
      const output = device.outputs[name] || blankOutput();
      return `
        <div class="output-row">
          <label>
            <span>Output</span>
            <input type="text" value="${name.toUpperCase()}" disabled>
          </label>
          <label>
            <span>Role</span>
            <select data-output="${name}" data-field="role">
              <option value="">Disabled</option>
              <option value="light" ${output.role === "light" && output.enabled ? "selected" : ""}>Light</option>
              <option value="switch" ${output.role === "switch" && output.enabled ? "selected" : ""}>Switch</option>
            </select>
          </label>
          <label>
            <span>Name</span>
            <input type="text" data-output="${name}" data-field="name" value="${output.name || ""}">
          </label>
          <label>
            <span>Entity ID</span>
            <input type="text" data-output="${name}" data-field="entity_id" value="${output.entity_id || ""}">
          </label>
          <label>
            <span>Initial brightness</span>
            <input type="number" min="0" max="255" data-output="${name}" data-field="initial_brightness" value="${output.initial_brightness ?? ""}">
          </label>
        </div>
      `;
    })
    .join("");
}

function openEditor(device = blankDevice(), index = null) {
  state.editingIndex = index;
  document.getElementById("editor-card").classList.remove("hidden");
  document.getElementById("editor-title").textContent = index === null ? "Add Bloc9 device" : `Edit Bloc9 #${device.bus_id}`;
  document.getElementById("device-bus-id").value = device.bus_id;
  document.getElementById("device-name").value = device.name || "";
  document.getElementById("device-description").value = device.description || "";
  renderOutputEditor(device);
  clearMessage();
}

function closeEditor() {
  state.editingIndex = null;
  document.getElementById("editor-card").classList.add("hidden");
}

function readDeviceForm() {
  const device = blankDevice();
  device.bus_id = Number(document.getElementById("device-bus-id").value);
  device.name = document.getElementById("device-name").value.trim();
  device.description = document.getElementById("device-description").value.trim();

  document.querySelectorAll("#outputs-editor [data-output]").forEach((input) => {
    const outputName = input.dataset.output;
    const field = input.dataset.field;
    if (!device.outputs[outputName]) {
      device.outputs[outputName] = blankOutput();
    }
    const value = input.value;
    if (field === "initial_brightness") {
      device.outputs[outputName][field] = value === "" ? null : Number(value);
      return;
    }
    device.outputs[outputName][field] = value;
  });

  for (const outputName of outputs) {
    const output = device.outputs[outputName];
    output.enabled = Boolean(output.role);
    if (!output.enabled) {
      device.outputs[outputName] = blankOutput();
    }
  }

  return device;
}

async function refreshStatus() {
  const response = await fetch("./api/status");
  const payload = await response.json();
  renderStatus(payload.runtime, payload.config);
}

async function loadConfig() {
  const response = await fetch("./api/config");
  const payload = await response.json();
  state.config = payload.config || { schema_version: 1, devices: [] };
  state.baseRevision = payload.revision;
  state.diagnostics = payload.diagnostics || { errors: [], warnings: [] };
  renderDiagnostics();
  renderDevices();
}

function renderDiscovery() {
  const container = document.getElementById("discovery-list");
  const status = document.getElementById("discovery-status");
  status.innerHTML = `
    <div class="status-item"><span class="label">State</span><span class="value">${state.discovery.status || "idle"}</span></div>
    <div class="status-item"><span class="label">State updates</span><span class="value">${state.discovery.message_counts?.state_update || 0}</span></div>
    <div class="status-item"><span class="label">Heartbeats</span><span class="value">${state.discovery.message_counts?.heartbeat || 0}</span></div>
  `;

  if (!state.discovery.candidates?.length) {
    container.className = "device-list empty-state";
    container.textContent = "Discovery has not found any Bloc9 candidates yet.";
    return;
  }

  container.className = "device-list";
  container.innerHTML = state.discovery.candidates
    .map((candidate) => `
      <article class="discovery-card">
        <div class="device-card-header">
          <div>
            <h3>Bloc9 candidate #${candidate.bus_id}</h3>
            <div class="muted">Confidence: ${candidate.confidence.level} (${candidate.confidence.score})</div>
          </div>
          <button data-action="promote-candidate" data-bus-id="${candidate.bus_id}">Use as device</button>
        </div>
        <div class="muted">Groups seen: ${candidate.groups_seen.join(", ") || "heartbeat only"}</div>
        <div class="muted">Arbitration IDs: ${candidate.sample_arbitration_ids.join(", ")}</div>
      </article>
    `)
    .join("");
}

async function refreshDiscovery() {
  const response = await fetch("./api/discovery");
  state.discovery = await response.json();
  renderDiscovery();
}

async function startDiscovery() {
  const response = await fetch("./api/discovery/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ timeout_seconds: 60 }),
  });
  const payload = await response.json();
  if (!response.ok) {
    showMessage(payload.error || "Failed to start discovery", "error");
    return;
  }
  state.discovery = payload;
  renderDiscovery();
  showMessage("Bloc9 discovery started", "success");
}

async function stopDiscovery() {
  const response = await fetch("./api/discovery/stop", { method: "POST" });
  state.discovery = await response.json();
  renderDiscovery();
  showMessage("Bloc9 discovery stopped", "success");
}

async function validateAndApply() {
  clearMessage();
  const response = await fetch("./api/config/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config: state.config, base_revision: state.baseRevision }),
  });
  const payload = await response.json();
  if (!response.ok) {
    showMessage(payload.details || payload.error || "Failed to apply configuration", "error");
    if (payload.diagnostics) {
      state.diagnostics = payload.diagnostics;
      renderDiagnostics();
    }
    return;
  }
  state.config = payload.config;
  state.baseRevision = payload.revision;
  state.diagnostics = payload.diagnostics;
  renderDiagnostics();
  renderDevices();
  await refreshStatus();
  showMessage("Configuration saved and bridge reloaded", "success");
}

function promoteCandidate(busId) {
  const existingIndex = state.config.devices.findIndex((device) => Number(device.bus_id) === Number(busId));
  if (existingIndex >= 0) {
    openEditor(state.config.devices[existingIndex], existingIndex);
    return;
  }
  const device = blankDevice();
  device.bus_id = Number(busId);
  openEditor(device, null);
}

document.addEventListener("click", (event) => {
  const action = event.target.dataset.action;
  if (!action) return;

  if (action === "edit-device") {
    const index = Number(event.target.dataset.index);
    openEditor(state.config.devices[index], index);
  }

  if (action === "delete-device") {
    const index = Number(event.target.dataset.index);
    state.config.devices.splice(index, 1);
    renderDevices();
    showMessage("Device removed from the local draft", "warning");
  }

  if (action === "promote-candidate") {
    promoteCandidate(event.target.dataset.busId);
  }
});

document.getElementById("add-device-button").addEventListener("click", () => openEditor());
document.getElementById("cancel-edit-button").addEventListener("click", closeEditor);
document.getElementById("apply-button").addEventListener("click", validateAndApply);
document.getElementById("start-discovery-button").addEventListener("click", startDiscovery);
document.getElementById("stop-discovery-button").addEventListener("click", stopDiscovery);

document.getElementById("device-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const device = readDeviceForm();
  const draft = structuredClone(state.config);
  if (state.editingIndex === null) {
    draft.devices.push(device);
  } else {
    draft.devices[state.editingIndex] = device;
  }

  const response = await fetch("./api/config/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config: draft }),
  });
  const payload = await response.json();

  if (!response.ok || !payload.valid) {
    state.diagnostics = payload.diagnostics || { errors: [], warnings: [] };
    renderDiagnostics();
    showMessage("Fix validation errors before saving the device", "error");
    return;
  }

  state.config = payload.config;
  state.diagnostics = payload.diagnostics;
  renderDiagnostics();
  renderDevices();
  closeEditor();
  showMessage("Device saved to the local draft", "success");
});

async function initialize() {
  await Promise.all([loadConfig(), refreshStatus(), refreshDiscovery()]);
  setInterval(refreshStatus, 5000);
  setInterval(refreshDiscovery, 2000);
}

initialize().catch((error) => {
  showMessage(error.message || "Failed to initialize the setup UI", "error");
});
