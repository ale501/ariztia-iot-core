FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar archivos del proyecto
COPY . .

EXPOSE 5001 8000

# Por defecto arranca el servicio de monitoreo
CMD ["python", "app_ariztia.py"]
