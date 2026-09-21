// auth.js — 全局认证工具库（非模块，设置 window.Auth）
(function () {
  const TOKEN_KEY = "auth_token";
  const LOGIN_PAGE = "/login.html";
  const API_BASE = "/api";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  // 返回携带 Authorization 的 headers 对象（如无 token 则空）
  function authHeaders() {
    const token = getToken();
    return token ? { Authorization: "Bearer " + token } : {};
  }

  // 未登录时重定向到登录页，传入 next 参数以便登录后跳回
  function requireAuth() {
    if (!getToken()) {
      const next = encodeURIComponent(location.href);
      location.replace(LOGIN_PAGE + "?next=" + next);
    }
  }

  // 登出：清除 token 并跳转到登录页
  function logout() {
    clearToken();
    location.replace(LOGIN_PAGE);
  }

  // 携带认证头的 fetch 封装；401 时自动登出
  async function authFetch(url, options) {
    options = options || {};
    const existingHeaders = options.headers || {};
    const headers = Object.assign({}, authHeaders(), existingHeaders);
    const mergedOptions = Object.assign({}, options, { headers: headers });
    const r = await fetch(url, mergedOptions);
    if (r.status === 401) {
      logout();
      return null;
    }
    return r;
  }

  // ── 修改密码弹窗 ──────────────────────────────────────────
  function _ensureModal() {
    if (document.getElementById("_authChangePwdModal")) return;

    const style = `
      position:fixed;inset:0;z-index:9999;display:none;align-items:center;justify-content:center;
      background:rgba(0,0,0,.60);backdrop-filter:blur(4px);
    `;
    const modal = document.createElement("div");
    modal.id = "_authChangePwdModal";
    modal.setAttribute("style", style);
    modal.innerHTML = `
      <div style="background:#131d30;border:1px solid rgba(255,255,255,.12);border-radius:14px;
                  padding:28px 32px;width:340px;max-width:92vw;color:#e9eefc;font-family:inherit;">
        <div style="font-weight:700;font-size:16px;">设置</div>
        <div style="font-size:12px;color:#a8b3d6;margin:2px 0 18px;">修改密码</div>
        <div style="margin-bottom:12px;">
          <label style="font-size:13px;color:#a8b3d6;display:block;margin-bottom:4px;">当前密码</label>
          <input id="_cpOld" type="password" autocomplete="current-password"
            style="width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.15);
                   background:rgba(255,255,255,.06);color:#e9eefc;font-size:14px;box-sizing:border-box;" />
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:13px;color:#a8b3d6;display:block;margin-bottom:4px;">新密码</label>
          <input id="_cpNew" type="password" autocomplete="new-password"
            style="width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.15);
                   background:rgba(255,255,255,.06);color:#e9eefc;font-size:14px;box-sizing:border-box;" />
        </div>
        <div style="margin-bottom:20px;">
          <label style="font-size:13px;color:#a8b3d6;display:block;margin-bottom:4px;">确认新密码</label>
          <input id="_cpConfirm" type="password" autocomplete="new-password"
            style="width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.15);
                   background:rgba(255,255,255,.06);color:#e9eefc;font-size:14px;box-sizing:border-box;" />
        </div>
        <div id="_cpMsg" style="font-size:13px;min-height:18px;margin-bottom:14px;"></div>
        <div style="display:flex;gap:10px;justify-content:flex-end;">
          <button id="_cpCancel"
            style="cursor:pointer;padding:7px 16px;border-radius:8px;border:1px solid rgba(255,255,255,.12);
                   background:rgba(255,255,255,.05);color:#a8b3d6;font-size:13px;">取消</button>
          <button id="_cpSubmit"
            style="cursor:pointer;padding:7px 16px;border-radius:8px;border:none;
                   background:#4f80ff;color:#fff;font-size:13px;font-weight:600;">保存</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    document.getElementById("_cpCancel").onclick = () => { modal.style.display = "none"; };
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.style.display = "none"; });

    document.getElementById("_cpSubmit").onclick = async () => {
      const oldPwd = document.getElementById("_cpOld").value;
      const newPwd = document.getElementById("_cpNew").value;
      const confirm = document.getElementById("_cpConfirm").value;
      const msg = document.getElementById("_cpMsg");
      msg.style.color = "#f87171";
      msg.textContent = "";

      if (!oldPwd || !newPwd || !confirm) { msg.textContent = "请填写所有字段"; return; }
      if (newPwd !== confirm) { msg.textContent = "两次输入的新密码不一致"; return; }
      if (newPwd.length < 6) { msg.textContent = "新密码不能少于6位"; return; }

      const btn = document.getElementById("_cpSubmit");
      btn.disabled = true;
      btn.textContent = "保存中…";
      try {
        const r = await authFetch(API_BASE + "/auth/password", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_password: oldPwd, new_password: newPwd })
        });
        if (!r) return; // authFetch 已处理 401
        if (r.status === 204) {
          msg.style.color = "#4ade80";
          msg.textContent = "密码修改成功，请重新登录";
          setTimeout(() => { modal.style.display = "none"; logout(); }, 1500);
        } else {
          const data = await r.json().catch(() => ({}));
          msg.textContent = data.detail || "修改失败，请重试";
        }
      } catch (e) {
        msg.textContent = "网络错误，请重试";
      } finally {
        btn.disabled = false;
        btn.textContent = "保存";
      }
    };

    // 支持回车提交
    [document.getElementById("_cpOld"), document.getElementById("_cpNew"), document.getElementById("_cpConfirm")]
      .forEach(el => el.addEventListener("keydown", (e) => { if (e.key === "Enter") document.getElementById("_cpSubmit").click(); }));
  }

  function showChangePassword() {
    _ensureModal();
    const modal = document.getElementById("_authChangePwdModal");
    document.getElementById("_cpOld").value = "";
    document.getElementById("_cpNew").value = "";
    document.getElementById("_cpConfirm").value = "";
    document.getElementById("_cpMsg").textContent = "";
    modal.style.display = "flex";
    document.getElementById("_cpOld").focus();
  }

  window.Auth = { getToken, setToken, clearToken, authHeaders, requireAuth, logout, authFetch, showChangePassword };
})();
