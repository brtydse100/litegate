# Stage 1: build the React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build

# Stage 2: runtime - nginx (frontend) + Python (backend) via supervisord
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor \
    && groupadd --system --gid 10001 litegate \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin litegate \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app/ ./app/
RUN mkdir -p /app/backend/data \
    && chown -R litegate:litegate /app/backend/data

COPY --from=frontend-build /app/dist /usr/share/nginx/html

COPY deploy/docker-compose/nginx.conf /etc/nginx/nginx.conf
COPY deploy/docker-compose/supervisord.conf /etc/supervisor/conf.d/litegate.conf

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"]

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/litegate.conf"]
