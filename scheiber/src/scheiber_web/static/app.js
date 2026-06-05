const outputs = ["s1", "s2", "s3", "s4", "s5", "s6"];
const entityIdPattern = /^[a-z0-9_]+$/;
const resolveAppUrl = window.ScheiberWebPaths?.resolve || ((path) => path);

const state = {
  runtime: {
    running: false,
    last_error: null,
    read_only: false,
  },
  config: { schema_version: 1, devices: [] },
  baseRevision: null,
  diagnostics: { errors: [], warnings: [] },
  discovery: { status: "idle", candidates: [], message_counts: {} },
  bloc7Discovery: { status: "idle", candidates: [], total_messages: 0, unique_ids: 0 },
  setupHelper: {
    status: "idle",
    target_name: "",
    entity_id: null,
    target_role: "light",
    phase: "idle",
    instruction: "",
    active_run: null,
    completed_run: null,
  },
  setupHelperDraft: {
    target_name: "",
    entity_id: "",
    role: "light",
    output_name: "",
    selected_outputs: {},
    device_names: {},
  },
  activeTab: "bloc9",
  bloc9Drafts: {},
  bloc7Drafts: {},
  bloc7CandidateDrafts: {},
  busyActions: {},
  controlState: {},
  outputActivity: {},
  bloc9ToastHistory: {},
  inspectLoaded: false,
  bloc9CardExpansion: {},
  bloc9OutputExpansion: {},
};

const heartbeatManager = window.ScheiberHeartbeat?.createHeartbeatManager("setup");

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

function blankBloc9Device() {
  return {
    type: "bloc9",
    bus_id: "",
    segment_id: 0,
    name: "",
    description: "",
    outputs: Object.fromEntries(outputs.map((name) => [name, blankOutput()])),
  };
}

function blankBloc7Device() {
  return {
    type: "bloc7",
    bus_id: "",
    segment_id: 0,
    name: "",
    description: "",
    sensors: [],
  };
}

const bloc7SensorTypeLabels = {
  level: "Level",
  voltage: "Voltage",
  frequency: "Frequency",
  current: "Current",
  state_of_charge: "State of charge",
  raw: "Raw",
};

function renderBloc7SensorTypeOptions(selectedType, allowedTypes = Object.keys(bloc7SensorTypeLabels)) {
  return allowedTypes
    .map(
      (type) =>
        `<option value="${type}" ${selectedType === type ? "selected" : ""}>${bloc7SensorTypeLabels[type]}</option>`,
    )
    .join("");
}

function clone(value) {
  return structuredClone(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatHex(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "string") return value;
  return `0x${Number(value).toString(16).toUpperCase()}`;
}

function routeSlug(busId, segmentId = 0) {
  return Number(segmentId || 0) === 0 ? `${busId}` : `${busId}_${segmentId}`;
}

function domSafeId(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "-");
}

function bloc9KeyFor(deviceOrCandidate) {
  return routeSlug(deviceOrCandidate.bus_id, deviceOrCandidate.segment_id || 0);
}

function deviceLabel(device) {
  return `${String(device.type || "device").toUpperCase()} #${routeSlug(
    device.bus_id,
    device.segment_id || 0,
  )}`;
}

function toneLabel(status) {
  if (status === "synced") return "discovered + configured";
  if (status === "discovered") return "discovered";
  if (status === "configured") return "configured";
  return "draft";
}

function candidateLastSeen(candidate) {
  if (!candidate?.last_seen_at) return "No live updates yet";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - candidate.last_seen_at));
  if (seconds < 1) return "Updated just now";
  if (seconds < 60) return `Updated ${seconds}s ago`;
  return `Updated ${Math.floor(seconds / 60)}m ago`;
}

function devicesEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function parseArbitrationId(value) {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  const text = String(value ?? "").trim();
  if (!text) return null;
  const parsed = text.startsWith("0x") || text.startsWith("0X")
    ? Number.parseInt(text, 16)
    : Number.parseInt(text, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function captureActiveField() {
  const active = document.activeElement;
  if (!active || !active.dataset) return null;
  const selectorParts = [];
  for (const [name, value] of Object.entries(active.dataset)) {
    if (value !== undefined && value !== "") {
      selectorParts.push(`[data-${name.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}="${CSS.escape(value)}"]`);
    }
  }
  if (!selectorParts.length) return null;
  return {
    selector: `${active.tagName.toLowerCase()}${selectorParts.join("")}`,
    selectionStart:
      typeof active.selectionStart === "number" ? active.selectionStart : null,
    selectionEnd: typeof active.selectionEnd === "number" ? active.selectionEnd : null,
  };
}

function restoreActiveField(snapshot) {
  if (!snapshot?.selector) return;
  const target = document.querySelector(snapshot.selector);
  if (!target) return;
  target.focus({ preventScroll: true });
  if (
    typeof snapshot.selectionStart === "number" &&
    typeof target.setSelectionRange === "function"
  ) {
    target.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd);
  }
}

function rerender(callback) {
  const active = captureActiveField();
  callback();
  restoreActiveField(active);
}

function renderCurrentTab() {
  renderTabs();
  if (state.activeTab === "bloc9") {
    renderBloc9Cards();
    return;
  }
  if (state.activeTab === "bloc7") {
    renderBloc7Cards();
    return;
  }
  if (state.activeTab === "helper") {
    renderSetupHelperPanel();
    return;
  }
  renderInspectPanel();
}

function renderTabIfVisible(tabName) {
  if (state.activeTab !== tabName) return;
  renderCurrentTab();
}

function hasActiveEditor(kind) {
  const active = document.activeElement;
  const activeKind = active?.dataset?.cardKind || "";
  return Boolean(activeKind === kind || activeKind.startsWith(`${kind}-`));
}

function showToast(message, level = "success") {
  const region = document.getElementById("toast-region");
  const toast = document.createElement("div");
  toast.className = `toast ${level}`;
  toast.textContent = message;
  region.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("visible"));
  window.setTimeout(() => {
    toast.classList.remove("visible");
    window.setTimeout(() => toast.remove(), 220);
  }, 4200);
}

function setBusy(actionKey, isBusy) {
  state.busyActions[actionKey] = isBusy;
  rerender(renderCurrentTab);
}

function actionAttrs(actionKey, disabled = false, extra = "") {
  const isBusy = !!state.busyActions[actionKey];
  const attrs = [];
  if (disabled || isBusy) attrs.push("disabled");
  const classes = [];
  if (isBusy) classes.push("is-busy");
  if (extra) classes.push(extra);
  if (classes.length) attrs.push(`class="${classes.join(" ")}"`);
  return attrs.join(" ");
}

function updateOutputActivity(previousCandidates, nextCandidates) {
  const previousMap = Object.fromEntries(
    (previousCandidates || []).map((candidate) => [String(candidate.candidate_key), candidate]),
  );

  for (const candidate of nextCandidates || []) {
    const key = String(candidate.candidate_key);
    const previousOutputs = previousMap[key]?.latest_outputs || {};
    const nextOutputs = candidate.latest_outputs || {};
    for (const outputName of outputs) {
      const previousValue = previousOutputs[outputName];
      const nextValue = nextOutputs[outputName];
      if (!nextValue) continue;
      if (!previousValue || JSON.stringify(previousValue) !== JSON.stringify(nextValue)) {
        state.outputActivity[key] = state.outputActivity[key] || {};
        state.outputActivity[key][outputName] = Date.now();
        if (previousValue) {
          announceBloc9StatusChange(candidate, outputName, previousValue, nextValue);
        }
      }
    }
  }
}

function describeBloc9OutputState(outputName, value) {
  if (!value) return `${outputName.toUpperCase()} unknown`;
  if (!value.state) return `${outputName.toUpperCase()} OFF`;
  return `${outputName.toUpperCase()} ON (${value.effective_brightness})`;
}

function bloc9OutputDisplayName(outputName, output) {
  return String(output?.name || "").trim() || outputName.toUpperCase();
}

function bloc9CardStateSummary(draft, candidate) {
  const liveOutputs = candidate?.latest_outputs || {};
  const summaries = outputs
    .filter((outputName) => liveOutputs[outputName])
    .map((outputName) => {
      const output = draft.outputs?.[outputName] || blankOutput();
      const live = liveOutputs[outputName];
      return `${bloc9OutputDisplayName(outputName, output)}: ${live.state ? `On ${live.effective_brightness}` : "Off"}`;
    });

  if (summaries.length) {
    return summaries.join(" · ");
  }

  return candidate ? "No live output status yet" : "Configured without live discovery yet";
}

function announceBloc9StatusChange(candidate, outputName, previousValue, nextValue) {
  if (state.activeTab !== "bloc9") return;
  const message = `Bloc9 #${bloc9KeyFor(candidate)} ${describeBloc9OutputState(outputName, nextValue)}`;
  const historyKey = `${candidate.candidate_key}:${outputName}:${JSON.stringify(nextValue)}`;
  const lastShownAt = state.bloc9ToastHistory[historyKey];
  if (lastShownAt && Date.now() - lastShownAt < 2500) return;

  state.bloc9ToastHistory[historyKey] = Date.now();
  const level = nextValue.state ? "success" : "warning";
  if (JSON.stringify(previousValue) !== JSON.stringify(nextValue)) {
    showToast(message, level);
  }
}

function outputIsActive(candidateKey, outputName) {
  const changedAt = state.outputActivity[String(candidateKey)]?.[outputName];
  return Boolean(changedAt && Date.now() - changedAt < 3200);
}

function renderDiagnostics() {
  const container = document.getElementById("global-diagnostics");
  const warnings = state.diagnostics.warnings || [];
  const errors = state.diagnostics.errors || [];
  if (!warnings.length && !errors.length) {
    container.className = "global-diagnostics hidden";
    container.innerHTML = "";
    return;
  }

  const items = [
    ...errors.map(
      (error) =>
        `<div class="diagnostic-item error">${escapeHtml(error.message || "Validation error")}</div>`,
    ),
    ...warnings.map(
      (warning) => `<div class="diagnostic-item warning">${escapeHtml(warning)}</div>`,
    ),
  ];
  container.className = "global-diagnostics";
  container.innerHTML = items.join("");
}

function renderHeader() {
  const pill = document.getElementById("bridge-pill");
  const stateLabel = document.getElementById("bridge-state-label");
  const errorWrap = document.getElementById("bridge-error");
  const errorText = document.getElementById("bridge-error-text");
  const running = !!state.runtime.running;

  pill.className = `runtime-pill ${running ? "running" : "stopped"}`;
  stateLabel.textContent = running ? "Bridge running" : "Bridge stopped";

  if (state.runtime.last_error) {
    errorWrap.classList.remove("hidden");
    errorText.textContent = state.runtime.last_error;
  } else {
    errorWrap.classList.add("hidden");
    errorText.textContent = "";
  }
}

function renderTabs() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.activeTab);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === state.activeTab);
  });
}

function getControlState(cardKey, outputName) {
  const key = String(cardKey);
  state.controlState[key] = state.controlState[key] || {};
  state.controlState[key][outputName] = state.controlState[key][outputName] || {
    brightness: 255,
  };
  return state.controlState[key][outputName];
}

function outputUsesBrightness(output) {
  return output?.role === "light";
}

function outputUsesPulse(roleOrOutput) {
  const role =
    typeof roleOrOutput === "string" ? roleOrOutput : roleOrOutput?.role;
  return role === "pulse";
}

function getConfiguredBloc9Map() {
  return Object.fromEntries(
    state.config.devices
      .filter((device) => device.type === "bloc9")
      .map((device) => [bloc9KeyFor(device), device]),
  );
}

function getDiscoveredBloc9Map() {
  return Object.fromEntries(
    (state.discovery.candidates || []).map((candidate) => [bloc9KeyFor(candidate), candidate]),
  );
}

function ensureBloc9Draft(cardKey, configuredDevice, discoveredCandidate) {
  if (state.bloc9Drafts[cardKey]) return state.bloc9Drafts[cardKey];
  if (configuredDevice) {
    state.bloc9Drafts[cardKey] = clone(configuredDevice);
    return state.bloc9Drafts[cardKey];
  }
  const draft = blankBloc9Device();
  draft.bus_id = Number(discoveredCandidate?.bus_id ?? "");
  draft.segment_id = Number(discoveredCandidate?.segment_id || 0);
  state.bloc9Drafts[cardKey] = draft;
  return draft;
}

function collectEntityIds(excludedDevicePredicate) {
  const entityIds = new Map();
  for (const device of state.config.devices) {
    if (excludedDevicePredicate?.(device)) continue;
    if (device.type === "bloc9") {
      for (const outputName of outputs) {
        const output = device.outputs?.[outputName];
        if (output?.enabled && output.entity_id) {
          if (!entityIds.has(output.entity_id)) entityIds.set(output.entity_id, new Set());
          entityIds.get(output.entity_id).add(output.role);
        }
      }
      continue;
    }
    for (const sensor of device.sensors || []) {
      if (sensor.entity_id) entityIds.set(sensor.entity_id, new Set(["sensor"]));
    }
  }
  return entityIds;
}

function validateBloc9Draft(draft, cardKey) {
  const errors = {};
  const seenEntityIds = collectEntityIds(
    (device) => device.type === "bloc9" && bloc9KeyFor(device) === cardKey,
  );
  const localEntityIds = new Map();

  if (!Number.isInteger(Number(draft.bus_id)) || Number(draft.bus_id) < 0 || Number(draft.bus_id) > 15) {
    errors["device.bus_id"] = "Bus ID must be between 0 and 15.";
  }
  if (
    !Number.isInteger(Number(draft.segment_id)) ||
    Number(draft.segment_id) < 0 ||
    Number(draft.segment_id) > 7
  ) {
    errors["device.segment_id"] = "Segment ID must be between 0 and 7.";
  }

  for (const outputName of outputs) {
    const output = draft.outputs?.[outputName] || blankOutput();
    const role = output.role || "";
    const basePath = `outputs.${outputName}`;

    if (!role) continue;
    if (!["light", "switch", "pulse"].includes(role)) {
      errors[`${basePath}.role`] = "Choose light, switch, or pulse.";
      continue;
    }
    if (!String(output.name || "").trim()) {
      errors[`${basePath}.name`] = "Configured outputs need a name.";
    }
    const entityId = String(output.entity_id || "").trim();
    if (!entityId) {
      errors[`${basePath}.entity_id`] = "Configured outputs need an entity ID.";
    } else if (
      entityId.startsWith("light.")
      || entityId.startsWith("switch.")
      || entityId.startsWith("button.")
    ) {
      errors[`${basePath}.entity_id`] = "Do not include the Home Assistant domain.";
    } else if (!entityIdPattern.test(entityId)) {
      errors[`${basePath}.entity_id`] =
        "Use lowercase letters, numbers, and underscores only.";
    } else {
      const seenRoles = seenEntityIds.get(entityId);
      const localRoles = localEntityIds.get(entityId);
      const conflictingSeenRole = seenRoles && !seenRoles.has(role);
      const conflictingLocalRole = localRoles && !localRoles.has(role);
      if (conflictingSeenRole || conflictingLocalRole) {
        errors[`${basePath}.entity_id`] =
          "This entity ID is already used by a different role.";
      } else {
        if (!localEntityIds.has(entityId)) localEntityIds.set(entityId, new Set());
        localEntityIds.get(entityId).add(role);
      }
    }

    const brightness = output.initial_brightness;
    if (role === "light" && brightness !== null && brightness !== "") {
      if (!Number.isInteger(Number(brightness)) || Number(brightness) < 0 || Number(brightness) > 255) {
        errors[`${basePath}.initial_brightness`] = "Use a brightness from 0 to 255.";
      }
    }
    if (role !== "light" && brightness !== null && brightness !== "") {
      errors[`${basePath}.initial_brightness`] =
        "Initial brightness is only supported for lights.";
    }
  }

  return { valid: Object.keys(errors).length === 0, errors };
}

function buildBloc9DraftForSave(draft) {
  const next = blankBloc9Device();
  next.bus_id = Number(draft.bus_id);
  next.segment_id = Number(draft.segment_id || 0);
  next.name = String(draft.name || "").trim();
  next.description = String(draft.description || "").trim();
  next.outputs = Object.fromEntries(
    outputs.map((outputName) => {
      const output = draft.outputs?.[outputName] || blankOutput();
      const role = output.role || null;
      return [
        outputName,
        {
          enabled: Boolean(role),
          role,
          name: String(output.name || "").trim(),
          entity_id: String(output.entity_id || "").trim(),
          initial_brightness:
            output.initial_brightness === "" || output.initial_brightness === null
              ? null
              : Number(output.initial_brightness),
        },
      ];
    }),
  );
  return next;
}

function bloc9FieldClass(validation, fieldPath, dirty) {
  const classes = ["field-shell"];
  if (validation.errors[fieldPath]) classes.push("invalid");
  if (dirty) classes.push("dirty");
  return classes.join(" ");
}

function isBloc9CardExpanded(cardKey) {
  if (!(cardKey in state.bloc9CardExpansion)) {
    state.bloc9CardExpansion[cardKey] = false;
  }
  return state.bloc9CardExpansion[cardKey];
}

function isBloc9OutputExpanded(cardKey, outputName) {
  const key = String(cardKey);
  state.bloc9OutputExpansion[key] = state.bloc9OutputExpansion[key] || {};
  if (!(outputName in state.bloc9OutputExpansion[key])) {
    state.bloc9OutputExpansion[key][outputName] = false;
  }
  return state.bloc9OutputExpansion[key][outputName];
}

function renderBloc9OutputRow(cardKey, draft, baseline, candidate, outputName, validation) {
  const output = draft.outputs?.[outputName] || blankOutput();
  const baselineOutput = baseline?.outputs?.[outputName] || blankOutput();
  const live = candidate?.latest_outputs?.[outputName];
  const control = getControlState(cardKey, outputName);
  const liveState = live
    ? live.state
      ? `On · ${live.effective_brightness}`
      : "Off"
    : "No live status";
  const liveTone = live ? (live.state ? "on" : "off") : "unknown";
  const liveFlash = candidate && outputIsActive(candidate.candidate_key, outputName);
  const canUseBrightness = outputUsesBrightness(output);
  const brightnessValue =
    output.initial_brightness === null || output.initial_brightness === undefined
      ? ""
      : output.initial_brightness;
  const isExpanded = isBloc9OutputExpanded(cardKey, outputName);
  const outputPanelId = `bloc9-output-${domSafeId(cardKey)}-${outputName}`;
  const outputLabel = bloc9OutputDisplayName(outputName, output);
  const outputSummary = output.role ? `${output.role} configured` : "Not configured";
  const isPulse = outputUsesPulse(output);

  return `
    <section class="output-card${liveFlash ? " live-change" : ""}">
      <button
        type="button"
        class="collapse-toggle output-card-header"
        data-action="toggle-bloc9-output"
        data-card-key="${escapeHtml(cardKey)}"
        data-output="${outputName}"
        aria-expanded="${isExpanded ? "true" : "false"}"
        aria-controls="${outputPanelId}"
      >
        <div class="collapse-toggle-main">
          <div>
            <h4>${escapeHtml(outputLabel)}</h4>
            <p>${escapeHtml(outputName.toUpperCase())} · ${escapeHtml(outputSummary)} · ${escapeHtml(candidateLastSeen(candidate))}</p>
          </div>
          <span class="live-state ${liveTone}">
            <span class="state-beacon${liveFlash ? " flashing" : ""}"></span>
            ${escapeHtml(liveState)}
          </span>
        </div>
        <span class="collapse-indicator" aria-hidden="true">${isExpanded ? "−" : "+"}</span>
      </button>

      <div id="${outputPanelId}" class="collapse-body${isExpanded ? "" : " hidden"}">
        <div class="card-grid compact-grid">
          <label class="${bloc9FieldClass(validation, `outputs.${outputName}.role`, output.role !== baselineOutput.role)}">
            <span>Role</span>
            <select data-card-kind="bloc9" data-card-key="${escapeHtml(cardKey)}" data-output="${outputName}" data-field="role">
              <option value="" ${!output.role ? "selected" : ""}>Not configured</option>
              <option value="light" ${output.role === "light" ? "selected" : ""}>Light</option>
              <option value="switch" ${output.role === "switch" ? "selected" : ""}>Switch</option>
              <option value="pulse" ${output.role === "pulse" ? "selected" : ""}>Pulse</option>
            </select>
            ${validation.errors[`outputs.${outputName}.role`] ? `<small>${escapeHtml(validation.errors[`outputs.${outputName}.role`])}</small>` : ""}
          </label>

          <label class="${bloc9FieldClass(validation, `outputs.${outputName}.name`, output.name !== baselineOutput.name)}">
            <span>Name</span>
            <input
              type="text"
              value="${escapeHtml(output.name || "")}"
              data-card-kind="bloc9"
              data-card-key="${escapeHtml(cardKey)}"
              data-output="${outputName}"
              data-field="name"
            >
            ${validation.errors[`outputs.${outputName}.name`] ? `<small>${escapeHtml(validation.errors[`outputs.${outputName}.name`])}</small>` : ""}
          </label>

          <label class="${bloc9FieldClass(validation, `outputs.${outputName}.entity_id`, output.entity_id !== baselineOutput.entity_id)}">
            <span>Entity ID</span>
            <input
              type="text"
              value="${escapeHtml(output.entity_id || "")}"
              placeholder="Required when a role is selected"
              data-card-kind="bloc9"
              data-card-key="${escapeHtml(cardKey)}"
              data-output="${outputName}"
              data-field="entity_id"
            >
            ${validation.errors[`outputs.${outputName}.entity_id`] ? `<small>${escapeHtml(validation.errors[`outputs.${outputName}.entity_id`])}</small>` : ""}
          </label>

          ${
            canUseBrightness
              ? `<label class="${bloc9FieldClass(validation, `outputs.${outputName}.initial_brightness`, brightnessValue !== (baselineOutput.initial_brightness ?? ""))}">
            <span>Initial brightness</span>
            <input
              type="number"
              min="0"
              max="255"
              value="${escapeHtml(brightnessValue)}"
              placeholder="Optional for lights"
              data-card-kind="bloc9"
              data-card-key="${escapeHtml(cardKey)}"
              data-output="${outputName}"
              data-field="initial_brightness"
            >
            ${validation.errors[`outputs.${outputName}.initial_brightness`] ? `<small>${escapeHtml(validation.errors[`outputs.${outputName}.initial_brightness`])}</small>` : ""}
          </label>`
              : ""
          }
        </div>

        <div class="test-controls">
          <div class="test-controls-header">
            <strong>Live test</strong>
            <span class="muted">Commands are sent immediately and never saved by themselves.</span>
          </div>
          <div class="test-controls-row">
            ${
              canUseBrightness
                ? `<label class="slider-field">
              <span>Brightness</span>
              <input
                type="range"
                min="0"
                max="255"
                value="${control.brightness}"
                data-card-kind="bloc9-control"
                data-card-key="${escapeHtml(cardKey)}"
                data-output="${outputName}"
                data-field="brightness"
              >
              <span class="slider-value">${control.brightness}</span>
            </label>`
                : `<span class="muted">${isPulse
                  ? "Trigger sends a momentary ON impulse; the Bloc9 is expected to reset the output itself."
                  : "ON sends a full-on command without brightness or PWM."}</span>`
            }
            <div class="button-group">
             <button
                 type="button"
                 data-action="send-control"
                data-card-key="${escapeHtml(cardKey)}"
                data-output="${outputName}"
                data-on="1"
                ${actionAttrs(`control:${cardKey}:${outputName}:on`, !state.runtime.running || state.runtime.read_only)}
              >${isPulse ? "Trigger" : "On"}</button>
              ${isPulse
                ? ""
                : `<button
                type="button"
                data-action="send-control"
                data-card-key="${escapeHtml(cardKey)}"
                data-output="${outputName}"
                data-on="0"
                ${actionAttrs(`control:${cardKey}:${outputName}:off`, !state.runtime.running || state.runtime.read_only)}
              >Off</button>`}
            </div>
          </div>
        </div>
      </div>
    </section>
  `;
}

function renderBloc9Cards() {
  const configuredMap = getConfiguredBloc9Map();
  const discoveredMap = getDiscoveredBloc9Map();
  const keys = [...new Set([...Object.keys(configuredMap), ...Object.keys(discoveredMap)])].sort(
    (left, right) => left.localeCompare(right, undefined, { numeric: true }),
  );
  const container = document.getElementById("bloc9-list");
  const summary = document.getElementById("bloc9-summary");
  const isRunning = state.discovery.status === "running";

  document.getElementById("discovery-toggle-button").textContent = isRunning
    ? "Stop discovery"
    : "Start discovery";
  document.getElementById("discovery-toggle-button").className = isRunning
    ? ""
    : "primary";

  summary.innerHTML = `
    <span class="summary-chip ${isRunning ? "positive" : "negative"}">Discovery ${escapeHtml(state.discovery.status || "idle")}</span>
    <span class="summary-chip">State updates ${(state.discovery.message_counts?.state_update || 0)}</span>
    <span class="summary-chip">Heartbeats ${(state.discovery.message_counts?.heartbeat || 0)}</span>
    <span class="summary-chip">Cards ${keys.length}</span>
  `;

  if (!keys.length) {
    container.className = "card-list empty-state";
    container.textContent = "No Bloc9 devices are visible yet. Leave discovery running and interact with the panel.";
    return;
  }

  container.className = "card-list";
  container.innerHTML = keys
    .map((cardKey) => {
      const configured = configuredMap[cardKey] || null;
      const candidate = discoveredMap[cardKey] || null;
      const draft = ensureBloc9Draft(cardKey, configured, candidate);
      const validation = validateBloc9Draft(draft, cardKey);
      const normalizedDraft = buildBloc9DraftForSave(draft);
      const dirty = configured ? !devicesEqual(normalizedDraft, configured) : true;
      const status = configured && candidate ? "synced" : candidate ? "discovered" : "configured";
      const actionKey = `save-bloc9:${cardKey}`;
      const buttonDisabled = !validation.valid || (configured ? !dirty : false);
      const buttonLabel = configured ? "Save" : "Add to configuration";
      const readonlyId = routeSlug(draft.bus_id, draft.segment_id || 0);
      const isExpanded = isBloc9CardExpanded(cardKey);
      const cardPanelId = `bloc9-card-${domSafeId(cardKey)}`;
      const cardTitle = String(draft.name || "").trim() || deviceLabel({ type: "bloc9", bus_id: draft.bus_id, segment_id: draft.segment_id || 0 });
      const cardSubtitle = `${deviceLabel({ type: "bloc9", bus_id: draft.bus_id, segment_id: draft.segment_id || 0 })} · ${candidateLastSeen(candidate)}`;
      const cardStateSummary = bloc9CardStateSummary(draft, candidate);

      return `
        <article class="setup-card tone-${status}">
          <button
            type="button"
            class="collapse-toggle bloc9-card-toggle"
            data-action="toggle-bloc9-card"
            data-card-key="${escapeHtml(cardKey)}"
            aria-expanded="${isExpanded ? "true" : "false"}"
            aria-controls="${cardPanelId}"
          >
            <div class="collapse-toggle-main">
              <div class="card-banner">
                <span class="status-badge">${escapeHtml(toneLabel(status))}</span>
                <span class="status-meta">ID ${escapeHtml(readonlyId)}</span>
              </div>

              <div class="card-header">
                <div>
                  <h3>${escapeHtml(cardTitle)}</h3>
                  <p>${escapeHtml(cardSubtitle)}</p>
                  <p class="card-state-summary">${escapeHtml(cardStateSummary)}</p>
                </div>
              </div>
            </div>
            <span class="collapse-indicator" aria-hidden="true">${isExpanded ? "−" : "+"}</span>
          </button>

          <div id="${cardPanelId}" class="collapse-body${isExpanded ? "" : " hidden"}">
            <div class="card-grid">
              <label class="${bloc9FieldClass(validation, "device.name", draft.name !== (configured?.name || ""))}">
                <span>Name</span>
                <input type="text" value="${escapeHtml(draft.name || "")}" data-card-kind="bloc9" data-card-key="${escapeHtml(cardKey)}" data-field="name">
              </label>

              <label class="field-shell readonly">
                <span>Bloc9 ID</span>
                <input type="text" value="${escapeHtml(readonlyId)}" readonly>
              </label>

              <label class="${bloc9FieldClass(validation, "device.description", draft.description !== (configured?.description || ""))} full-width">
                <span>Description</span>
                <textarea rows="2" data-card-kind="bloc9" data-card-key="${escapeHtml(cardKey)}" data-field="description">${escapeHtml(draft.description || "")}</textarea>
              </label>
            </div>

            <div class="output-list">
              ${outputs
                .map((outputName) =>
                  renderBloc9OutputRow(cardKey, draft, configured, candidate, outputName, validation),
                )
                .join("")}
            </div>

            <div class="card-footer">
              <div class="card-hint">
                ${validation.valid ? (configured ? (dirty ? "Unsaved changes ready to apply." : "No unsaved changes.") : "Ready to add once you want it in the saved configuration.") : "Complete the highlighted fields before saving."}
              </div>
              <button
                type="button"
                data-action="save-bloc9"
                data-card-key="${escapeHtml(cardKey)}"
                ${actionAttrs(actionKey, buttonDisabled, "primary")}
              >${escapeHtml(buttonLabel)}</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function nextBloc7BusId() {
  const ids = state.config.devices
    .filter((device) => device.type === "bloc7")
    .map((device) => Number(device.bus_id))
    .filter((value) => Number.isInteger(value));
  Object.values(state.bloc7Drafts).forEach((draft) => {
    const busId = Number(draft.bus_id);
    if (Number.isInteger(busId)) ids.push(busId);
  });
  return ids.length ? Math.max(...ids) + 1 : 1;
}

function getBloc7ConfiguredCards() {
  return state.config.devices
    .filter((device) => device.type === "bloc7")
    .map((device) => {
      const key = `bloc7:${routeSlug(device.bus_id, device.segment_id || 0)}`;
      return { key, configured: device, draft: ensureBloc7Draft(key, device) };
    });
}

function ensureBloc7Draft(cardKey, configuredDevice) {
  if (state.bloc7Drafts[cardKey]) return state.bloc7Drafts[cardKey];
  state.bloc7Drafts[cardKey] = configuredDevice ? clone(configuredDevice) : blankBloc7Device();
  return state.bloc7Drafts[cardKey];
}

function validateBloc7Draft(draft, cardKey) {
  const errors = {};
  const excludedRoute = cardKey.startsWith("bloc7:") ? cardKey.split(":")[1] : null;
  const usedEntityIds = collectEntityIds(
    (device) => device.type === "bloc7" && routeSlug(device.bus_id, device.segment_id || 0) === excludedRoute,
  );
  const usedRoutes = new Set(
    state.config.devices
      .filter((device) => device.type === "bloc7" && routeSlug(device.bus_id, device.segment_id || 0) !== excludedRoute)
      .map((device) => routeSlug(device.bus_id, device.segment_id || 0)),
  );

  if (!Number.isInteger(Number(draft.bus_id)) || Number(draft.bus_id) < 0 || Number(draft.bus_id) > 255) {
    errors["device.bus_id"] = "Bus ID must be between 0 and 255.";
  } else if (!Number.isInteger(Number(draft.segment_id || 0)) || Number(draft.segment_id || 0) < 0 || Number(draft.segment_id || 0) > 7) {
    errors["device.segment_id"] = "Segment ID must be between 0 and 7.";
  } else if (usedRoutes.has(routeSlug(draft.bus_id, draft.segment_id || 0))) {
    errors["device.bus_id"] = "This Bloc7 route is already configured.";
  }

  const localEntityIds = new Set();
  (draft.sensors || []).forEach((sensor, index) => {
    const basePath = `sensors.${index}`;
    if (!String(sensor.name || "").trim()) {
      errors[`${basePath}.name`] = "Sensor name is required.";
    }
    const entityId = String(sensor.entity_id || "").trim();
    if (!entityId) {
      errors[`${basePath}.entity_id`] = "Entity ID is required.";
    } else if (entityId.startsWith("sensor.")) {
      errors[`${basePath}.entity_id`] = "Do not include the Home Assistant domain.";
    } else if (!entityIdPattern.test(entityId)) {
      errors[`${basePath}.entity_id`] = "Use lowercase letters, numbers, and underscores only.";
    } else if (usedEntityIds.has(entityId) || localEntityIds.has(entityId)) {
      errors[`${basePath}.entity_id`] = "This entity ID is already in use.";
    } else {
      localEntityIds.add(entityId);
    }

    if (!["level", "voltage", "frequency", "current", "state_of_charge", "raw"].includes(sensor.sensor_type)) {
      errors[`${basePath}.sensor_type`] = "Choose a supported sensor type.";
    }
    if (!String(sensor.matcher?.pattern ?? "").trim()) {
      errors[`${basePath}.matcher.pattern`] = "Matcher pattern is required.";
    }
    if (!String(sensor.matcher?.mask ?? "").trim()) {
      errors[`${basePath}.matcher.mask`] = "Matcher mask is required.";
    }
    if (!Number.isInteger(Number(sensor.value_config?.start_byte))) {
      errors[`${basePath}.value_config.start_byte`] = "Start byte must be an integer.";
    }
    if (!Number.isInteger(Number(sensor.value_config?.bit_length)) || Number(sensor.value_config?.bit_length) <= 0) {
      errors[`${basePath}.value_config.bit_length`] = "Bit length must be a positive integer.";
    }
    if (!["little", "big"].includes(sensor.value_config?.endian)) {
      errors[`${basePath}.value_config.endian`] = "Endian must be little or big.";
    }
    if (Number.isNaN(Number(sensor.value_config?.scale))) {
      errors[`${basePath}.value_config.scale`] = "Scale must be numeric.";
    }
  });

  return { valid: Object.keys(errors).length === 0, errors };
}

function buildBloc7DraftForSave(draft) {
  return {
    type: "bloc7",
    bus_id: Number(draft.bus_id),
    segment_id: Number(draft.segment_id || 0),
    name: String(draft.name || "").trim(),
    description: String(draft.description || "").trim(),
    sensors: (draft.sensors || []).map((sensor) => ({
      name: String(sensor.name || "").trim(),
      entity_id: String(sensor.entity_id || "").trim(),
      sensor_type: sensor.sensor_type,
      matcher: {
        pattern: String(sensor.matcher?.pattern || "").trim(),
        mask: String(sensor.matcher?.mask || "").trim(),
      },
      value_config: {
        start_byte: Number(sensor.value_config?.start_byte),
        bit_length: Number(sensor.value_config?.bit_length),
        endian: sensor.value_config?.endian || "little",
        scale: Number(sensor.value_config?.scale),
      },
    })),
  };
}

function getBloc7LiveReading(sensor) {
  const matcherPattern = parseArbitrationId(sensor?.matcher?.pattern);
  const startByte = Number(sensor?.value_config?.start_byte);
  if (matcherPattern === null || !Number.isInteger(startByte)) return null;

  for (const candidate of state.bloc7Discovery.candidates || []) {
    for (const suggestion of candidate.suggested_sensors || []) {
      if (
        Number(suggestion?.matcher?.pattern) === matcherPattern &&
        Number(suggestion?.value_config?.start_byte) === startByte
      ) {
        return {
          value: suggestion.current_value,
          history: suggestion.history || [],
          family: candidate.family,
          arbitrationId: candidate.arbitration_id,
        };
      }
    }
  }

  return null;
}

function formatBloc7SensorValue(sensorType, value) {
  const numericValue = Number(value);
  const rounded = Number.isInteger(numericValue) ? String(numericValue) : numericValue.toFixed(2);
  const units = {
    voltage: " V",
    frequency: " Hz",
    current: " A",
    level: "%",
    state_of_charge: "%",
    raw: "",
  };
  const unit = units[sensorType] ?? "";
  return `${rounded}${unit}`;
}

function formatBloc7LiveValue(sensor, liveReading) {
  if (!liveReading || liveReading.value === null || liveReading.value === undefined) {
    return "No live value";
  }

  return formatBloc7SensorValue(sensor?.sensor_type || "level", liveReading.value);
}

function matchesBloc7Suggestion(sensor, suggestion) {
  return (
    parseArbitrationId(sensor?.matcher?.pattern) === Number(suggestion?.matcher?.pattern) &&
    Number(sensor?.value_config?.start_byte) === Number(suggestion?.value_config?.start_byte)
  );
}

function getBloc7ConfiguredMessageDevice(candidate) {
  return (
    state.config.devices.find((device) => {
      if (device.type !== (candidate.device_type || "bloc7")) return false;
      const sensors = device.sensors || [];
      if (!sensors.length) return false;
      return sensors.every(
        (sensor) => parseArbitrationId(sensor?.matcher?.pattern) === candidate.arbitration_id_int,
      );
    }) || null
  );
}

function nextBloc7MessageBusId(excludedCandidateKey = null) {
  const ids = state.config.devices
    .filter((device) => device.type === "bloc7")
    .map((device) => Number(device.bus_id))
    .filter((value) => Number.isInteger(value));

  Object.values(state.bloc7Drafts).forEach((draft) => {
    const busId = Number(draft.bus_id);
    if (Number.isInteger(busId)) ids.push(busId);
  });

  Object.entries(state.bloc7CandidateDrafts || {}).forEach(([candidateKey, draft]) => {
    if (candidateKey === excludedCandidateKey) return;
    const busId = Number(draft?.bus_id);
    if (Number.isInteger(busId)) ids.push(busId);
  });

  return ids.length ? Math.max(...ids) + 1 : 1;
}

function ensureBloc7CandidateDraft(candidate) {
  const key = String(candidate.candidate_key);
  if (state.bloc7CandidateDrafts[key]) return state.bloc7CandidateDrafts[key];

  const configuredDevice = getBloc7ConfiguredMessageDevice(candidate);
  const channels = Object.fromEntries(
    (candidate.suggested_sensors || []).map((suggestion) => {
      const configuredSensor = (configuredDevice?.sensors || []).find((sensor) =>
        matchesBloc7Suggestion(sensor, suggestion),
      );
      return [
        suggestion.suggestion_key,
        {
          name: configuredSensor?.name || "",
          entity_id: configuredSensor?.entity_id || "",
          sensor_type: configuredSensor?.sensor_type || suggestion.sensor_type,
        },
      ];
    }),
  );

  state.bloc7CandidateDrafts[key] = {
    bus_id: configuredDevice?.bus_id ?? candidate.bus_id ?? nextBloc7MessageBusId(key),
    segment_id: configuredDevice?.segment_id ?? candidate.segment_id ?? 0,
    channels,
  };
  return state.bloc7CandidateDrafts[key];
}

function updateBloc7CandidateDraftField(candidateKey, suggestionKey, field, value) {
  const draft = state.bloc7CandidateDrafts[candidateKey];
  if (!draft) return;
  draft.channels[suggestionKey] = draft.channels[suggestionKey] || {
    name: "",
    entity_id: "",
  };
  draft.channels[suggestionKey][field] = value;
}

function validateBloc7CandidateDraft(candidate, candidateDraft) {
  const errors = {};
  const configuredDevice = getBloc7ConfiguredMessageDevice(candidate);
  const usedEntityIds = collectEntityIds(
    (device) =>
      device.type === (candidate.device_type || "bloc7")
      && routeSlug(device.bus_id, device.segment_id || 0)
        === routeSlug(configuredDevice?.bus_id, configuredDevice?.segment_id || 0),
  );
  let configuredCount = 0;

  for (const suggestion of candidate.suggested_sensors || []) {
    const channel = candidateDraft.channels[suggestion.suggestion_key] || {
      name: "",
      entity_id: "",
      sensor_type: suggestion.sensor_type,
    };
    const basePath = `channels.${suggestion.suggestion_key}`;
    const name = String(channel.name || "").trim();
    const entityId = String(channel.entity_id || "").trim();
    const sensorType = String(channel.sensor_type || suggestion.sensor_type || "").trim();

    if (!name && !entityId) {
      continue;
    }

    if (!name) {
      errors[`${basePath}.name`] = "Name is required when this channel is enabled.";
    }

    if (!entityId) {
      errors[`${basePath}.entity_id`] = "Entity ID is required when this channel is enabled.";
      continue;
    }

    if (entityId.startsWith("sensor.")) {
      errors[`${basePath}.entity_id`] = "Do not include the Home Assistant domain.";
    } else if (!entityIdPattern.test(entityId)) {
      errors[`${basePath}.entity_id`] =
        "Use lowercase letters, numbers, and underscores only.";
    } else if (usedEntityIds.has(entityId)) {
      errors[`${basePath}.entity_id`] = "This entity ID is already in use.";
    } else {
      usedEntityIds.add(entityId);
    }

    if (name && entityId) {
      if (!Object.hasOwn(bloc7SensorTypeLabels, sensorType)) {
        errors[`${basePath}.sensor_type`] = "Choose a supported sensor type.";
      }
      configuredCount += 1;
    }
  }

  return {
    valid: Object.keys(errors).length === 0 && configuredCount > 0,
    errors,
    configuredCount,
    configuredDevice,
  };
}

function buildBloc7DeviceFromCandidate(candidate, candidateDraft, configuredDevice = null) {
  const sensors = (candidate.suggested_sensors || [])
    .map((suggestion) => {
      const channel = candidateDraft.channels[suggestion.suggestion_key] || {
        name: "",
        entity_id: "",
        sensor_type: suggestion.sensor_type,
      };
      const name = String(channel.name || "").trim();
      const entityId = String(channel.entity_id || "").trim();
      if (!name || !entityId) return null;
      return {
        name,
        entity_id: entityId,
        sensor_type: channel.sensor_type || suggestion.sensor_type,
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
      };
    })
    .filter(Boolean);

  return {
    type: candidate.device_type || "bloc7",
    bus_id: Number(configuredDevice?.bus_id ?? candidateDraft.bus_id),
    segment_id: Number(configuredDevice?.segment_id ?? candidateDraft.segment_id ?? 0),
    name:
      String(configuredDevice?.name || "").trim()
      || `${candidate.device_type === "source_selector" ? "SourceSelector" : "Bloc7"} ${candidate.route_slug || candidate.arbitration_id}`,
    description:
      String(configuredDevice?.description || "").trim()
      || `Configured from ${candidate.arbitration_id} (${candidate.family})`,
    sensors,
  };
}

function renderSensorDraft(cardKey, sensor, index, validation, baselineSensor = null) {
  const basePath = `sensors.${index}`;
  const liveReading = getBloc7LiveReading(sensor);
  const liveValue = formatBloc7LiveValue(sensor, liveReading);
  const matcherPattern = parseArbitrationId(sensor?.matcher?.pattern);
  const hasFixedMapping =
    matcherPattern !== null && Number.isInteger(Number(sensor?.value_config?.start_byte));
  const fieldClass = (field, dirty) => {
    const classes = ["field-shell"];
    if (validation.errors[`${basePath}.${field}`]) classes.push("invalid");
    if (dirty) classes.push("dirty");
    return classes.join(" ");
  };

  return `
    <section class="sensor-card">
      <div class="sensor-card-header">
        <div>
          <h4>${escapeHtml(String(sensor.name || "").trim() || `Sensor ${index + 1}`)}</h4>
          <p class="sensor-live-summary">
            Live value ${escapeHtml(liveValue)}
            ${liveReading?.arbitrationId ? ` · ${escapeHtml(liveReading.arbitrationId)}` : ""}
          </p>
        </div>
        <div class="sensor-card-actions">
          <span class="summary-chip">${escapeHtml(sensor.sensor_type || "sensor")}</span>
          <button type="button" data-action="remove-bloc7-sensor" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}">Remove</button>
        </div>
      </div>
      <div class="card-grid">
        <label class="${fieldClass("name", sensor.name !== (baselineSensor?.name || ""))}">
          <span>Name</span>
          <input type="text" value="${escapeHtml(sensor.name || "")}" data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="name">
          ${validation.errors[`${basePath}.name`] ? `<small>${escapeHtml(validation.errors[`${basePath}.name`])}</small>` : ""}
        </label>
        <label class="${fieldClass("entity_id", sensor.entity_id !== (baselineSensor?.entity_id || ""))}">
          <span>Entity ID</span>
          <input type="text" value="${escapeHtml(sensor.entity_id || "")}" data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="entity_id">
          ${validation.errors[`${basePath}.entity_id`] ? `<small>${escapeHtml(validation.errors[`${basePath}.entity_id`])}</small>` : ""}
        </label>
        ${
          hasFixedMapping
            ? `<label class="${fieldClass("sensor_type", sensor.sensor_type !== (baselineSensor?.sensor_type || "level"))}">
                <span>Type</span>
                <select data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="sensor_type">
                  ${renderBloc7SensorTypeOptions(sensor.sensor_type || "level")}
                </select>
                ${validation.errors[`${basePath}.sensor_type`] ? `<small>${escapeHtml(validation.errors[`${basePath}.sensor_type`])}</small>` : ""}
              </label>
              <div class="sensor-metadata full-width">
                <span class="summary-chip">${escapeHtml(sensor.sensor_type || "level")}</span>
                <span class="summary-chip">${escapeHtml(formatHex(matcherPattern))}</span>
                <span class="summary-chip">byte ${escapeHtml(sensor.value_config?.start_byte ?? 0)}</span>
                <span class="summary-chip">${escapeHtml(`${sensor.value_config?.bit_length ?? 8}-bit ${sensor.value_config?.endian || "little"}`)}</span>
                <span class="summary-chip">scale ${escapeHtml(sensor.value_config?.scale ?? 1)}</span>
              </div>`
            : `
              <label class="${fieldClass("sensor_type", sensor.sensor_type !== (baselineSensor?.sensor_type || "level"))}">
                <span>Type</span>
                <select data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="sensor_type">
                  ${renderBloc7SensorTypeOptions(sensor.sensor_type || "level")}
                </select>
                ${validation.errors[`${basePath}.sensor_type`] ? `<small>${escapeHtml(validation.errors[`${basePath}.sensor_type`])}</small>` : ""}
              </label>
              <label class="${fieldClass("matcher.pattern", String(sensor.matcher?.pattern || "") !== String(baselineSensor?.matcher?.pattern || ""))}">
                <span>Matcher pattern</span>
                <input type="text" value="${escapeHtml(formatHex(sensor.matcher?.pattern) || "")}" data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="matcher.pattern">
                ${validation.errors[`${basePath}.matcher.pattern`] ? `<small>${escapeHtml(validation.errors[`${basePath}.matcher.pattern`])}</small>` : ""}
              </label>
              <label class="${fieldClass("matcher.mask", String(sensor.matcher?.mask || "") !== String(baselineSensor?.matcher?.mask || ""))}">
                <span>Matcher mask</span>
                <input type="text" value="${escapeHtml(formatHex(sensor.matcher?.mask) || "")}" data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="matcher.mask">
                ${validation.errors[`${basePath}.matcher.mask`] ? `<small>${escapeHtml(validation.errors[`${basePath}.matcher.mask`])}</small>` : ""}
              </label>
              <label class="${fieldClass("value_config.start_byte", Number(sensor.value_config?.start_byte) !== Number(baselineSensor?.value_config?.start_byte ?? 0))}">
                <span>Start byte</span>
                <input type="number" min="0" value="${escapeHtml(sensor.value_config?.start_byte ?? 0)}" data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="value_config.start_byte">
                ${validation.errors[`${basePath}.value_config.start_byte`] ? `<small>${escapeHtml(validation.errors[`${basePath}.value_config.start_byte`])}</small>` : ""}
              </label>
              <label class="${fieldClass("value_config.bit_length", Number(sensor.value_config?.bit_length) !== Number(baselineSensor?.value_config?.bit_length ?? 8))}">
                <span>Bit length</span>
                <input type="number" min="1" value="${escapeHtml(sensor.value_config?.bit_length ?? 8)}" data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="value_config.bit_length">
                ${validation.errors[`${basePath}.value_config.bit_length`] ? `<small>${escapeHtml(validation.errors[`${basePath}.value_config.bit_length`])}</small>` : ""}
              </label>
              <label class="${fieldClass("value_config.endian", sensor.value_config?.endian !== (baselineSensor?.value_config?.endian || "little"))}">
                <span>Endian</span>
                <select data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="value_config.endian">
                  <option value="little" ${sensor.value_config?.endian === "little" ? "selected" : ""}>Little</option>
                  <option value="big" ${sensor.value_config?.endian === "big" ? "selected" : ""}>Big</option>
                </select>
                ${validation.errors[`${basePath}.value_config.endian`] ? `<small>${escapeHtml(validation.errors[`${basePath}.value_config.endian`])}</small>` : ""}
              </label>
              <label class="${fieldClass("value_config.scale", Number(sensor.value_config?.scale) !== Number(baselineSensor?.value_config?.scale ?? 1))}">
                <span>Scale</span>
                <input type="number" step="any" value="${escapeHtml(sensor.value_config?.scale ?? 1)}" data-card-kind="bloc7" data-card-key="${escapeHtml(cardKey)}" data-sensor-index="${index}" data-field="value_config.scale">
                ${validation.errors[`${basePath}.value_config.scale`] ? `<small>${escapeHtml(validation.errors[`${basePath}.value_config.scale`])}</small>` : ""}
              </label>
            `
        }
      </div>
    </section>
  `;
}

function renderBloc7Cards() {
  const configuredCards = getBloc7ConfiguredCards();
  const newDraftEntries = Object.entries(state.bloc7Drafts)
    .filter(([key]) => key.startsWith("new-bloc7:"))
    .map(([key, draft]) => ({ key, configured: null, draft }));
  const allDraftCards = [...configuredCards, ...newDraftEntries].sort((left, right) =>
    Number(left.draft.bus_id || 0) - Number(right.draft.bus_id || 0),
  );
  const container = document.getElementById("bloc7-list");
  const summary = document.getElementById("bloc7-summary");

  summary.innerHTML = `
    <span class="summary-chip">Configured ${configuredCards.length}</span>
    <span class="summary-chip">Drafts ${newDraftEntries.length}</span>
    <span class="summary-chip">Live candidates ${(state.bloc7Discovery.candidates || []).length}</span>
    <span class="summary-chip ${state.bloc7Discovery.status === "running" ? "positive" : "neutral"}">Inspector ${escapeHtml(state.bloc7Discovery.status || "idle")}</span>
  `;

  const draftCardsHtml = allDraftCards
    .map(({ key, configured, draft }) => {
      const validation = validateBloc7Draft(draft, key);
      const normalizedDraft = buildBloc7DraftForSave(draft);
      const dirty = configured ? !devicesEqual(normalizedDraft, configured) : true;
      const actionKey = `save-bloc7:${key}`;
      const buttonDisabled = !validation.valid || (configured ? !dirty : false);
      const bannerTone = configured ? "configured" : "draft";
      const liveSensorCount = (draft.sensors || []).filter((sensor) => getBloc7LiveReading(sensor)).length;
      return `
        <article class="setup-card tone-${bannerTone}">
          <div class="card-banner">
            <span class="status-badge">${escapeHtml(configured ? "configured" : "draft")}</span>
            <span class="status-meta">Route ${escapeHtml(routeSlug(draft.bus_id || "—", draft.segment_id || 0))}</span>
          </div>
          <div class="card-header">
            <div>
              <h3>${escapeHtml(String(draft.name || "").trim() || deviceLabel({ type: "bloc7", bus_id: draft.bus_id || "?", segment_id: 0 }))}</h3>
              <p>${escapeHtml(configured ? "Saved device ready for edits." : "Draft device not saved yet.")}</p>
              <p class="card-state-summary">${escapeHtml(liveSensorCount ? `${liveSensorCount} sensor${liveSensorCount === 1 ? "" : "s"} currently reporting live values.` : "No matched live readings yet.")}</p>
            </div>
          </div>
          <div class="card-grid">
            <label class="field-shell ${validation.errors["device.bus_id"] ? "invalid" : ""}">
              <span>Bus ID</span>
              <input type="number" min="0" max="255" value="${escapeHtml(draft.bus_id ?? "")}" data-card-kind="bloc7" data-card-key="${escapeHtml(key)}" data-field="bus_id">
              ${validation.errors["device.bus_id"] ? `<small>${escapeHtml(validation.errors["device.bus_id"])}</small>` : ""}
            </label>
            <label class="field-shell ${validation.errors["device.segment_id"] ? "invalid" : ""}">
              <span>Segment ID</span>
              <input type="number" min="0" max="7" value="${escapeHtml(draft.segment_id ?? 0)}" data-card-kind="bloc7" data-card-key="${escapeHtml(key)}" data-field="segment_id">
              ${validation.errors["device.segment_id"] ? `<small>${escapeHtml(validation.errors["device.segment_id"])}</small>` : ""}
            </label>
            <label class="field-shell ${draft.name !== (configured?.name || "") ? "dirty" : ""}">
              <span>Name</span>
              <input type="text" value="${escapeHtml(draft.name || "")}" data-card-kind="bloc7" data-card-key="${escapeHtml(key)}" data-field="name">
            </label>
            <label class="field-shell full-width ${draft.description !== (configured?.description || "") ? "dirty" : ""}">
              <span>Description</span>
              <textarea rows="2" data-card-kind="bloc7" data-card-key="${escapeHtml(key)}" data-field="description">${escapeHtml(draft.description || "")}</textarea>
            </label>
          </div>
          <div class="section-subheader">
            <h4>Sensors</h4>
            <button type="button" data-action="add-bloc7-sensor" data-card-key="${escapeHtml(key)}">Add sensor</button>
          </div>
          <div class="sensor-list">
            ${(draft.sensors || []).length
              ? draft.sensors
                  .map((sensor, index) =>
                    renderSensorDraft(key, sensor, index, validation, configured?.sensors?.[index] || null),
                  )
                  .join("")
              : '<div class="empty-inline">No sensors yet.</div>'}
          </div>
          <div class="card-footer">
            <div class="card-hint">
              ${validation.valid ? (configured ? (dirty ? "Unsaved changes ready to apply." : "No unsaved changes.") : "Ready to add to the saved configuration.") : "Complete the highlighted sensor fields before saving."}
            </div>
            <button type="button" data-action="save-bloc7" data-card-key="${escapeHtml(key)}" ${actionAttrs(actionKey, buttonDisabled, "primary")}>${escapeHtml(configured ? "Save" : "Add to configuration")}</button>
          </div>
        </article>
      `;
    })
    .join("");

  const candidateCardsHtml = (state.bloc7Discovery.candidates || [])
    .map((candidate) => {
      const configuredDevice = getBloc7ConfiguredMessageDevice(candidate);
      const candidateDraft = ensureBloc7CandidateDraft(candidate);
      const validation = validateBloc7CandidateDraft(candidate, candidateDraft);
      const suggestions = (candidate.suggested_sensors || [])
        .map(
          (suggestion) => `
            <div class="candidate-suggestion candidate-channel-card">
              <div class="candidate-channel-header">
                <div>
                  <strong>${escapeHtml(suggestion.label)}</strong>
                  <div class="muted">${escapeHtml(suggestion.notes || "")}</div>
                </div>
                <span class="live-state ${suggestion.current_value === null || suggestion.current_value === undefined ? "unknown" : "on"}">
                  <span class="state-beacon"></span>
                  ${escapeHtml(
                    suggestion.current_value === null || suggestion.current_value === undefined
                      ? "No live value"
                      : formatBloc7SensorValue(suggestion.sensor_type, suggestion.current_value),
                  )}
                </span>
              </div>
              <div class="candidate-tags">
                <span class="summary-chip">${escapeHtml(suggestion.sensor_type)}</span>
                <span class="summary-chip">byte ${escapeHtml(suggestion.value_config?.start_byte)}</span>
                <span class="summary-chip">${escapeHtml(formatHex(suggestion.matcher?.pattern))}</span>
              </div>
              <div class="card-grid compact-grid">
                <label class="field-shell ${validation.errors[`channels.${suggestion.suggestion_key}.name`] ? "invalid" : ""}">
                  <span>Name</span>
                  <input
                    type="text"
                    value="${escapeHtml(candidateDraft.channels[suggestion.suggestion_key]?.name || "")}"
                    placeholder="e.g. Fresh water"
                    data-card-kind="bloc7-candidate"
                    data-candidate-key="${escapeHtml(candidate.candidate_key)}"
                    data-suggestion-key="${escapeHtml(suggestion.suggestion_key)}"
                    data-field="name"
                  >
                  ${validation.errors[`channels.${suggestion.suggestion_key}.name`] ? `<small>${escapeHtml(validation.errors[`channels.${suggestion.suggestion_key}.name`])}</small>` : ""}
                </label>
                <label class="field-shell ${validation.errors[`channels.${suggestion.suggestion_key}.entity_id`] ? "invalid" : ""}">
                  <span>Entity ID</span>
                  <input
                    type="text"
                    value="${escapeHtml(candidateDraft.channels[suggestion.suggestion_key]?.entity_id || "")}"
                    placeholder="fresh_water"
                    data-card-kind="bloc7-candidate"
                    data-candidate-key="${escapeHtml(candidate.candidate_key)}"
                    data-suggestion-key="${escapeHtml(suggestion.suggestion_key)}"
                    data-field="entity_id"
                  >
                  ${validation.errors[`channels.${suggestion.suggestion_key}.entity_id`] ? `<small>${escapeHtml(validation.errors[`channels.${suggestion.suggestion_key}.entity_id`])}</small>` : ""}
                </label>
                ${
                  candidate.device_type === "bloc7"
                    ? `<label class="field-shell ${validation.errors[`channels.${suggestion.suggestion_key}.sensor_type`] ? "invalid" : ""}">
                  <span>Type</span>
                  <select
                    data-card-kind="bloc7-candidate"
                    data-candidate-key="${escapeHtml(candidate.candidate_key)}"
                    data-suggestion-key="${escapeHtml(suggestion.suggestion_key)}"
                    data-field="sensor_type"
                  >
                    ${renderBloc7SensorTypeOptions(
                      candidateDraft.channels[suggestion.suggestion_key]?.sensor_type || suggestion.sensor_type,
                    )}
                  </select>
                  ${validation.errors[`channels.${suggestion.suggestion_key}.sensor_type`] ? `<small>${escapeHtml(validation.errors[`channels.${suggestion.suggestion_key}.sensor_type`])}</small>` : ""}
                </label>`
                    : ""
                }
              </div>
            </div>
          `,
        )
        .join("");
      return `
        <article class="setup-card tone-${configuredDevice ? "configured" : "discovered"}">
          <div class="card-banner">
            <span class="status-badge">${escapeHtml(configuredDevice ? "configured" : "discovered")}</span>
             <span class="status-meta">${escapeHtml(candidate.route_slug || candidate.arbitration_id)} · ${escapeHtml(candidate.arbitration_id)}</span>
          </div>
          <div class="card-header">
            <div>
              <h3>${escapeHtml(configuredDevice?.name || candidate.title)}</h3>
              <p>${escapeHtml(candidate.summary)}</p>
              ${candidate.safety_notice ? `<p class="card-state-summary warning">${escapeHtml(candidate.safety_notice)}</p>` : ""}
              <p class="card-state-summary">Configure each reported channel by name, entity ID, and type. The matcher and byte mapping stay fixed to this message.</p>
            </div>
          </div>
          <div class="summary-bar compact">
            <span class="summary-chip">${escapeHtml(candidate.device_type || "bloc7")}</span>
            <span class="summary-chip">${escapeHtml(candidate.family)}</span>
            <span class="summary-chip">${escapeHtml(candidate.confidence.level)} ${escapeHtml(candidate.confidence.score)}</span>
            <span class="summary-chip">${escapeHtml(candidate.freq_hz)} Hz</span>
          </div>
          <div class="candidate-list">${suggestions}</div>
          <div class="card-footer">
            <div class="card-hint">
              ${validation.configuredCount
                ? `${validation.configuredCount} channel${validation.configuredCount === 1 ? "" : "s"} ready to save for this message.`
                : "Fill in at least one channel to save this message."}
            </div>
            <button
              type="button"
              data-action="save-bloc7-candidate"
              data-candidate-key="${escapeHtml(candidate.candidate_key)}"
              ${actionAttrs(`save-bloc7-candidate:${candidate.candidate_key}`, !validation.valid, "primary")}
            >${escapeHtml(configuredDevice ? "Save channels" : "Add message to configuration")}</button>
          </div>
        </article>
      `;
    })
    .join("");

  const html = [draftCardsHtml, candidateCardsHtml].filter(Boolean).join("");
  if (!html) {
    container.className = "card-list empty-state";
    container.textContent = "No Bloc7 devices or candidates are visible yet.";
    return;
  }
  container.className = "card-list";
  container.innerHTML = html;
}

function renderInspectPanel() {
  if (state.activeTab !== "inspect" || state.inspectLoaded) return;
  const frame = document.getElementById("inspect-frame");
  frame.src = resolveAppUrl("inspect?embedded=1");
  state.inspectLoaded = true;
}

function slugifyEntityId(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function getConfiguredBloc9OutputByRef(outputRef) {
  const [route, outputName] = String(outputRef || "").split(":");
  if (!route || !outputName) return null;
  return (
    state.config.devices.find(
      (device) => device.type === "bloc9" && routeSlug(device.bus_id, device.segment_id || 0) === route,
    )?.outputs?.[outputName] || null
  );
}

function getConfiguredBloc9DeviceByRoute(route) {
  return (
    state.config.devices.find(
      (device) => device.type === "bloc9" && routeSlug(device.bus_id, device.segment_id || 0) === route,
    ) || null
  );
}

function getSetupHelperSuggestions() {
  const groups = new Map();
  for (const device of state.config.devices) {
    if (device.type !== "bloc9") continue;
    for (const outputName of outputs) {
      const output = device.outputs?.[outputName];
      if (!output?.enabled || !output?.entity_id || !output?.role) continue;
      const key = `${output.role}:${output.entity_id}`;
      if (!groups.has(key)) {
        groups.set(key, {
          role: output.role,
          entity_id: output.entity_id,
          name: output.name || formatDiscoveryName(output.entity_id),
          count: 0,
        });
      }
      groups.get(key).count += 1;
    }
  }
  return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function formatDiscoveryName(entityId) {
  return String(entityId || "")
    .split("_")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function syncSetupHelperDraft() {
  const helper = state.setupHelper;
  const draft = state.setupHelperDraft;
  if (!draft.target_name && helper.target_name) draft.target_name = helper.target_name;
  if (!draft.output_name && helper.target_name) draft.output_name = helper.target_name;
  if (!draft.entity_id) {
    draft.entity_id = helper.entity_id || slugifyEntityId(helper.target_name || draft.target_name);
  }
  if (helper.completed_run?.suggested_role) {
    draft.role = helper.completed_run.suggested_role;
  } else if (helper.target_role) {
    draft.role = helper.target_role;
  }
  for (const output of helper.completed_run?.changed_outputs || []) {
    if (!(output.output_ref in draft.selected_outputs)) {
      draft.selected_outputs[output.output_ref] = true;
    }
  }
}

function selectedSetupHelperOutputs() {
  return (state.setupHelper.completed_run?.changed_outputs || []).filter(
    (output) => state.setupHelperDraft.selected_outputs[output.output_ref],
  );
}

function helperConflictSummary(output) {
  const configured = getConfiguredBloc9OutputByRef(output.output_ref);
  if (!configured?.enabled) return "New mapping";
  const issues = [];
  if (configured.role !== state.setupHelperDraft.role) issues.push(`currently ${configured.role}`);
  if (configured.entity_id !== state.setupHelperDraft.entity_id) {
    issues.push(`entity ${configured.entity_id}`);
  }
  if (configured.name !== state.setupHelperDraft.output_name) issues.push(`name ${configured.name}`);
  return issues.length ? `Will replace ${issues.join(" · ")}` : "Already matches";
}

function helperOutputTitle(output) {
  const configuredDevice = getConfiguredBloc9DeviceByRoute(output.route_slug);
  const configuredName = String(configuredDevice?.name || "").trim();
  return configuredName
    ? `Bloc9 #${output.route_slug} (${configuredName}) ${output.output_name.toUpperCase()}`
    : `Bloc9 #${output.route_slug} ${output.output_name.toUpperCase()}`;
}

function helperApplyReady() {
  return Boolean(
    state.setupHelperDraft.output_name
      && state.setupHelperDraft.entity_id
      && selectedSetupHelperOutputs().length,
  );
}

function renderSetupHelperPanel() {
  syncSetupHelperDraft();
  const container = document.getElementById("helper-panel");
  const helper = state.setupHelper;
  const draft = state.setupHelperDraft;
  const suggestions = getSetupHelperSuggestions();
  const selectedOutputs = selectedSetupHelperOutputs();
  const unnamedRoutes = [...new Set(selectedOutputs.map((output) => output.route_slug))].filter(
    (route) => !getConfiguredBloc9DeviceByRoute(route)?.name,
  );
  const activeRun = helper.active_run;
  const completedRun = helper.completed_run;

  const countdownMarkup = activeRun?.countdown
    ? `<div class="helper-countdown">${escapeHtml(activeRun.countdown > 0 ? activeRun.countdown : "Now!")}</div>`
    : "";

  const findingsMarkup = completedRun
    ? `
      <section class="setup-card tone-${completedRun.confidence?.level || "discovered"}">
        <div class="card-header">
          <div>
            <h3>Findings</h3>
            <p>${escapeHtml(completedRun.changed_outputs?.length
              ? `Detected ${completedRun.changed_outputs.length} changed Bloc9 output${completedRun.changed_outputs.length === 1 ? "" : "s"}.`
              : "No conclusive Bloc9 output change was captured.")}</p>
          </div>
        </div>
        <div class="summary-bar compact">
          <span class="summary-chip">${escapeHtml(completedRun.confidence?.level || "low")} confidence</span>
          <span class="summary-chip">Suggested ${escapeHtml(completedRun.suggested_role || draft.role)}</span>
          <span class="summary-chip">Captured ${escapeHtml(completedRun.captured_message_count || 0)} frames</span>
        </div>
        <div class="helper-output-list">
          ${(completedRun.changed_outputs || []).map((output) => `
            <label class="helper-output-card">
              <input
                type="checkbox"
                ${draft.selected_outputs[output.output_ref] ? "checked" : ""}
                data-card-kind="setup-helper-output"
                data-output-ref="${escapeHtml(output.output_ref)}"
              >
              <div>
                <strong>${escapeHtml(helperOutputTitle(output))}</strong>
                <div class="muted">${escapeHtml(helperConflictSummary(output))}</div>
                <div class="muted">${escapeHtml(output.dimming_observed
                  ? "Dimming observed during hold."
                  : output.pulse_observed
                    ? "Momentary ON->OFF self-reset observed during tap."
                    : "No dimming observed in this capture.")}</div>
              </div>
              <span class="summary-chip">${escapeHtml(output.confidence?.level || "low")} ${escapeHtml(output.confidence?.score || 0)}</span>
            </label>
          `).join("") || '<div class="empty-inline">Run the guided capture again and follow the countdown.</div>'}
        </div>
        ${(completedRun.recommendations || []).length
          ? `<div class="helper-recommendations">
              ${(completedRun.recommendations || []).map((item) => `<div class="diagnostic-item warning">${escapeHtml(item)}</div>`).join("")}
            </div>`
          : ""}
        ${(completedRun.other_messages || []).length
          ? `<div class="helper-observations">
              <h4>Other CAN traffic seen during the interaction</h4>
              ${(completedRun.other_messages || []).map((entry) => `
                <div class="summary-chip">${escapeHtml(entry.arbitration_id)} · ${escapeHtml(entry.count)}× · ${escapeHtml(entry.sample_data)}</div>
              `).join("")}
            </div>`
          : ""}
      </section>
      <section class="setup-card tone-configured">
        <div class="card-header">
          <div>
            <h3>Apply to configuration</h3>
            <p>${escapeHtml(selectedOutputs.length > 1
              ? "Multiple outputs are selected, so this will be saved as one logical light, switch, or pulse by reusing the same entity ID."
              : "This will save the selected Bloc9 output directly into the configuration.")}</p>
          </div>
        </div>
        <div class="card-grid compact-grid">
          <label class="field-shell">
            <span>Role</span>
            <select data-card-kind="setup-helper" data-field="role">
              <option value="light" ${draft.role === "light" ? "selected" : ""}>Light</option>
              <option value="switch" ${draft.role === "switch" ? "selected" : ""}>Switch</option>
              <option value="pulse" ${draft.role === "pulse" ? "selected" : ""}>Pulse</option>
            </select>
          </label>
          <label class="field-shell">
            <span>Name</span>
            <input type="text" value="${escapeHtml(draft.output_name || "")}" data-card-kind="setup-helper" data-field="output_name">
          </label>
          <label class="field-shell">
            <span>Entity ID</span>
            <input type="text" value="${escapeHtml(draft.entity_id || "")}" data-card-kind="setup-helper" data-field="entity_id">
          </label>
          ${unnamedRoutes
            .map((routeSlugValue) => `
                <label class="field-shell">
                  <span>Bloc9 #${escapeHtml(routeSlugValue)} name (optional)</span>
                  <input
                    type="text"
                    value="${escapeHtml(draft.device_names[routeSlugValue] || "")}"
                    data-card-kind="setup-helper-device"
                    data-field="${escapeHtml(routeSlugValue)}"
                  >
                </label>
              `)
            .join("")}
        </div>
        <div class="card-footer">
          <div class="card-hint">
            ${helperApplyReady()
              ? `${selectedOutputs.length} output${selectedOutputs.length === 1 ? "" : "s"} ready to save.`
              : "Select at least one output and fill in the logical name and entity ID before saving."}
          </div>
          <button type="button" data-action="helper-apply" ${actionAttrs("helper-apply", !helperApplyReady(), "primary")}>Apply findings</button>
        </div>
      </section>
    `
    : "";

  container.className = "card-list";
  container.innerHTML = `
    <section class="setup-card tone-discovered">
      <div class="card-header">
        <div>
          <h3>What are you about to control?</h3>
          <p>Pick a known light, switch, or pulse, or enter a new name for the thing behind the button you are testing.</p>
        </div>
      </div>
      <div class="card-grid compact-grid">
        <label class="field-shell">
          <span>Name</span>
          <input
            type="text"
            list="helper-known-targets"
            value="${escapeHtml(draft.target_name || "")}"
            data-card-kind="setup-helper"
            data-field="target_name"
            placeholder="Underwater Light"
          >
          <datalist id="helper-known-targets">
            ${suggestions.map((suggestion) => `<option value="${escapeHtml(suggestion.name)}">${escapeHtml(`${suggestion.role} · ${suggestion.entity_id}`)}</option>`).join("")}
          </datalist>
        </label>
        <label class="field-shell">
          <span>Entity ID</span>
          <input
            type="text"
            value="${escapeHtml(draft.entity_id || "")}"
            data-card-kind="setup-helper"
            data-field="entity_id"
            placeholder="underwater_light"
          >
        </label>
        <label class="field-shell">
          <span>Preferred role</span>
          <select data-card-kind="setup-helper" data-field="role">
            <option value="light" ${draft.role === "light" ? "selected" : ""}>Light</option>
            <option value="switch" ${draft.role === "switch" ? "selected" : ""}>Switch</option>
            <option value="pulse" ${draft.role === "pulse" ? "selected" : ""}>Pulse</option>
          </select>
        </label>
      </div>
      <div class="card-footer">
        <div class="card-hint">${escapeHtml(helper.instruction || "Start a helper session and follow the guided countdown.")}</div>
        <div class="toolbar-actions">
          <button type="button" data-action="helper-start" ${actionAttrs("helper-start", !draft.target_name, "primary")}>Start helper</button>
          <button type="button" data-action="helper-stop" ${actionAttrs("helper-stop", helper.status === "idle")}>Reset</button>
        </div>
      </div>
    </section>

    <section class="setup-card tone-synced">
      <div class="card-header">
        <div>
          <h3>Guided actions</h3>
          <p>${escapeHtml(helper.target_name
            ? `Discovering mappings for ${helper.target_name}.`
            : "Start a helper session, then choose how you want to interact with the button.")}</p>
        </div>
      </div>
      <div class="summary-bar compact">
        <span class="summary-chip">${escapeHtml(helper.phase || "idle")}</span>
        ${activeRun ? `<span class="summary-chip">${escapeHtml(activeRun.action)}</span>` : ""}
        <span class="summary-chip">Known outputs ${escapeHtml(helper.known_output_count || 0)}</span>
      </div>
      <div class="helper-instruction-card">
        <strong>${escapeHtml(helper.instruction || "Ready when you are.")}</strong>
        ${countdownMarkup}
      </div>
      <div class="toolbar-actions helper-action-grid">
        <button type="button" data-action="helper-run-tap" ${actionAttrs("helper-run-tap", helper.status === "idle", "primary")}>Press and release</button>
        <button type="button" data-action="helper-run-hold" ${actionAttrs("helper-run-hold", helper.status === "idle")}>Press, hold, release</button>
      </div>
      <div class="helper-guidance muted">
        For <strong>Press and release</strong>, tap the button exactly when the countdown reaches <strong>Now</strong>. For <strong>Press, hold, release</strong>, hold through the second countdown so the helper can see whether dimming starts. A quick ON-&gt;OFF self-reset during the tap capture suggests a pulse output.
      </div>
    </section>

    ${findingsMarkup}
  `;
}

function renderActiveTab() {
  renderCurrentTab();
}

function parseNumberOrNull(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? value : parsed;
}

function updateBloc9DraftField(cardKey, field, value, outputName = null) {
  const draft = state.bloc9Drafts[cardKey];
  if (!draft) return;
  if (outputName) {
    draft.outputs[outputName] = draft.outputs[outputName] || blankOutput();
    draft.outputs[outputName][field] =
      field === "initial_brightness" ? parseNumberOrNull(value) : value;
    if (field === "role" && value !== "light") {
      draft.outputs[outputName].initial_brightness = null;
    }
    return;
  }
  draft[field] = value;
}

function updateBloc7DraftField(cardKey, field, value, sensorIndex = null) {
  const draft = state.bloc7Drafts[cardKey];
  if (!draft) return;
  if (sensorIndex === null) {
    draft[field] = ["bus_id", "segment_id"].includes(field)
      ? parseNumberOrNull(value)
      : value;
    return;
  }

  draft.sensors[sensorIndex] = draft.sensors[sensorIndex] || blankSensor();
  const sensor = draft.sensors[sensorIndex];
  if (field.startsWith("matcher.")) {
    sensor.matcher[field.split(".")[1]] = value;
    return;
  }
  if (field.startsWith("value_config.")) {
    const key = field.split(".")[1];
    sensor.value_config[key] =
      key === "start_byte" || key === "bit_length" || key === "scale"
        ? parseNumberOrNull(value)
        : value;
    return;
  }
  sensor[field] = value;
}

async function refreshStatus() {
  const response = await fetch(resolveAppUrl("api/status"));
  const payload = await response.json();
  state.runtime = payload.runtime || state.runtime;
  renderHeader();
}

async function loadConfig() {
  const response = await fetch(resolveAppUrl("api/config"));
  const payload = await response.json();
  state.config = payload.config || { schema_version: 1, devices: [] };
  state.baseRevision = payload.revision;
  state.diagnostics = payload.diagnostics || { errors: [], warnings: [] };

  for (const device of state.config.devices) {
    if (device.type === "bloc9") {
      state.bloc9Drafts[bloc9KeyFor(device)] = clone(device);
    }
    if (device.type === "bloc7") {
      state.bloc7Drafts[`bloc7:${device.bus_id}`] = clone(device);
    }
  }
  renderDiagnostics();
}

async function refreshDiscovery() {
  const previousCandidates = state.discovery.candidates || [];
  const response = await fetch(resolveAppUrl("api/discovery"));
  const payload = await response.json();
  updateOutputActivity(previousCandidates, payload.candidates || []);
  state.discovery = payload;
  if (hasActiveEditor("bloc9")) return;
  rerender(() => renderTabIfVisible("bloc9"));
}

async function refreshBloc7Candidates() {
  const response = await fetch(resolveAppUrl("api/discovery/bloc7"));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    state.bloc7Discovery = { status: "error", candidates: [], total_messages: 0, unique_ids: 0 };
    if (payload.error) showToast(payload.error, "warning");
    if (hasActiveEditor("bloc7")) return;
    rerender(() => renderTabIfVisible("bloc7"));
    return;
  }
  state.bloc7Discovery = payload;
  if (hasActiveEditor("bloc7")) return;
  rerender(() => renderTabIfVisible("bloc7"));
}

async function refreshSetupHelper() {
  const response = await fetch(resolveAppUrl("api/setup-helper"));
  const payload = await response.json();
  state.setupHelper = payload;
  syncSetupHelperDraft();
  if (hasActiveEditor("setup-helper")) return;
  rerender(() => renderTabIfVisible("helper"));
}

async function ensureDiscoveryRunning() {
  if (!state.runtime.running || state.discovery.status === "running") return;
  const response = await fetch(resolveAppUrl("api/discovery/start"), { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (response.ok) {
    state.discovery = payload;
  }
  rerender(() => renderTabIfVisible("bloc9"));
}

async function toggleDiscovery() {
  const action = state.discovery.status === "running" ? "stop" : "start";
  const response = await fetch(resolveAppUrl(`api/discovery/${action}`), {
    method: "POST",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(payload.error || "Failed to change discovery state", "error");
    return;
  }
  state.discovery = payload;
  rerender(() => renderTabIfVisible("bloc9"));
  showToast(
    action === "start" ? "Bloc9 discovery started." : "Bloc9 discovery stopped.",
    "success",
  );
}

async function applyConfig(nextConfig, successMessage) {
  const response = await fetch(resolveAppUrl("api/config/apply"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config: nextConfig, base_revision: state.baseRevision }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    state.diagnostics = payload.diagnostics || state.diagnostics;
    renderDiagnostics();
    showToast(payload.details || payload.error || "Failed to apply configuration.", "error");
    return false;
  }
  state.config = payload.config;
  state.baseRevision = payload.revision;
  state.diagnostics = payload.diagnostics || { errors: [], warnings: [] };
  renderDiagnostics();
  showToast(successMessage, "success");
  return true;
}

async function startSetupHelperSession() {
  const response = await fetch(resolveAppUrl("api/setup-helper/session"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: state.setupHelperDraft.target_name,
      entity_id: state.setupHelperDraft.entity_id || null,
      role: state.setupHelperDraft.role,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(payload.error || "Failed to start the setup helper.", "error");
    return;
  }
  state.setupHelper = payload;
  syncSetupHelperDraft();
  rerender(() => renderTabIfVisible("helper"));
}

async function runSetupHelper(action) {
  const response = await fetch(resolveAppUrl("api/setup-helper/run"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(payload.error || "Failed to start the guided capture.", "error");
    return;
  }
  state.setupHelper = payload;
  rerender(() => renderTabIfVisible("helper"));
}

async function stopSetupHelper() {
  const response = await fetch(resolveAppUrl("api/setup-helper/stop"), {
    method: "POST",
  });
  state.setupHelper = await response.json().catch(() => ({
    status: "idle",
    phase: "idle",
    instruction: "Start a setup helper session to begin guided discovery.",
  }));
  state.setupHelperDraft.selected_outputs = {};
  rerender(() => renderTabIfVisible("helper"));
}

async function applySetupHelperFindings() {
  const selected = selectedSetupHelperOutputs();
  const actionKey = "helper-apply";
  setBusy(actionKey, true);
  try {
    const response = await fetch(resolveAppUrl("api/setup-helper/apply"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_revision: state.baseRevision,
        role: state.setupHelperDraft.role,
        entity_id: state.setupHelperDraft.entity_id,
        output_name: state.setupHelperDraft.output_name,
        device_names: state.setupHelperDraft.device_names,
        outputs: selected.map((output) => ({
          bus_id: output.bus_id,
          segment_id: output.segment_id,
          output_name: output.output_name,
        })),
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      showToast(payload.details || payload.error || "Failed to apply setup-helper findings.", "error");
      return;
    }
    state.config = payload.config;
    state.baseRevision = payload.revision;
    state.diagnostics = payload.diagnostics || { errors: [], warnings: [] };
    renderDiagnostics();
    await refreshStatus();
    await refreshDiscovery();
    showToast("Setup-helper findings applied to the configuration.", "success");
  } finally {
    setBusy(actionKey, false);
  }
}

async function saveBloc9Card(cardKey) {
  const configuredIndex = state.config.devices.findIndex(
    (device) => device.type === "bloc9" && bloc9KeyFor(device) === cardKey,
  );
  const draft = buildBloc9DraftForSave(state.bloc9Drafts[cardKey]);
  const nextConfig = clone(state.config);
  if (configuredIndex >= 0) {
    nextConfig.devices[configuredIndex] = draft;
  } else {
    nextConfig.devices.push(draft);
  }

  const actionKey = `save-bloc9:${cardKey}`;
  setBusy(actionKey, true);
  try {
    const success = await applyConfig(
      nextConfig,
      configuredIndex >= 0 ? `Saved Bloc9 #${cardKey}.` : `Added Bloc9 #${cardKey}.`,
    );
    if (!success) return;
    state.bloc9Drafts[cardKey] = clone(draft);
    await refreshStatus();
    rerender(() => renderTabIfVisible("bloc9"));
  } finally {
    setBusy(actionKey, false);
  }
}

async function sendControl(cardKey, outputName, on) {
  const draft = state.bloc9Drafts[cardKey];
  const output = draft?.outputs?.[outputName] || blankOutput();
  const switchNr = outputs.indexOf(outputName);
  const control = getControlState(cardKey, outputName);
  const canUseBrightness = outputUsesBrightness(output);
  const isPulse = outputUsesPulse(output);
  const actionKey = `control:${cardKey}:${outputName}:${on ? "on" : "off"}`;
  setBusy(actionKey, true);
  try {
    const response = await fetch(resolveAppUrl("api/discovery/control"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bus_id: Number(draft.bus_id),
        segment_id: Number(draft.segment_id || 0),
        switch_nr: switchNr,
        on,
        role: output.role || null,
        brightness: on && canUseBrightness ? Number(control.brightness) : null,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      showToast(payload.error || "Failed to send command.", "error");
      return;
    }
    showToast(
      `Sent ${isPulse ? "trigger" : on ? "on" : "off"} command to ${outputName.toUpperCase()} on Bloc9 #${cardKey}.`,
      "success",
    );
  } finally {
    setBusy(actionKey, false);
  }
}

async function saveBloc7Candidate(candidateKey) {
  const candidate = (state.bloc7Discovery.candidates || []).find(
    (entry) => entry.candidate_key === candidateKey,
  );
  if (!candidate) {
    showToast("The selected Bloc7 message is no longer available.", "error");
    return;
  }

  const candidateDraft = ensureBloc7CandidateDraft(candidate);
  const validation = validateBloc7CandidateDraft(candidate, candidateDraft);
  if (!validation.valid) {
    rerender(() => renderTabIfVisible("bloc7"));
    showToast("Complete the channel names and entity IDs before saving.", "error");
    return;
  }

  const device = buildBloc7DeviceFromCandidate(
    candidate,
    candidateDraft,
    validation.configuredDevice,
  );
  const nextConfig = clone(state.config);
  const configuredIndex = nextConfig.devices.findIndex(
    (entry) =>
      entry.type === "bloc7"
          && entry.type === device.type
          && routeSlug(entry.bus_id, entry.segment_id || 0)
            === routeSlug(validation.configuredDevice?.bus_id ?? device.bus_id, validation.configuredDevice?.segment_id ?? device.segment_id),
  );
  if (configuredIndex >= 0) {
    nextConfig.devices[configuredIndex] = device;
  } else {
    nextConfig.devices.push(device);
  }

  const actionKey = `save-bloc7-candidate:${candidateKey}`;
  setBusy(actionKey, true);
  try {
    const success = await applyConfig(
      nextConfig,
      configuredIndex >= 0
        ? `Saved Bloc7 message ${candidate.arbitration_id}.`
        : `Added Bloc7 message ${candidate.arbitration_id}.`,
    );
    if (!success) return;
    state.bloc7CandidateDrafts[candidateKey] = {
      bus_id: device.bus_id,
      segment_id: device.segment_id,
      channels: Object.fromEntries(
        (candidate.suggested_sensors || []).map((suggestion) => {
          const savedSensor = (device.sensors || []).find((sensor) =>
            matchesBloc7Suggestion(sensor, suggestion),
          );
          return [
            suggestion.suggestion_key,
            {
              name: savedSensor?.name || "",
              entity_id: savedSensor?.entity_id || "",
              sensor_type: savedSensor?.sensor_type || suggestion.sensor_type,
            },
          ];
        }),
      ),
    };
    await refreshStatus();
    rerender(() => renderTabIfVisible("bloc7"));
  } finally {
    setBusy(actionKey, false);
  }
}

function addManualBloc7Draft() {
  const draftKey = `new-bloc7:${Date.now()}`;
  state.bloc7Drafts[draftKey] = {
    ...blankBloc7Device(),
    bus_id: nextBloc7BusId(),
    sensors: [blankSensor()],
  };
  state.activeTab = "bloc7";
  rerender(renderCurrentTab);
}

async function saveBloc7Card(cardKey) {
  const draft = buildBloc7DraftForSave(state.bloc7Drafts[cardKey]);
  const configuredIndex = state.config.devices.findIndex(
    (device) => device.type === "bloc7" && Number(device.bus_id) === Number(draft.bus_id),
  );
  const nextConfig = clone(state.config);
  if (configuredIndex >= 0) {
    nextConfig.devices[configuredIndex] = draft;
  } else {
    nextConfig.devices.push(draft);
  }

  const actionKey = `save-bloc7:${cardKey}`;
  setBusy(actionKey, true);
  try {
    const success = await applyConfig(
      nextConfig,
      configuredIndex >= 0 ? `Saved Bloc7 #${draft.bus_id}.` : `Added Bloc7 #${draft.bus_id}.`,
    );
    if (!success) return;
    delete state.bloc7Drafts[cardKey];
    state.bloc7Drafts[`bloc7:${draft.bus_id}`] = clone(draft);
    await refreshStatus();
    rerender(() => renderTabIfVisible("bloc7"));
  } finally {
    setBusy(actionKey, false);
  }
}

document.addEventListener("click", async (event) => {
  const tabButton = event.target.closest("[data-tab]");
  if (tabButton && tabButton.classList.contains("tab-button")) {
    state.activeTab = tabButton.dataset.tab;
    rerender(renderCurrentTab);
    return;
  }

  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) return;
  const action = actionTarget.dataset.action;

  if (action === "save-bloc9") {
    await saveBloc9Card(actionTarget.dataset.cardKey);
    return;
  }
  if (action === "toggle-bloc9-card") {
    const cardKey = actionTarget.dataset.cardKey;
    state.bloc9CardExpansion[cardKey] = !isBloc9CardExpanded(cardKey);
    rerender(() => renderTabIfVisible("bloc9"));
    return;
  }
  if (action === "toggle-bloc9-output") {
    const { cardKey, output } = actionTarget.dataset;
    state.bloc9OutputExpansion[cardKey] = state.bloc9OutputExpansion[cardKey] || {};
    state.bloc9OutputExpansion[cardKey][output] = !isBloc9OutputExpanded(cardKey, output);
    rerender(() => renderTabIfVisible("bloc9"));
    return;
  }
  if (action === "send-control") {
    await sendControl(
      actionTarget.dataset.cardKey,
      actionTarget.dataset.output,
      actionTarget.dataset.on === "1",
    );
    return;
  }
  if (action === "save-bloc7") {
    await saveBloc7Card(actionTarget.dataset.cardKey);
    return;
  }
  if (action === "save-bloc7-candidate") {
    await saveBloc7Candidate(actionTarget.dataset.candidateKey);
    return;
  }
  if (action === "add-bloc7-sensor") {
    state.bloc7Drafts[actionTarget.dataset.cardKey].sensors.push(blankSensor());
    rerender(() => renderTabIfVisible("bloc7"));
    return;
  }
  if (action === "remove-bloc7-sensor") {
    state.bloc7Drafts[actionTarget.dataset.cardKey].sensors.splice(
      Number(actionTarget.dataset.sensorIndex),
      1,
    );
    rerender(() => renderTabIfVisible("bloc7"));
    return;
  }
  if (action === "helper-start") {
    await startSetupHelperSession();
    return;
  }
  if (action === "helper-stop") {
    await stopSetupHelper();
    return;
  }
  if (action === "helper-run-tap") {
    await runSetupHelper("tap");
    return;
  }
  if (action === "helper-run-hold") {
    await runSetupHelper("hold");
    return;
  }
  if (action === "helper-apply") {
    await applySetupHelperFindings();
    return;
  }
});

document.addEventListener("input", (event) => {
  const target = event.target;
  if (target.dataset.cardKind === "bloc9") {
    updateBloc9DraftField(
      target.dataset.cardKey,
      target.dataset.field,
      target.value,
      target.dataset.output || null,
    );
    return;
  }
  if (target.dataset.cardKind === "bloc7") {
    updateBloc7DraftField(
      target.dataset.cardKey,
      target.dataset.field,
      target.value,
      target.dataset.sensorIndex !== undefined ? Number(target.dataset.sensorIndex) : null,
    );
    return;
  }
  if (target.dataset.cardKind === "bloc7-candidate") {
    updateBloc7CandidateDraftField(
      target.dataset.candidateKey,
      target.dataset.suggestionKey,
      target.dataset.field,
      target.value,
    );
    return;
  }
  if (target.dataset.cardKind === "bloc9-control") {
    const control = getControlState(target.dataset.cardKey, target.dataset.output);
    control.brightness = Number(target.value);
    const valueLabel = target.closest(".slider-field")?.querySelector(".slider-value");
    if (valueLabel) valueLabel.textContent = String(control.brightness);
    return;
  }
  if (target.dataset.cardKind === "setup-helper") {
    state.setupHelperDraft[target.dataset.field] = target.value;
    if (target.dataset.field === "target_name" && !state.setupHelperDraft.entity_id) {
      state.setupHelperDraft.entity_id = slugifyEntityId(target.value);
    }
    const suggestion = getSetupHelperSuggestions().find(
      (item) => item.name.toLowerCase() === String(target.value || "").trim().toLowerCase(),
    );
    if (suggestion) {
      state.setupHelperDraft.entity_id = suggestion.entity_id;
      state.setupHelperDraft.role = suggestion.role;
      if (!state.setupHelperDraft.output_name) state.setupHelperDraft.output_name = suggestion.name;
    }
    return;
  }
  if (target.dataset.cardKind === "setup-helper-device") {
    state.setupHelperDraft.device_names[target.dataset.field] = target.value;
    return;
  }
  if (target.dataset.cardKind === "setup-helper-output") {
    state.setupHelperDraft.selected_outputs[target.dataset.outputRef] = target.checked;
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (target.dataset.cardKind === "bloc9") {
    updateBloc9DraftField(
      target.dataset.cardKey,
      target.dataset.field,
      target.value,
      target.dataset.output || null,
    );
    rerender(() => renderTabIfVisible("bloc9"));
    return;
  }
  if (target.dataset.cardKind === "bloc7") {
    updateBloc7DraftField(
      target.dataset.cardKey,
      target.dataset.field,
      target.value,
      target.dataset.sensorIndex !== undefined ? Number(target.dataset.sensorIndex) : null,
    );
    rerender(() => renderTabIfVisible("bloc7"));
    return;
  }
  if (target.dataset.cardKind === "bloc7-candidate") {
    updateBloc7CandidateDraftField(
      target.dataset.candidateKey,
      target.dataset.suggestionKey,
      target.dataset.field,
      target.value,
    );
    rerender(() => renderTabIfVisible("bloc7"));
    return;
  }
  if (target.dataset.cardKind === "setup-helper" || target.dataset.cardKind === "setup-helper-device") {
    rerender(() => renderTabIfVisible("helper"));
    return;
  }
  if (target.dataset.cardKind === "setup-helper-output") {
    state.setupHelperDraft.selected_outputs[target.dataset.outputRef] = target.checked;
    rerender(() => renderTabIfVisible("helper"));
  }
});

document.getElementById("discovery-toggle-button").addEventListener("click", toggleDiscovery);
document.getElementById("bloc7-refresh-button").addEventListener("click", refreshBloc7Candidates);
document.getElementById("add-bloc7-button").addEventListener("click", addManualBloc7Draft);

async function initialize() {
  heartbeatManager?.start();
  await Promise.all([refreshStatus(), loadConfig(), refreshDiscovery(), refreshBloc7Candidates(), refreshSetupHelper()]);
  renderHeader();
  renderDiagnostics();
  renderCurrentTab();
  await ensureDiscoveryRunning();
  window.setInterval(refreshStatus, 5000);
  window.setInterval(refreshDiscovery, 2000);
  window.setInterval(refreshBloc7Candidates, 4000);
  window.setInterval(refreshSetupHelper, 1000);
}

initialize().catch((error) => {
  showToast(error.message || "Failed to load the setup UI.", "error");
});
