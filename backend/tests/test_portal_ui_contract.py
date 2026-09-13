from urllib.request import urlopen


CSS_URL = "http://web/app.css"
JS_URL = "http://web/app.js"


def load_served_css() -> str:
    with urlopen(CSS_URL, timeout=10) as response:
        return response.read().decode("utf-8")


def load_served_js() -> str:
    with urlopen(JS_URL, timeout=10) as response:
        return response.read().decode("utf-8")


def test_sidebar_is_visually_stable():
    css = load_served_css()
    sidebar = css.split(".sidebar{", 1)[1].split("}", 1)[0]
    assert "width:196px" in sidebar
    assert "flex-shrink:0" in sidebar
    assert "height:100dvh" in css.split(".app-shell{", 1)[1].split("}", 1)[0]
    assert "transition:width" not in css
    assert "overflow:hidden" in css.split(".workspace{", 1)[1].split("}", 1)[0]
    assert "overflow-y:auto" in css.split(".main{", 1)[1].split("}", 1)[0]


def test_home_layout_is_boundary_alert_and_knowledge_workbench():
    css = load_served_css()
    js = load_served_js()
    assert "--drawer-w:max(340px,33.333vw)" in css
    assert ".home-drawer{" in css
    assert "home-drawer-tab" in css
    assert "transform:scaleX(.06)" in css
    assert ".home-drawer-tab{" in css
    assert ".home-knowledge-section" in css
    assert "margin-left:calc(var(--drawer-w)" not in css
    assert ".home-boundary-grid" in css
    assert ".home-alert-list" in css
    assert ".home-knowledge-section" in css
    assert "技术边界" in js
    assert "技术预警" in js
    assert "与知识库互动" not in js
    assert "loadHomeBoundaries" in js
    assert "sort((a,b)=>new Date(b.updated_at||0)-new Date(a.updated_at||0))" in js
    assert "是什么" in js and "关键指标边界" in js
    assert "<th>情报发布</th>" not in js and "<th>预警生成</th>" not in js
    assert "进入广度追踪" not in js
    assert "HOME_ALERT_PAGE_SIZE=5" in js
    assert "homeAlertTimestamp(b)-homeAlertTimestamp(a)" in js
    assert "home-alert-reason-text" in js and "data-alert-reason-toggle" in js
    assert "focus_title" in js and "focus_date" in js and "focus_url" in js
    assert "/breadth/data/processed/alert-records.json" in js
    assert "homeDrawer" in js
    assert "homeDrawerClose" not in js
    assert "homeDrawerOpen" in js
    assert "drawer-collapsed" in js
    assert "knowledgeToggle" not in js
    assert "情报面板" not in js
    assert "homeDrawerOutsideBound" in js
    assert "event.target.closest('.home-drawer,.home-drawer-tab')" in js
    assert "home-drawer-collapse" not in css
    assert ".home-knowledge-section .qa-graph-container{" in css
    assert "flex:1 1 0" in css
    assert "width:100%" in css
    assert "min-height:360px" in css
    assert "最新研究结论" not in js
    assert "高信号变化" not in js
    assert "基于知识库的问答" not in js


def test_answer_contains_inline_resource_slots_and_enter_send():
    js = load_served_js()
    css = load_served_css()
    assistant_text = css.split(".conversation-history .assistant-msg .response-text{", 1)[1].split("}", 1)[0]
    user_text = css.split(".conversation-history .user-msg p{", 1)[1].split("}", 1)[0]
    emphasis = css.split(".conversation-history .assistant-msg .response-text strong{", 1)[1].split("}", 1)[0]
    assert "font-size:15px" in assistant_text
    assert "font-size:15px" in user_text
    assert "font-weight:700" in emphasis
    assert "background:var(--brand-bg)" in emphasis
    assert ".conversation-history .assistant-msg > strong" in css
    assert "function renderInlineResources" in js
    assert "检索 ${count} 条索引记录" in js
    assert "qa-citations-block" in js
    assert "qa-citation-ref" in js
    assert "data-citation-card" in js
    assert "data-qa-action=\"copy\"" in js
    assert "data-qa-action=\"regenerate\"" in js
    assert "data-qa-action=\"export\"" in js
    assert "home_query_draft" in js
    assert "keydown" in js and "Enter" in js
    assert ".inline-resources" in css
    assert "if(/^[-*_]{3,}$/.test(trimmed))" in js
    assert "function normalizeChatSoftBreaks" in js
    assert "!isSentenceEnd(previous)&&next&&!isBlockStart(next)" in js


def test_home_exposes_model_selector_and_sends_model_param():
    js = load_served_js()
    css = load_served_css()
    assert "modelSelect" in js
    assert "assistant_model" in js
    assert "/api/assistant/models" in js
    assert "glm-5.1" in js
    assert "method:'POST'" in js
    assert "session_id:requestedSessionId||null" in js
    assert "AbortController" in js
    assert ".model-select" in css


def test_home_exposes_persisted_conversations_in_sidebar():
    js = load_served_js()
    css = load_served_css()
    assert "/api/conversations" in js
    assert "sidebarNewConversationBtn" in js
    assert "sidebarConversationList" in js
    assert "data-conversation-id" in js
    assert "data-delete-conversation" in js
    assert "conversationState" not in js
    assert "sessionSelect" not in js
    assert "newConversationBtn" not in js
    assert "deleteConversationBtn" not in js
    assert "method:'DELETE'" in js
    assert "const deletingActive=sessionId===activeSessionId" in js
    assert "if(deletingActive)startNewConversation()" in js
    assert "loadConversationMessages" in js
    assert "pendingConversation={id:`pending-${requestEpoch}`,title:'新对话',pending:true}" in js
    assert "event.target?.closest?.('#sidebarNewConversationBtn')" in js
    assert "qa-message-avatar" not in js
    assert "sidebar-conversation-heading" not in js
    assert "sidebar-retrieval-status" not in css
    assert ".qa-message.user{justify-content:flex-end}" in css
    assert ".qa-message.assistant{justify-content:flex-start}" in css
    assert ".qa-message-content{min-width:0}" in css
    assert ".qa-message.user .qa-message.user" not in css
    assert "TECHDB_QA_SERVICE_URL" not in js
    assert "regenerate,retry" in js
    assert ".sidebar-conversation-list" in css
    assert "max-height:168px" in css
    assert "overflow-y:hidden" in css
    assert ".sidebar-conversation-list:hover" in css


def test_industry_map_page_uses_server_tree():
    js = load_served_js()
    css = load_served_css()
    assert "loadIndustryMap" in js
    assert "loadIndustryMap" in js
    assert "mindmap-canvas" in js
    assert "bookmark-tab" in js
    assert "data-map-group" in js
    assert "function industryNode" in js
    assert "industryTree" in js
    assert ".mindmap-root" in css
    assert ".mind-card" in css
    assert ".leaf-tags" in css
    assert "category_counts" in js
    assert "/api/delivery-intel/category-counts" in js
    assert "(node.path||[]).join('/')" in js


def test_deep_research_metrics_use_commercial_readiness_statuses():
    js = load_served_js()
    css = load_served_css()
    assert "理论值 / 需求值 / 实际值分列" in js
    assert "进一步调研方向" in js
    assert "✓ 已达商用" in js
    assert "! 未达商用" in js
    assert "? 缺数据" in js
    assert "? 理论不可达" in js
    assert "verificationBadge" not in js
    assert "isSofcReport?'':indicatorGrid('关键指标（经济）'" in js
    assert ".commercial-status-missing" in css
    assert "color:var(--red);background:var(--red-bg)" in css


def test_breadth_portal_focuses_the_exact_alert_record():
    js = load_served_js()
    breadth_js = urlopen("http://web/breadth/app.js", timeout=10).read().decode("utf-8")
    assert "focus_title" in js and "focus_date" in js and "focus_url" in js
    assert "focusRecord" in breadth_js
    assert "data-record-index" in breadth_js
    assert "scrollMarginTop" in breadth_js
    assert "scrollIntoView({ block: 'start' })" in breadth_js
