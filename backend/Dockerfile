FROM python:3.11-slim

# Native legacy Office conversion and audio/video support; no uploaded code is run.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 libgomp1 ffmpeg libreoffice-core libreoffice-writer \
    libreoffice-calc libreoffice-impress fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

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
    && pip install --no-cache-dir torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --find-links=/app/wheels -r /app/requirements.txt

COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/tests /app/tests
COPY data /app/data

ENV PYTHONPATH=/app ORT_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_TELEMETRY=1

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

