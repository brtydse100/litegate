# Stage 1: build the React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build

# Stage 2: runtime - nginx (frontend) + Python (backend) via supervisord
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor && apt-get clean

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

COPY --from=frontend-build /app/dist /usr/share/nginx/html

COPY deploy/docker-compose/nginx.conf /etc/nginx/sites-enabled/default
COPY deploy/docker-compose/supervisord.conf /etc/supervisor/conf.d/litegate.conf

EXPOSE 80

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/litegate.conf"]