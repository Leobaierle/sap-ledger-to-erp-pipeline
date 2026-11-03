# Portal do robô diário da ACME: frontend React (portal/web) + API Flask (portal/api).
# Contexto = raiz do repositório (usa app/tabelas.py e app/conversor.py do conversor): docker build -f portal/Dockerfile .
FROM node:22-alpine AS web
WORKDIR /web
COPY portal/web/package.json portal/web/package-lock.json ./
RUN npm ci
COPY portal/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORTAL_ARQUIVOS=/dados/arquivos
WORKDIR /app
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY app/conversor.py app/tabelas.py app/xlsx_rapido.py app/arquivos.py ./app/
COPY portal/api/app.py ./portal/api/
# importação avulsa (CronJob contabil-fila): python /app/sap/importar_fila.py
COPY sap/lotes.py sap/erp.py sap/importar_fila.py ./sap/
COPY --from=web /web/dist ./portal/web/dist
RUN useradd --uid 10001 --no-create-home contabil && mkdir -p /dados/arquivos && chown 10001 /dados/arquivos
USER 10001
EXPOSE 8080
CMD ["gunicorn", "--chdir", "/app/portal/api", "--workers", "1", "--threads", "8", "--timeout", "120", \
     "--bind", "0.0.0.0:8080", "--access-logfile", "-", "app:app"]
