FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
# 离线依赖：若 backend/wheels/ 存在，先从本地 wheel 安装（服务器可能碰不到 PyPI）。
# wheels 内含 pypdf/python-docx/openpyxl 及其传递依赖（lxml/et_xmlfile/typing_extensions）。
COPY backend/wheels /app/wheels
# 第一步用 --no-deps 装 wheels（避免缺传递依赖 lxml 时报错），
# 第二步用 requirements 解析完整依赖树；find-links 让离线环境从 wheels 补 lxml。
RUN if [ -n "$(ls -A /app/wheels 2>/dev/null)" ]; then \
        pip install --no-cache-dir --no-deps /app/wheels/*.whl; \
    fi \
    && pip install --no-cache-dir --find-links=/app/wheels -r /app/requirements.txt

COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/tests /app/tests
COPY data /app/data

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
