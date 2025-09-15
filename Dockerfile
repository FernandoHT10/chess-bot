# Imagen base de Python
FROM python:3.11-slim

# Instalar dependencias del sistema para cairosvg
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiar todos los archivos del proyecto
COPY . /app

# Dar permisos de ejecución al binario Stockfish
RUN chmod +x /app/stockfish/stockfish-ubuntu-x86-64

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Comando por defecto al iniciar el contenedor
CMD ["python", "telegram_stockfish_bot3.py"]
