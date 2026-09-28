#!/usr/bin/env bash
# Instala o repara Búho en la Raspberry Pi. Es idempotente: correrlo otra vez no rompe nada.
# Uso, desde el repo clonado en /opt/buho:   sudo ./deploy/install_pi.sh
set -euo pipefail

APP_DIR=/opt/buho

if [[ $EUID -ne 0 ]]; then
    echo "Ejecútalo con sudo: sudo ./deploy/install_pi.sh" >&2
    exit 1
fi
if [[ "$(cd "$(dirname "$0")/.." && pwd)" != "$APP_DIR" ]]; then
    echo "El repo debe estar clonado en $APP_DIR (ver README)." >&2
    exit 1
fi
cd "$APP_DIR"
OWNER=$(stat -c %U "$APP_DIR")  # quien clonó el repo: hace git pull y es dueño del venv

echo "==> Paquetes del sistema"
missing=()
for pkg in python3-venv sqlite3; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
    apt-get update -q
    apt-get install -y -q "${missing[@]}"
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || {
    echo "Búho necesita Python 3.11 o superior; esta Pi tiene $(python3 --version)." >&2
    exit 1
}

echo "==> Usuario de servicio 'buho'"
id -u buho >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin buho

echo "==> Entorno virtual y dependencias"
[[ -x .venv/bin/python ]] || sudo -H -u "$OWNER" python3 -m venv .venv
sudo -H -u "$OWNER" .venv/bin/pip install -q -r requirements.txt

echo "==> Configuración"
[[ -f config.yaml ]] || sudo -u "$OWNER" cp config.example.yaml config.yaml
[[ -f .env ]] || cp .env.example .env
chown root:root .env
chmod 600 .env

echo "==> journald: máximo 50 MB de logs, para cuidar la microSD"
if [[ ! -f /etc/systemd/journald.conf.d/buho.conf ]]; then
    install -d /etc/systemd/journald.conf.d
    printf '[Journal]\nSystemMaxUse=50M\n' >/etc/systemd/journald.conf.d/buho.conf
    systemctl restart systemd-journald
fi

echo "==> Esperar a tener la hora sincronizada al arrancar"
systemctl enable --quiet systemd-time-wait-sync.service

echo "==> Servicio buho-bot"
install -m 644 deploy/buho-bot.service /etc/systemd/system/buho-bot.service
systemctl daemon-reload
systemctl enable --quiet buho-bot.service

if ! grep -qw memory /sys/fs/cgroup/cgroup.controllers 2>/dev/null; then
    echo "AVISO: el kernel tiene apagado el control de memoria, así que MemoryMax=300M no se aplica." >&2
    echo "       Para activarlo, agrega 'cgroup_enable=memory' al final de la única línea de" >&2
    echo "       /boot/firmware/cmdline.txt y reinicia la Pi. Búho funciona igual sin esto." >&2
fi

if grep -Eq '^TELEGRAM_BOT_TOKEN=.+' .env; then
    systemctl restart buho-bot.service
    echo "Listo: Búho (re)iniciado. Logs en vivo: journalctl -u buho-bot -f"
else
    echo "Listo. Falta el token: edita el archivo con 'sudo nano $APP_DIR/.env'"
    echo "y luego arranca Búho con 'sudo systemctl restart buho-bot'."
fi
