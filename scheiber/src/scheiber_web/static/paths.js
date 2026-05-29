(function () {
  function fallbackBasePath() {
    const pathname = window.location.pathname || "/";
    if (pathname === "/" || pathname.endsWith("/")) {
      return pathname;
    }
    const trimmed = pathname.replace(/\/+$/, "");
    const slashIndex = trimmed.lastIndexOf("/");
    if (slashIndex <= 0) {
      return "/";
    }
    return `${trimmed.slice(0, slashIndex)}/`;
  }

  function normalizedBasePath() {
    const configuredPath =
      typeof window.ScheiberWebBasePath === "string" ? window.ScheiberWebBasePath : "";
    const basePath = configuredPath || fallbackBasePath();
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
