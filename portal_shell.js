(function () {
  const NAV_ITEMS = [
    { href: "index.html", label: "门户", code: "HOME" },
    { href: "info_table.html", label: "情报总表", code: "INT" },
    { href: "industry_map.html", label: "行业图景", code: "MAP" },
    { href: "industry_dashboards.html", label: "行业仪表盘", code: "ART" },
    { href: "sources.html", label: "信息源", code: "SRC" },
  ];

  function currentFile() {
    const path = location.pathname.split("/").pop() || "index.html";
    return path === "" ? "index.html" : path;
  }

  function injectStyles() {
    if (document.getElementById("techdbPortalShellStyles")) return;
    const style = document.createElement("style");
    style.id = "techdbPortalShellStyles";
    style.textContent = `
      :root{--portal-sidebar-width:264px;}
      body.with-portal-shell{padding-left:var(--portal-sidebar-width)!important;}
      body.with-portal-shell .topbar{display:none!important;}
      body.with-portal-shell > .container,
      body.with-portal-shell > main,
      body.with-portal-shell > .wrap{max-width:1400px;}
      .portal-shell-sidebar{position:fixed;left:0;top:0;bottom:0;width:var(--portal-sidebar-width);z-index:9998;background:#fff;border-right:1px solid rgba(0,0,0,.08);padding:18px 14px;display:flex;flex-direction:column;gap:18px;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif;color:#171717;}
      .portal-shell-brand{padding:4px 6px 14px;}
      .portal-shell-title{font-weight:650;letter-spacing:-.04em;font-size:18px;}
      .portal-shell-sub{margin-top:6px;color:#666;font-size:12px;line-height:1.45;}
      .portal-shell-nav{display:flex;flex-direction:column;gap:6px;}
      .portal-shell-nav a{display:flex;align-items:center;justify-content:space-between;min-height:42px;padding:0 10px;border-radius:10px;color:#3f3f46;font-size:14px;font-weight:500;text-decoration:none;}
      .portal-shell-nav a:hover,.portal-shell-nav a.active{background:#f4f4f5;color:#111;text-decoration:none;}
      .portal-shell-code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;font-size:11px;color:#a1a1aa;}
      .portal-shell-account{margin-top:auto;border-top:1px solid rgba(0,0,0,.08);padding-top:14px;}
      .portal-shell-account-title{font-size:12px;color:#888;padding:0 10px 8px;}
      .portal-shell-account button{width:100%;height:40px;text-align:left;border:0;background:transparent;border-radius:10px;padding:0 10px;color:#3f3f46;cursor:pointer;font:inherit;}
      .portal-shell-account button:hover{background:#f4f4f5;color:#111;}
      .portal-shell-legacy{margin:10px 10px 0;color:#999;font-size:11px;line-height:1.45;}
      @media(max-width:980px){body.with-portal-shell{padding-left:0!important;padding-top:0!important}.portal-shell-sidebar{position:relative;width:auto;height:auto}.portal-shell-account{margin-top:0}}
    `;
    document.head.appendChild(style);
  }

  function injectSidebar() {
    if (document.querySelector(".portal-shell-sidebar")) return;
    document.body.classList.add("with-portal-shell");
    const active = currentFile();
    const aside = document.createElement("aside");
    aside.className = "portal-shell-sidebar";
    aside.innerHTML = `
      <div class="portal-shell-brand">
        <div class="portal-shell-title">技术边界数据库</div>
        <div class="portal-shell-sub">默认从门户进入，支持页面只作为辅助工具。</div>
      </div>
      <nav class="portal-shell-nav" aria-label="统一主导航">
        ${NAV_ITEMS.map(item => `<a class="${active === item.href ? "active" : ""}" href="${item.href}"><span>${item.label}</span><span class="portal-shell-code">${item.code}</span></a>`).join("")}
      </nav>
      <div class="portal-shell-account">
        <div class="portal-shell-account-title">账号</div>
        <button type="button" data-change-password>修改密码</button>
        <button type="button" data-logout>退出登录</button>
        <div class="portal-shell-legacy">旧版上传、批量导入和草稿页已保留，但不作为主入口。</div>
      </div>
    `;
    document.body.insertBefore(aside, document.body.firstChild);
    aside.querySelector("[data-change-password]").addEventListener("click", () => window.Auth && Auth.showChangePassword());
    aside.querySelector("[data-logout]").addEventListener("click", () => window.Auth && Auth.logout());
  }

  function boot() {
    injectStyles();
    injectSidebar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
