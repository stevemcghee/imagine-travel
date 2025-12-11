# Stage 1: Build Frontend
FROM node:18-alpine as frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

COPY frontend/ .
RUN npm run build

# Stage 2: Setup Backend
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy built frontend assets from builder stage
COPY --from=frontend-builder /app/frontend/dist ./static

# Expose port (Cloud Run sets PORT env var, defaulting to 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
