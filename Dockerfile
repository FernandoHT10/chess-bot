FROM python:3.11-slim

# Instalar librerías del sistema necesarias para cairosvg
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear y usar el directorio de la app
WORKDIR /app
COPY . /app

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Comando para ejecutar tu bot
CMD ["python", "telegram_stockfish_bot3.py"]
