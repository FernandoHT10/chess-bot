# Imagen base de Python ligera
FROM python:3.11-slim

# Instalar librerías del sistema necesarias para cairosvg
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear carpeta de la app
WORKDIR /app

# Copiar requirements primero (cachea las dependencias Python)
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo tu código al contenedor
COPY . .

# Comando para arrancar tu bot
CMD ["python", "telegram_stockfish_bot3.py"]
