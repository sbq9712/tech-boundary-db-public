# 侧边栏重设计 + 行业图景并入深度调研 · 实施规格（2026-09-21）

## 需求（用户口述）
1. 侧边栏默认收起为窄条（仅容一个 logo 宽度）；鼠标悬停窄条→展开为现有宽度；移出→收起。按位置判定，不点击。
2. 收起条自上而下：品牌 logo、门户、广度追踪、深度调研、资料库、用户管理 各自的 logo；底部用户头像。
3. 账户行：移除"密码/退出"两个小按钮，整行成为一个按钮；点击弹出面板：上方"设置"、下方"退出登录"；设置=现修改密码弹窗，标题改"设置"，修改密码为其子功能；无头像上传；只显示名称，不显示角色。
4. 展开态：顶部品牌 logo（替换原"技术边界数据库"图标）；每项文字前有对应 logo。
5. 行业图景不再有侧边栏项（并入深度调研）：深度调研页顶部两个按钮"深度调研报告 / 行业图景"切换。
6. 文案删除：用户管理副标题"管理系统用户账号、角色和启用状态"；资料库标题块（"资料库"+权限副标题，筛选行保留）；深度调研 h1（由切换按钮替代）；行业图景 h1"追求完备而互斥"。

## 决策
- D1 logo 素材：《..AAA UI设计》文件夹当前为空（服务器上未发现图片）。先以内联 SVG 图标占位，集中在 app.js `NAV_ICONS`/`BRAND_LOGO` 常量；素材到位后仅改这两处（或换 <img>）。
- D2 悬停展开采用 overlay（侧边栏 fixed，展开时浮在内容上），主区不回流——广度追踪是 iframe，推挤式展开会造成反复重排。
- D3 行业图景路由 `#map` 保留为别名（渲染 dashboard 图景 tab），旧链接不 404；`data-map-group` 切换改写 `#dashboard?tab=map&group=…`。
- D4 tab 深链：`#dashboard?tab=map|report`（缺省 report）。
- D5 账户弹出面板用 fixed 定位（侧边栏 overflow:hidden 会裁剪 absolute 弹层）；外点/Esc/路由切换关闭。
- D6 收起态隐藏会话中枢与新对话按钮（CSS opacity/pointer-events），DOM 保留。

## 改动面
- app.js：shell() 侧边栏结构、NAV_ICONS/BRAND_LOGO、账户面板、dashboardView tabs、mapView→mapBody 复用、usersView/libraryView 文案、bindEvents。
- app.css：sidebar 收起/展开、图标、账户面板、lib-head 调整。
- auth.js：弹窗标题"设置"+子标题"修改密码"。
- index.html：cache bump。

## 验收
- node --check 通过；无头浏览器截图收起/展开/账户面板/图景 tab 四态。
- `#map`、`#dashboard?tab=map`、门户"查看全部"跳转均可达图景。

## v6 增补（2026-09-22 下午，用户反馈第 5 轮）
- D7 图标横向基准＝收起态：收起态 rail 56px 居中给出 img x=17。展开态全部对齐到同一 x：
  brand padding-left 17→16、nav 横向 padding 10→8、account 横向 padding 10→12（+btn 4px）；
  Playwright 断言两态下 brand/门户/广度/深度/资料库/用户管理 img 均 22px 宽、x=17。
- D8 收起/展开图标全态同尺寸：展开态右侧按钮 16px → 22px，与收起态品牌悬浮图标一致（用户报"大小不一样"根因）。
- D9 「历史对话」折叠失效根因：`.sidebar-conversation-list{display:flex}` 覆盖 UA 的
  `[hidden]{display:none}`，JS 设 hidden 属性无视觉效果。修复：补
  `.sidebar-conversation-list[hidden]{display:none}`；测试改断 computed display 而非 hidden 属性。
- D10 导航按钮纵向位置两态不变：brand 行固定 52px（v5 已做），v6 断言 [data-route] 按钮 y 在收起/展开两态逐项相等。
- D11 资料库列表不再显示原文件名（s41467-….pdf 等），只显示资料标题（AI 标记保留，note 追加显示）；原文件名在下载时仍作为保存文件名。
- D12 上传弹窗改版：去掉密级/来源类型字段；初始只显示拖拽区；选定文件后出现表格（一行一文件：
  文件/资料标题/资料日期/行业图景节点/备注/移除），弹窗加宽 min(1000px)；自定义日历删除，
  日期用原生 input[type=date]；提交按行逐个文件上传（title/document_date/primary_category/note 随行生效），
  单行失败不影响其余行，已成功行重试时跳过。
- D13 Hermes 清理（服务器侧，已授权）：hermes-gateway.service 停用并删除 unit；~/.hermes（20GB）删除；
  ~/.local/bin/hermes 与 .bashrc 音效 hook 删除。headroom-hermes-proxy.service 为独立代理（仅名字带 hermes，
  读 ~/.headroom），保留。仓库内 hermes_bridge/readonly-agent HTTP 链路为在用功能，不改。
