# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Configuración de variables de entorno para ejecución óptima de Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Instalar herramientas básicas del sistema (curl para healthchecks, gcc para extensiones nativas si aplican)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias primero para optimizar la caché de capas
COPY requirements.txt .

# Actualizar pip e instalar requerimientos
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del conector
COPY . .

# Puerto por defecto del servidor MCP y OAuth Server (definido en settings: 8005)
EXPOSE 8005

# Comando de inicio del servidor
CMD ["python", "src/main.py"]
