#!/usr/bin/env python3
"""验证资料日期 YYYY/MM/DD 三段同一行渲染（修复：CSS 特异性覆盖导致三段各占一行）。

背景：.lib-up-seg{width:44px}(0,1,0) 被 .lib-upload-table .lib-upload-input
{width:100%;min-width:110px}(0,2,0) 压制，年/月/日各被撑到 ≥110px，日期列
换行成三行。修复：同特异性后置覆盖 + flex nowrap。断言：三段 y 坐标一致
（±2px 亚像素容差，日历按钮与输入框高度不同属正常）。
"""
import json, urllib.request, re, sys, io
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path("/home/rhett/tech-boundary-db")
env = (REPO/".env").read_text()
u = re.search(r"TECHDB_INITIAL_ADMIN_USERNAME=(.*)", env).group(1).strip()
p = re.search(r"TECHDB_INITIAL_ADMIN_PASSWORD=(.*)", env).group(1).strip()
tok = json.load(urllib.request.urlopen(urllib.request.Request(
    "http://localhost:8080/api/auth/login", method="POST",
    data=json.dumps({"username":u,"password":p}).encode(),
    headers={"Content-Type":"application/json"})))["access_token"]

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width":1440,"height":900})
    pg.add_init_script(f"localStorage.setItem('auth_token','{tok}')")
    pg.goto("http://localhost:8080/#library?section=industry")
    pg.wait_for_timeout(2000)
    pg.click("text=上传资料")
    pg.wait_for_timeout(800)
    assert pg.evaluate("!!document.getElementById('upInput')"), "上传区未展开"
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title="数据"
    ws.append(["标题","日期","链接","正文"]); ws.append(["验证行","2026-09-20","https://t/1","内容"])
    buf = io.BytesIO(); wb.save(buf)
    pg.set_input_files("#upInput", files=[{"name":"datecheck.xlsx",
        "mimeType":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "buffer":buf.getvalue()}])
    pg.wait_for_timeout(2500)
    boxes = pg.eval_on_selector_all(".lib-up-datebox", """els => els.map(e => {
        const segs = [...e.querySelectorAll('.lib-up-seg')].map(s => {
            const r = s.getBoundingClientRect();
            return {ph: s.placeholder, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
        });
        const cal = e.querySelector('.lib-up-cal');
        const cr = cal ? cal.getBoundingClientRect() : null;
        return {segs, calY: cr ? Math.round(cr.y) : null, boxH: Math.round(e.getBoundingClientRect().height)};
    })""")
    print(json.dumps(boxes, ensure_ascii=False))
    ok = bool(boxes)
    for bx in boxes:
        ys = {s["y"] for s in bx["segs"]}          # 三段输入框必须严格同行
        if len(ys) != 1: ok = False; print(f"FAIL: 年/月/日不同行 y={sorted(ys)}")
        if bx["calY"] is not None and abs(bx["calY"] - next(iter(ys))) > 2:
            ok = False; print(f"FAIL: 日历按钮换行 y={bx['calY']} vs {next(iter(ys))}")
    print("RESULT:", "PASS 年/月/日同一行" if ok else "FAIL")
    pg.screenshot(path="/tmp/e2e-shots/date_row_fixed.png")
    b.close()
    sys.exit(0 if ok else 1)
