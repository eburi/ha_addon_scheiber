const state = {
  config: { schema_version: 1, devices: [] },
  baseRevision: null,
  editingIndex: null,
  diagnostics: { errors: [], warnings: [] },
  discovery: { status: "idle", candidates: [], message_counts: {} },
  bloc7Discovery: { status: "idle", candidates: [] },
  expandedCandidates: {},
  controlState: {},
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

function blankSensor() {
  return {
    name: "",
    entity_id: "",
    sensor_type: "level",
    matcher: { pattern: "", mask: "0xFFFFFFFF" },
    value_config: { start_byte: 0, bit_length: 8, endian: "little", scale: 1.0 },
  };
}

function blankDevice(type = "bloc9") {
  return {
    type,
    bus_id: "",
    segment_id: 0,
    name: "",
    description: "",
    outputs: Object.fromEntries(outputs.map((name) => [name, blankOutput()])),
    sensors: [],
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

function deviceRouteSlug(device) {
  return Number(device.segment_id || 0) === 0
    ? `${device.bus_id}`
    : `${device.bus_id}_${device.segment_id}`;
}

function deviceLabel(device) {
  const type = (device.type || "bloc9").toUpperCase();
  return `${type} #${deviceRouteSlug(device)}`;
}

function bloc9CandidateLabel(candidate) {
  if ((candidate.segment_id || 0) === 0) {
    return `Bloc9 #${candidate.bus_id}`;
  }
  return `Bloc9 #${candidate.bus_id}_${candidate.segment_id}`;
}

function bloc9CandidateRouteDescription(candidate) {
  if ((candidate.segment_id || 0) === 0) {
    return "Native local-bus arbitration IDs (segment 0)";
  }
  return `Forwarded/segmented arbitration IDs on segment ${candidate.segment_id}`;
}

function renderStatus(runtime, config) {
  document.getElementById("runtime-status").innerHTML = `
    <div class="status-item"><span class="label">Bridge</span><span class="value">${runtime.running ? "Running" : "Stopped"}</span></div>
    <div class="status-item"><span class="label">CAN interface</span><span class="value">${runtime.can_interface}</span></div>
    <div class="status-item"><span class="label">MQTT</span><span class="value">${runtime.mqtt_host}:${runtime.mqtt_port}</span></div>
    <div class="status-item"><span class="label">Config file</span><span class="value">${runtime.config_path}</span></div>
    <div class="status-item"><span class="label">Last error</span><span class="value">${runtime.last_error || "None"}</span></div>
  `;

  document.getElementById("config-status").innerHTML = `
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

function summarizeOutputs(outputsMap = {}) {
  const rows = [];
  for (const [name, output] of Object.entries(outputsMap)) {
    if (output.enabled && output.role) {
      rows.push(`
        <div class="status-item">
          <div><strong>${name.toUpperCase()}</strong> <span class="pill secondary">${output.role}</span></div>
          <div class="muted">${output.name} &middot; ${output.entity_id}</div>
        </div>
      `);
      continue;
    }
    if (output.name) {
      rows.push(`
        <div class="status-item">
          <div><strong>${name.toUpperCase()}</strong> <span class="pill secondary">unassigned</span></div>
          <div class="muted">${output.name}</div>
        </div>
      `);
    }
  }
  return rows.length ? rows.join("") : `<div class="muted">No outputs configured.</div>`;
}

function summarizeSensors(sensors = []) {
  if (!sensors.length) {
    return `<div class="muted">No sensors configured.</div>`;
  }
  return sensors
    .map(
      (sensor) => `
        <div class="status-item">
          <div><strong>${sensor.name}</strong> <span class="pill secondary">${sensor.sensor_type}</span></div>
          <div class="muted">${sensor.entity_id}</div>
          <div class="muted">Pattern <span class="code-chip">${formatHex(sensor.matcher?.pattern)}</span> &middot; byte ${sensor.value_config?.start_byte}</div>
        </div>
      `
    )
    .join("");
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
    .map((device, index) => {
      const summary =
        device.type === "bloc7"
          ? summarizeSensors(device.sensors || [])
          : summarizeOutputs(device.outputs || {});
      return `
        <article class="device-card">
          <div class="device-card-header">
            <div>
              <h3>${deviceLabel(device)}</h3>
              <div class="muted">${device.name || "Unnamed device"}</div>
            </div>
            <div class="inline-actions">
              <button data-action="edit-device" data-index="${index}">Edit</button>
              <button data-action="delete-device" data-index="${index}">Delete</button>
            </div>
          </div>
          <div class="muted">${device.description || "No description"}</div>
          <div class="output-summary">${summary}</div>
        </article>
      `;
    })
    .join("");
}

function renderOutputEditor(device) {
  const container = document.getElementById("outputs-editor");
  container.innerHTML = outputs
    .map((name) => {
      const output = device.outputs?.[name] || blankOutput();
      const role = output.enabled ? output.role : "";
      const entityDisabled = !role;
      const brightnessDisabled = role !== "light";
      return `
        <div class="output-row">
          <label>
            <span>Output</span>
            <input type="text" value="${name.toUpperCase()}" disabled>
          </label>
          <label>
            <span>Role</span>
            <select data-output="${name}" data-field="role">
              <option value="">Not configured yet</option>
              <option value="light" ${role === "light" ? "selected" : ""}>Light</option>
              <option value="switch" ${role === "switch" ? "selected" : ""}>Switch</option>
            </select>
          </label>
          <label>
            <span>Name</span>
            <input type="text" data-output="${name}" data-field="name" value="${output.name || ""}">
          </label>
          <label>
            <span>Entity ID</span>
            <input type="text" data-output="${name}" data-field="entity_id" value="${output.entity_id || ""}" placeholder="Required once a role is selected" ${entityDisabled ? "disabled" : ""}>
          </label>
          <label>
            <span>Initial brightness</span>
            <input type="number" min="0" max="255" data-output="${name}" data-field="initial_brightness" value="${output.initial_brightness ?? ""}" ${brightnessDisabled ? "disabled" : ""}>
          </label>
        </div>
      `;
    })
    .join("");
}

function renderSensorEditor(device) {
  const container = document.getElementById("sensors-editor");
  const sensors = device.sensors || [];
  if (!sensors.length) {
    container.innerHTML = `<div class="empty-state">No sensors configured yet.</div>`;
    return;
  }

  container.innerHTML = sensors
    .map((sensor, index) => {
      const matcher = sensor.matcher || {};
      const valueConfig = sensor.value_config || {};
      return `
        <div class="sensor-row">
          <div class="section-header">
            <strong>Sensor ${index + 1}</strong>
            <button type="button" data-action="remove-sensor" data-sensor-index="${index}">Remove</button>
          </div>
          <div class="sensor-row-grid">
            <label>
              <span>Name</span>
              <input type="text" data-sensor-index="${index}" data-sensor-field="name" value="${sensor.name || ""}">
            </label>
            <label>
              <span>Entity ID</span>
              <input type="text" data-sensor-index="${index}" data-sensor-field="entity_id" value="${sensor.entity_id || ""}">
            </label>
            <label>
              <span>Sensor type</span>
              <select data-sensor-index="${index}" data-sensor-field="sensor_type">
                <option value="level" ${sensor.sensor_type === "level" ? "selected" : ""}>Level</option>
                <option value="voltage" ${sensor.sensor_type === "voltage" ? "selected" : ""}>Voltage</option>
              </select>
            </label>
            <label>
              <span>Matcher pattern</span>
              <input type="text" data-sensor-index="${index}" data-sensor-field="matcher.pattern" value="${formatHex(matcher.pattern)}" placeholder="0x02040582">
            </label>
            <label>
              <span>Matcher mask</span>
              <input type="text" data-sensor-index="${index}" data-sensor-field="matcher.mask" value="${formatHex(matcher.mask)}" placeholder="0xFFFFFFFF">
            </label>
            <label>
              <span>Start byte</span>
              <input type="number" min="0" data-sensor-index="${index}" data-sensor-field="value_config.start_byte" value="${valueConfig.start_byte ?? 0}">
            </label>
            <label>
              <span>Bit length</span>
              <input type="number" min="1" data-sensor-index="${index}" data-sensor-field="value_config.bit_length" value="${valueConfig.bit_length ?? 8}">
            </label>
            <label>
              <span>Endian</span>
              <select data-sensor-index="${index}" data-sensor-field="value_config.endian">
                <option value="little" ${valueConfig.endian === "little" ? "selected" : ""}>Little</option>
                <option value="big" ${valueConfig.endian === "big" ? "selected" : ""}>Big</option>
              </select>
            </label>
            <label>
              <span>Scale</span>
              <input type="number" step="any" data-sensor-index="${index}" data-sensor-field="value_config.scale" value="${valueConfig.scale ?? 1}">
            </label>
          </div>
        </div>
      `;
    })
    .join("");
}

function updateEditorSections(deviceType) {
  const isBloc7 = deviceType === "bloc7";
  document.getElementById("bloc9-editor-section").classList.toggle("hidden", isBloc7);
  document.getElementById("bloc7-editor-section").classList.toggle("hidden", !isBloc7);
  document.getElementById("segment-id-field").classList.toggle("hidden", isBloc7);
  const busIdInput = document.getElementById("device-bus-id");
  busIdInput.max = isBloc7 ? "255" : "15";
}

function openEditor(device = blankDevice("bloc9"), index = null) {
  state.editingIndex = index;
  document.getElementById("editor-card").classList.remove("hidden");
  document.getElementById("device-type").value = device.type || "bloc9";
  document.getElementById("device-bus-id").value = device.bus_id ?? "";
  document.getElementById("device-segment-id").value = device.segment_id ?? 0;
  document.getElementById("device-name").value = device.name || "";
  document.getElementById("device-description").value = device.description || "";
  document.getElementById("editor-title").textContent =
    index === null ? `Add ${(device.type || "bloc9").toUpperCase()} device` : `Edit ${deviceLabel(device)}`;
  updateEditorSections(device.type || "bloc9");
  renderOutputEditor(device);
  renderSensorEditor(device);
  clearMessage();
}

function closeEditor() {
  state.editingIndex = null;
  document.getElementById("editor-card").classList.add("hidden");
}

function parseIntegerLike(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (/^0x/i.test(text)) {
    const parsed = Number.parseInt(text, 16);
    return Number.isNaN(parsed) ? text : parsed;
  }
  const parsed = Number.parseInt(text, 10);
  return Number.isNaN(parsed) ? text : parsed;
}

function parseFloatLike(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const parsed = Number.parseFloat(text);
  return Number.isNaN(parsed) ? text : parsed;
}

function formatHex(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "string") return value;
  return `0x${Number(value).toString(16).toUpperCase()}`;
}

function readDeviceForm() {
  const type = document.getElementById("device-type").value;
  const device = blankDevice(type);
  device.type = type;
  device.bus_id = Number(document.getElementById("device-bus-id").value);
  device.segment_id =
    type === "bloc7"
      ? 0
      : Number(document.getElementById("device-segment-id").value || 0);
  device.name = document.getElementById("device-name").value.trim();
  device.description = document.getElementById("device-description").value.trim();

  if (type === "bloc7") {
    const sensors = [];
    document.querySelectorAll("#sensors-editor [data-sensor-index]").forEach((input) => {
      const index = Number(input.dataset.sensorIndex);
      const field = input.dataset.sensorField;
      if (!sensors[index]) {
        sensors[index] = blankSensor();
      }
      const value = input.value;
      if (field === "matcher.pattern" || field === "matcher.mask") {
        sensors[index].matcher[field.split(".")[1]] = parseIntegerLike(value);
      } else if (field === "value_config.start_byte" || field === "value_config.bit_length") {
        sensors[index].value_config[field.split(".")[1]] = parseIntegerLike(value);
      } else if (field === "value_config.scale") {
        sensors[index].value_config.scale = parseFloatLike(value);
      } else if (field.startsWith("value_config.")) {
        sensors[index].value_config[field.split(".")[1]] = value;
      } else {
        sensors[index][field] = value.trim ? value.trim() : value;
      }
    });
    device.sensors = sensors.filter(Boolean);
    return device;
  }

  document.querySelectorAll("#outputs-editor [data-output]").forEach((input) => {
    const outputName = input.dataset.output;
    const field = input.dataset.field;
    if (!device.outputs[outputName]) {
      device.outputs[outputName] = blankOutput();
    }
    if (field === "initial_brightness") {
      device.outputs[outputName][field] = input.value === "" ? null : Number(input.value);
      return;
    }
    device.outputs[outputName][field] = input.value;
  });

  for (const outputName of outputs) {
    const output = device.outputs[outputName];
    output.name = (output.name || "").trim();
    output.entity_id = (output.entity_id || "").trim();
    output.enabled = Boolean(output.role);
    if (!output.enabled) {
      device.outputs[outputName] = { ...blankOutput(), name: output.name };
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

function getControlState(candidateKey) {
  const key = String(candidateKey);
  if (!state.controlState[key]) {
    state.controlState[key] = {};
    for (const name of outputs) {
      state.controlState[key][name] = { role: "none", brightness: 128 };
    }
  }
  return state.controlState[key];
}

function renderOutputControls(candidate) {
  const candidateKey = String(candidate.candidate_key);
  const busId = Number(candidate.bus_id);
  const segmentId = Number(candidate.segment_id || 0);
  const ctrl = getControlState(candidateKey);
  const rows = outputs
    .map((name, switchNr) => {
      const current = ctrl[name];
      const roleOptions = ["none", "switch", "light"]
        .map(
          (role) =>
            `<option value="${role}" ${current.role === role ? "selected" : ""}>${role === "none" ? "—" : role.charAt(0).toUpperCase() + role.slice(1)}</option>`
        )
        .join("");

      let controls = "";
      if (current.role !== "none") {
        const dimControls =
          current.role === "light"
            ? `<input type="range" class="brightness-slider" min="0" max="255" value="${current.brightness}"
                data-action="set-brightness" data-candidate-key="${candidateKey}" data-output="${name}">
               <span class="brightness-value">${current.brightness}</span>`
            : "";
        controls = `
          <button data-action="send-control" data-bus-id="${busId}" data-segment-id="${segmentId}" data-candidate-key="${candidateKey}" data-switch-nr="${switchNr}" data-on="1" class="primary">On</button>
          <button data-action="send-control" data-bus-id="${busId}" data-segment-id="${segmentId}" data-candidate-key="${candidateKey}" data-switch-nr="${switchNr}" data-on="0">Off</button>
          ${dimControls}`;
      }

      return `
        <div class="output-control-row">
          <span class="output-label">${name.toUpperCase()}</span>
          <select data-action="set-output-role" data-candidate-key="${candidateKey}" data-output="${name}">${roleOptions}</select>
          <div class="control-widget">${controls}</div>
        </div>`;
    })
    .join("");

  return `
    <div class="output-controls">
      <div class="control-hint">Live test — commands are sent with bus ID ${busId} on segment ${segmentId}; nothing is saved.</div>
      ${rows}
    </div>`;
}

async function sendControl(busId, switchNr, on, brightness, segmentId) {
  const response = await fetch("./api/discovery/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bus_id: busId, segment_id: segmentId, switch_nr: switchNr, on, brightness }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    showMessage(payload.error || "Failed to send CAN command", "error");
    return;
  }
  const routeSlug = Number(payload.segment_id || 0) === 0 ? `${payload.bus_id}` : `${payload.bus_id}_${payload.segment_id}`;
  showMessage(`Sent ${payload.can_id || "CAN command"} to Bloc9 #${routeSlug}`, "success");
}

function renderDiscovery() {
  const container = document.getElementById("discovery-list");
  const status = document.getElementById("discovery-status");
  const toggleBtn = document.getElementById("discovery-toggle-button");
  const isRunning = state.discovery.status === "running";

  toggleBtn.textContent = isRunning ? "Stop discovery" : "Start discovery";
  toggleBtn.className = isRunning ? "secondary" : "primary";
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
    .map((candidate) => {
      const candidateKey = String(candidate.candidate_key);
      const expanded = !!state.expandedCandidates[candidateKey];
      const expandLabel = expanded ? "▲ Hide controls" : "▼ Test outputs";
      return `
        <article class="discovery-card">
          <div class="device-card-header">
            <div>
              <h3>${bloc9CandidateLabel(candidate)}</h3>
              <div class="muted">Confidence: ${candidate.confidence.level} (${candidate.confidence.score})</div>
            </div>
            <div class="inline-actions">
              <button data-action="toggle-expand" data-candidate-key="${candidateKey}">${expandLabel}</button>
              <button data-action="promote-candidate" data-bus-id="${candidate.bus_id}" data-segment-id="${candidate.segment_id || 0}">Use as device</button>
            </div>
          </div>
          <div class="muted">Bus/segment: <strong>${candidate.route_slug || deviceRouteSlug(candidate)}</strong></div>
          <div class="muted">${bloc9CandidateRouteDescription(candidate)}</div>
          <div class="muted">Groups seen: ${candidate.groups_seen.join(", ") || "heartbeat only"}</div>
          <div class="muted">Arbitration IDs: ${candidate.sample_arbitration_ids.join(", ")}</div>
          ${expanded ? renderOutputControls(candidate) : ""}
        </article>`;
    })
    .join("");
}

function renderBloc7Candidates() {
  const status = document.getElementById("bloc7-discovery-status");
  const container = document.getElementById("bloc7-discovery-list");
  status.innerHTML = `
    <div class="status-item"><span class="label">Inspector</span><span class="value">${state.bloc7Discovery.status || "idle"}</span></div>
    <div class="status-item"><span class="label">Frames seen</span><span class="value">${state.bloc7Discovery.total_messages || 0}</span></div>
    <div class="status-item"><span class="label">Unique CAN IDs</span><span class="value">${state.bloc7Discovery.unique_ids || 0}</span></div>
  `;

  if (!state.bloc7Discovery.candidates?.length) {
    container.className = "device-list empty-state";
    container.textContent = "No Bloc7 candidate frames have been identified yet.";
    return;
  }

  container.className = "device-list";
  container.innerHTML = state.bloc7Discovery.candidates
    .map((candidate) => {
      const reasons = (candidate.confidence?.reasons || [])
        .map((reason) => `<div class="muted">${reason}</div>`)
        .join("");
      const suggestions = (candidate.suggested_sensors || [])
        .map(
          (suggestion) => `
            <div class="candidate-suggestion">
              <div class="device-card-header">
                <div>
                  <strong>${suggestion.label}</strong>
                  <div class="muted">${suggestion.sensor_type} &middot; entity hint ${suggestion.entity_id_hint}</div>
                </div>
                <button data-action="draft-bloc7-sensor" data-candidate-key="${candidate.candidate_key}" data-suggestion-key="${suggestion.suggestion_key}">Create draft</button>
              </div>
              <div class="candidate-metadata">
                <span class="code-chip">pattern ${formatHex(suggestion.matcher.pattern)}</span>
                <span class="code-chip">mask ${formatHex(suggestion.matcher.mask)}</span>
                <span class="code-chip">byte ${suggestion.value_config.start_byte}</span>
                <span class="code-chip">scale ${suggestion.value_config.scale}</span>
              </div>
              <div class="muted">${suggestion.notes}</div>
              ${
                suggestion.history?.length
                  ? `<div class="candidate-history">${suggestion.history
                      .map((value) => `<span class="code-chip">${value}</span>`)
                      .join("")}</div>`
                  : ""
              }
            </div>
          `
        )
        .join("");

      return `
        <article class="discovery-card">
          <div class="device-card-header">
            <div>
              <h3>${candidate.title}</h3>
              <div class="muted">Confidence: ${candidate.confidence.level} (${candidate.confidence.score})</div>
            </div>
            <span class="code-chip">${candidate.arbitration_id}</span>
          </div>
          <div class="candidate-summary">
            <div class="muted">${candidate.summary}</div>
            <div class="candidate-metadata">
              <span class="code-chip">last ${candidate.last_data.join(" ")}</span>
              <span class="code-chip">${candidate.family}</span>
              <span class="code-chip">${candidate.freq_hz} Hz</span>
            </div>
            ${reasons}
            <div class="candidate-suggestion-list">${suggestions}</div>
          </div>
        </article>
      `;
    })
    .join("");
}

async function refreshDiscovery() {
  const response = await fetch("./api/discovery");
  state.discovery = await response.json();
  renderDiscovery();
}

async function refreshBloc7Candidates() {
  const response = await fetch("./api/discovery/bloc7");
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    state.bloc7Discovery = { status: "error", candidates: [], total_messages: 0, unique_ids: 0 };
    renderBloc7Candidates();
    if (payload.error) {
      showMessage(payload.error, "warning");
    }
    return;
  }
  state.bloc7Discovery = payload;
  renderBloc7Candidates();
}

async function toggleDiscovery() {
  if (state.discovery.status === "running") {
    const response = await fetch("./api/discovery/stop", { method: "POST" });
    state.discovery = await response.json();
    renderDiscovery();
    showMessage("Bloc9 discovery stopped", "success");
  } else {
    const response = await fetch("./api/discovery/start", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      showMessage(payload.error || "Failed to start discovery", "error");
      return;
    }
    state.discovery = payload;
    renderDiscovery();
    showMessage("Bloc9 discovery started", "success");
  }
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

function promoteCandidate(busId, segmentId = 0) {
  const existingIndex = state.config.devices.findIndex(
    (device) =>
      device.type === "bloc9" &&
      Number(device.bus_id) === Number(busId) &&
      Number(device.segment_id || 0) === Number(segmentId)
  );
  if (existingIndex >= 0) {
    openEditor(state.config.devices[existingIndex], existingIndex);
    return;
  }
  const device = blankDevice("bloc9");
  device.bus_id = Number(busId);
  device.segment_id = Number(segmentId);
  openEditor(device, null);
}

function nextBloc7BusId() {
  const ids = state.config.devices
    .filter((device) => device.type === "bloc7")
    .map((device) => Number(device.bus_id))
    .filter((value) => Number.isFinite(value));
  return ids.length ? Math.max(...ids) + 1 : 1;
}

function createBloc7DraftFromSuggestion(candidateKey, suggestionKey) {
  const candidate = (state.bloc7Discovery.candidates || []).find(
    (item) => item.candidate_key === candidateKey
  );
  const suggestion = candidate?.suggested_sensors?.find(
    (item) => item.suggestion_key === suggestionKey
  );
  if (!candidate || !suggestion) {
    showMessage("The selected Bloc7 suggestion is no longer available", "error");
    return;
  }

  const device = blankDevice("bloc7");
  device.bus_id = nextBloc7BusId();
  device.name = `Bloc7 candidate ${device.bus_id}`;
  device.description = `Provisional draft from ${candidate.arbitration_id} (${candidate.family})`;
  device.sensors = [
    {
      name: suggestion.name_hint,
      entity_id: suggestion.entity_id_hint,
      sensor_type: suggestion.sensor_type,
      matcher: {
        pattern: suggestion.matcher.pattern,
        mask: suggestion.matcher.mask,
      },
      value_config: {
        start_byte: suggestion.value_config.start_byte,
        bit_length: suggestion.value_config.bit_length,
        endian: suggestion.value_config.endian,
        scale: suggestion.value_config.scale,
      },
    },
  ];
  openEditor(device, null);
  showMessage("Created a provisional Bloc7 sensor draft from the selected CAN frame", "success");
}

document.addEventListener("click", async (event) => {
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
    promoteCandidate(event.target.dataset.busId, event.target.dataset.segmentId || 0);
  }

  if (action === "toggle-expand") {
    const candidateKey = event.target.dataset.candidateKey;
    state.expandedCandidates[candidateKey] = !state.expandedCandidates[candidateKey];
    renderDiscovery();
  }

  if (action === "send-control") {
    const busId = Number(event.target.dataset.busId);
    const segmentId = Number(event.target.dataset.segmentId || 0);
    const candidateKey = event.target.dataset.candidateKey;
    const switchNr = Number(event.target.dataset.switchNr);
    const on = event.target.dataset.on === "1";
    const output = outputs[switchNr];
    const ctrl = getControlState(candidateKey);
    const brightness = on && ctrl[output]?.role === "light" ? ctrl[output].brightness : null;
    await sendControl(busId, switchNr, on, brightness, segmentId);
  }

  if (action === "remove-sensor") {
    const device = readDeviceForm();
    device.sensors.splice(Number(event.target.dataset.sensorIndex), 1);
    renderSensorEditor(device);
  }

  if (action === "draft-bloc7-sensor") {
    createBloc7DraftFromSuggestion(
      event.target.dataset.candidateKey,
      event.target.dataset.suggestionKey
    );
  }
});

document.addEventListener("change", (event) => {
  if (event.target.dataset.action === "set-output-role") {
    const candidateKey = event.target.dataset.candidateKey;
    const output = event.target.dataset.output;
    const ctrl = getControlState(candidateKey);
    ctrl[output].role = event.target.value;
    renderDiscovery();
    return;
  }

  if (event.target.id === "device-type") {
    const current = readDeviceForm();
    const nextType = event.target.value;
    const nextDevice =
      nextType === current.type
        ? current
        : {
            ...blankDevice(nextType),
            bus_id: current.bus_id,
            name: current.name,
            description: current.description,
          };
    openEditor(nextDevice, state.editingIndex);
    return;
  }

  if (event.target.dataset.field !== "role") return;
  renderOutputEditor(readDeviceForm());
});

document.addEventListener("input", (event) => {
  if (event.target.dataset.action === "set-brightness") {
    const candidateKey = event.target.dataset.candidateKey;
    const output = event.target.dataset.output;
    const value = Number(event.target.value);
    const ctrl = getControlState(candidateKey);
    ctrl[output].brightness = value;
    const label = event.target.closest(".output-control-row")?.querySelector(".brightness-value");
    if (label) label.textContent = value;
  }
});

document.getElementById("add-bloc9-button").addEventListener("click", () => openEditor(blankDevice("bloc9")));
document.getElementById("add-bloc7-button").addEventListener("click", () => {
  const device = blankDevice("bloc7");
  device.bus_id = nextBloc7BusId();
  openEditor(device);
});
document.getElementById("add-sensor-button").addEventListener("click", () => {
  const device = readDeviceForm();
  device.sensors.push(blankSensor());
  renderSensorEditor(device);
});
document.getElementById("cancel-edit-button").addEventListener("click", closeEditor);
document.getElementById("apply-button").addEventListener("click", validateAndApply);
document.getElementById("discovery-toggle-button").addEventListener("click", toggleDiscovery);
document.getElementById("bloc7-refresh-button").addEventListener("click", refreshBloc7Candidates);

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
  await Promise.all([loadConfig(), refreshStatus(), refreshDiscovery(), refreshBloc7Candidates()]);
  setInterval(refreshStatus, 5000);
  setInterval(refreshDiscovery, 2000);
  setInterval(refreshBloc7Candidates, 4000);
}

initialize().catch((error) => {
  showMessage(error.message || "Failed to initialize the setup UI", "error");
});
