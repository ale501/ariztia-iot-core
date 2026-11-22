FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema necesarias para OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar archivos del proyecto
COPY . .

EXPOSE 5001 5000 8000

# Por defecto arranca el servicio de monitoreo
CMD ["python", "app_ariztia.py"]
