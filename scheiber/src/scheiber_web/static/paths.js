(function () {
  function normalizedBasePath() {
    const configuredPath =
      typeof window.ScheiberWebBasePath === "string" ? window.ScheiberWebBasePath : "";
    const basePath = configuredPath || window.location.pathname || "/";
    return basePath.endsWith("/") ? basePath : `${basePath}/`;
  }

  function resolve(path) {
    const relativePath = String(path ?? "").replace(/^\/+/, "");
    return new URL(relativePath, `${window.location.origin}${normalizedBasePath()}`).toString();
  }

  window.ScheiberWebPaths = {
    basePath: normalizedBasePath(),
    resolve,
  };
})();
