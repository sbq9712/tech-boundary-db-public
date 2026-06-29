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
    assert "--side-collapsed:248px;--side-expanded:248px" in css
    assert ".sidebar{position:fixed" in css
    assert "height:100dvh" in css.split(".sidebar{", 1)[1].split("}", 1)[0]
    assert "transition:width" not in css
    assert ".brand-copy,.nav-text,.account-copy,.account-actions{opacity:1}" in css
    workspace = css.split(".workspace{", 1)[1].split("}", 1)[0]
    assert "margin-left:var(--side-collapsed)" in workspace
    assert "overflow:hidden" in workspace


def test_home_layout_keeps_single_hot_intel_panel_right_of_conversation():
    css = load_served_css()
    js = load_served_js()
    assert ".home-main{height:100%;display:grid;grid-template-columns:minmax(520px,1fr) 440px" in css
    assert ".home-insights" in css
    assert "function renderInsightPanels(){return insightCard('热点情报推送'" in js
    assert "insightCard('行业参数边界'" not in js
    assert "insightCard('相关行业预警情报'" not in js
    assert "function dashboardPanel" not in js


def test_answer_contains_inline_resource_slots_and_enter_send():
    js = load_served_js()
    css = load_served_css()
    assert "function renderInlineResources" in js
    assert "相关文档" in js
    assert "参数边界" in js
    assert "预警情报" in js
    assert "相关仪表盘" in js
    assert "home_query_draft" in js
    assert "keydown" in js and "Enter" in js
    assert ".inline-resources" in css


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
