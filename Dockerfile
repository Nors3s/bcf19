# Usa una imagen base de Ubuntu 22.04, que tiene un sistema actualizado
FROM ubuntu:22.04

# Actualiza el sistema e instala las dependencias necesarias para Playwright y tu bot
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    wget \
    unzip \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxi6 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Crea un enlace simbólico para que "python" apunte a "python3"
RUN ln -s /usr/bin/python3 /usr/bin/python

# Establece el directorio de trabajo en /app
WORKDIR /app

# Copia todo el contenido de tu repositorio al contenedor
COPY . /app

# Actualiza pip e instala las dependencias de Python
RUN pip3 install --upgrade pip && pip3 install -r requirements.txt

# Instala los navegadores necesarios para Playwright junto con sus dependencias
RUN python3 -m playwright install --with-deps

# Define el comando para arrancar tu bot
CMD ["python3", "bot_burgoscf.py"]
