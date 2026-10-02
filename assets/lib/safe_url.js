/**
 * TechDB 共享 URL 消毒器（T7/G11，2026-10-02）。
 *
 * 背景：qa.js 的 _qaSafeUrl/_qaSafeHref 已修复引用卡 javascript: 注入，
 * 但 app.js inlineMd 把 markdown 链接原始 URL 直插 href——同一漏洞在
 * 门户渲染链复现。消毒逻辑必须单一来源，两页共享，禁止各自复制粘贴漂移。
 *
 * 规则（与 qa.js 原实现语义一致，codex 复审 R2-1 结论）：
 *  1. 先剔 ASCII 控制字符 \x00-\x1F\x7F 再 trim——浏览器 URL 解析会剔
 *     TAB/LF/CR 与首尾 C0，`java\tscript:` / `\0javascript:` 由此归一为
 *     javascript:；先匹配 scheme 再剔控制字符会被绕过。
 *  2. scheme 白名单 http/https/mailto；javascript:/data:/vbscript: 等
 *     一律降级 '#'。
 *  3. 无 scheme 的相对地址原样放行（站内跳转）。
 *
 * 形态：浏览器经典脚本 IIFE 挂 window.TechDBSafeUrl（两页均无 ES module，
 * script 标签顺序加载，须先于 app.js/qa.js）；同时 CommonJS 导出供
 * tests/js（Node）直接 require 复用。
 */
(function (root) {
  'use strict';

  var CTRL_RE = /[\x00-\x1F\x7F]/g;
  var SCHEME_RE = /^([a-z][a-z0-9+.-]*):/i;
  var SAFE_SCHEME_RE = /^(https?|mailto)$/i;

  function safeUrl(url) {
    var u = String(url == null ? '' : url).replace(CTRL_RE, '').trim();
    if (!u) return '';
    var m = SCHEME_RE.exec(u);
    if (m) return SAFE_SCHEME_RE.test(m[1]) ? u : '#';
    return u; // 无 scheme：相对地址
  }

  /** 属性插值专用：白名单 + `"` 百分号编码 + 基本 HTML 转义。 */
  function safeHref(url, escapeHtmlFn) {
    var cleaned = safeUrl(url).replace(/"/g, '%22');
    if (typeof escapeHtmlFn === 'function') return escapeHtmlFn(cleaned);
    // 兜底转义（调用方没有 escHtml 时）：& < > "
    return cleaned
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  var api = { safeUrl: safeUrl, safeHref: safeHref };
  if (typeof module === 'object' && module.exports) {
    module.exports = api; // Node（tests/js）
  }
  if (typeof root !== 'undefined') {
    root.TechDBSafeUrl = api; // 浏览器全局
  }
})(typeof window !== 'undefined' ? window : globalThis);
