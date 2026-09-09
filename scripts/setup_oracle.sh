#!/usr/bin/env bash
# ==============================================================================
# Script de Configuración Inicial en Oracle Cloud VM (Ubuntu / Debian / Oracle Linux)
# Ejecutar una sola vez en la instancia de Oracle Cloud.
# ==============================================================================

set -e

CURRENT_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"
CURRENT_DIR="$SCRIPT_DIR"
PYTHON_BIN="$CURRENT_DIR/.venv/bin/python"

echo "=========================================================="
echo "🛠️  Configurando IABacktesterTrading en Oracle Cloud VM"
echo "Usuario actual: $CURRENT_USER"
echo "Directorio de la app: $CURRENT_DIR"
echo "=========================================================="

# 1. Actualizar paquetes del sistema
echo "📦 Actualizando paquetes del sistema..."
if command -v apt-get > /dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv git curl build-essential iptables-persistent
elif command -v dnf > /dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip git curl gcc gcc-c++
fi

# 1.1 Configurar Swap automático si la máquina tiene poca RAM (evita que PyTorch agote la memoria)
TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
SWAP_EXISTS=$(free -m | awk '/^Swap:/{print $2}')
if [ "${SWAP_EXISTS:-0}" -eq 0 ] && [ "${TOTAL_RAM_MB:-0}" -lt 3500 ]; then
    echo "💾 Máquina con poca RAM ($TOTAL_RAM_MB MB). Creando swap de 2GB..."
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab || true
fi

# 2. Configurar entorno virtual Python
echo "🐍 Configurando entorno virtual Python..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
echo "📥 Instalando dependencias de Python..."
if ! command -v nvidia-smi > /dev/null 2>&1; then
    echo "💡 Detectada CPU: instalando PyTorch versión CPU (ahorra 2.5 GB y acelera el despliegue)..."
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu || true
fi

if [ -f "requirements.txt" ]; then
    echo "📥 Instalando $CURRENT_DIR/requirements.txt..."
    pip install -r requirements.txt
else
    echo "❌ Error: No se encontró requirements.txt en $CURRENT_DIR"
    exit 1
fi

# 3. Crear o actualizar archivo .env
if [ -n "$TG_TOKEN" ]; then
    echo "🔐 Configurando variables de entorno (.env)..."
    cat <<EOF > .env
TELEGRAM_BOT_TOKEN=$TG_TOKEN
TELEGRAM_CHAT_ID=$TG_CHAT
EOF
elif [ ! -f ".env" ]; then
    echo "⚠️ Creando plantilla .env (recuerda editar con tus tokens de Telegram si no usas secrets):"
    cat <<EOF > .env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
fi

# 4. Crear el servicio Systemd para ejecución en segundo plano y arranque automático
echo "⚙️ Configurando servicio Systemd (/etc/systemd/system/backtester.service)..."
sudo bash -c "cat <<EOF > /etc/systemd/system/backtester.service
[Unit]
Description=IA Backtester Trading Web Server & Bot
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
ExecStart=$PYTHON_BIN web/server.py
Restart=always
RestartSec=5
EnvironmentFile=-$CURRENT_DIR/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

# 5. Permitir que el usuario reinicie el servicio sin pedir contraseña en sudo (crucial para GitHub Actions)
echo "🔑 Configurando permisos sudo sin contraseña para el servicio..."
SUDOERS_FILE="/etc/sudoers.d/backtester-deploy"
sudo bash -c "echo '$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart backtester, /usr/bin/systemctl is-active backtester, /usr/bin/systemctl status backtester' > $SUDOERS_FILE"
sudo chmod 0440 "$SUDOERS_FILE"

# 6. Configurar Firewall local del SO (Oracle bloquea puertos con iptables por defecto)
echo "🛡️ Abriendo puerto 8000 en el firewall local (iptables / ufw)..."
if command -v ufw > /dev/null 2>&1; then
    sudo ufw allow 8000/tcp || true
    sudo ufw allow 80/tcp || true
fi

# Regla directa en iptables (indispensable en imágenes de Oracle Cloud)
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT || true

if command -v netfilter-persistent > /dev/null 2>&1; then
    sudo netfilter-persistent save || true
fi

# 7. Iniciar y habilitar el servicio
echo "🚀 Iniciando servicio backtester..."
sudo systemctl daemon-reload
sudo systemctl enable backtester
sudo systemctl restart backtester

sleep 2
if sudo systemctl is-active --quiet backtester; then
    echo "=========================================================="
    echo "✅ ¡Configuración completada con éxito!"
    echo "El servidor está corriendo en el puerto 8000."
    echo "Para ver logs en vivo: sudo journalctl -u backtester -f"
    echo "=========================================================="
else
    echo "⚠️ El servicio se inició pero hubo un problema. Revisa los logs con:"
    echo "sudo journalctl -u backtester -n 50 --no-pager"
fi
