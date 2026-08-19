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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app/ ./app/
RUN mkdir -p /app/backend/data

COPY --from=frontend-build /app/dist /usr/share/nginx/html

COPY deploy/docker-compose/nginx.conf /etc/nginx/sites-enabled/default
COPY deploy/docker-compose/supervisord.conf /etc/supervisor/conf.d/litegate.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1/api/health', timeout=3)"]

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/litegate.conf"]
