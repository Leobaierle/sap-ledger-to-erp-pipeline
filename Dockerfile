# Conversor ACME (Razão SAP -> importação ERP): frontend React/shadcn + API Flask
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CONTABIL_WEB=/app/web/dist \
    CONTABIL_TRABALHOS=/tmp/contabil/trabalhos \
    CONTABIL_FALHAS=/tmp/contabil/falhas
WORKDIR /app
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY app/app.py app/conversor.py app/tabelas.py app/xlsx_rapido.py ./app/
COPY --from=web /web/dist ./web/dist
RUN useradd --uid 10001 --no-create-home contabil
USER 10001
EXPOSE 8080
# 1 processo (as conversões usam ~700 MB cada; o app limita a 2 simultâneas), threads para o resto
CMD ["gunicorn", "--chdir", "/app/app", "--workers", "1", "--threads", "8", "--timeout", "300", \
     "--bind", "0.0.0.0:8080", "--access-logfile", "-", "app:app"]
