(function () {
  const STORAGE_KEY = "scheiber-web-ui-client-id";
  const HEARTBEAT_INTERVAL_MS = 5000;

  function buildClientId() {
    if (window.crypto?.randomUUID) {
      return window.crypto.randomUUID();
    }
    return `browser-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function getClientId() {
    let clientId = window.sessionStorage.getItem(STORAGE_KEY);
    if (!clientId) {
      clientId = buildClientId();
      window.sessionStorage.setItem(STORAGE_KEY, clientId);
    }
    return clientId;
  }

  function sendJson(path, payload, keepalive = false) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive,
    }).catch(() => null);
  }

  function createHeartbeatManager(pageName) {
    const clientId = getClientId();
    let intervalId = null;
    let stopped = false;

    async function sendHeartbeat() {
      if (stopped) return null;
      return sendJson("./api/frontend/heartbeat", { client_id: clientId, page: pageName });
    }

    function disconnect() {
      if (stopped) return;
      stopped = true;
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }

      const payload = { client_id: clientId, page: pageName };
      if (navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify(payload)], {
          type: "application/json",
        });
        navigator.sendBeacon("./api/frontend/disconnect", blob);
        return;
      }
      sendJson("./api/frontend/disconnect", payload, true);
    }

    function start() {
      if (intervalId || stopped) return;
      sendHeartbeat();
      intervalId = window.setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);
    }

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        sendHeartbeat();
      }
    });
    window.addEventListener("pagehide", disconnect);

    return { clientId, start, disconnect, sendHeartbeat };
  }

  window.ScheiberHeartbeat = { createHeartbeatManager };
})();
