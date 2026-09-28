# 🦉 Búho

Bot personal de Telegram que corre 24/7 en una Raspberry Pi 3. Cada mañana manda el clima de
Hermosillo y responde comandos como `/clima` y `/estado`. Las noticias (Unison, Hermosillo y
videojuegos) llegan en la Fase 2.

Solo atiende a un chat: el tuyo. Cualquier otro se ignora y queda registrado en el log.

---

## 1. Preparar la Raspberry Pi

1. En tu PC, instala **Raspberry Pi Imager** (raspberrypi.com/software) y abre la app.
2. Elige:
   - **Dispositivo:** Raspberry Pi 3.
   - **Sistema:** *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)**.
   - **Almacenamiento:** tu microSD.
3. Cuando Imager ofrezca personalizar el sistema, llena:
   - **Nombre del equipo:** `buho`.
   - **Usuario y contraseña:** los tuyos. En esta guía, `tu_usuario`.
   - **Wi-Fi:** tu red y el país `MX`. La Pi 3 solo ve redes de 2.4 GHz.
   - **Zona horaria:** `America/Hermosillo`.
   - **SSH:** actívalo con autenticación por contraseña.
4. Graba la microSD, ponla en la Pi y conéctala a la corriente. Dale un par de minutos.
5. Desde la PC (PowerShell):

   ```powershell
   ssh tu_usuario@buho.local
   ```

   Si `buho.local` no responde, busca la IP de la Pi en tu módem y usa `ssh tu_usuario@<IP>`.
6. Ya dentro de la Pi, actualízala:

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   ```

> Usa una fuente de poder de 5 V y 2.5 A. Con una más débil, `/estado` mostrará avisos de bajo
> voltaje y la microSD puede corromperse.

## 2. Crear el bot en Telegram

1. En Telegram, abre **@BotFather** y manda `/newbot`.
2. Dale un nombre (por ejemplo, `Búho`) y un usuario que termine en `bot`.
3. BotFather te da un **token** parecido a `123456789:AA...`. Guárdalo para el paso 3.4.
   **Nunca lo pegues en un chat ni lo subas a git:** va solo en el archivo `.env` de la Pi.

## 3. Instalar Búho en la Pi

El repo es privado, así que la Pi necesita una **llave de despliegue**: una llave SSH que solo
puede leer este repo.

1. **Crea la llave en la Pi:**

   ```bash
   ssh-keygen -t ed25519 -C "buho-pi" -f ~/.ssh/id_ed25519 -N ""
   cat ~/.ssh/id_ed25519.pub
   ```

2. **Regístrala en GitHub.** En el repo, ve a *Settings → Deploy keys → Add deploy key*, pega la
   línea que imprimió `cat` y deja **sin marcar** *Allow write access*.

3. **Clona e instala:**

   ```bash
   sudo apt install -y git
   sudo mkdir -p /opt/buho && sudo chown "$USER": /opt/buho
   git clone git@github.com:Deivid-SVG-AI/HomeBot.git /opt/buho
   cd /opt/buho
   sudo ./deploy/install_pi.sh
   ```

   La primera vez que conectes con GitHub, SSH preguntará si confías en el servidor: responde
   `yes`.

   El script `install_pi.sh` se puede correr las veces que quieras sin romper nada. Hace esto:
   - instala `python3-venv` y `sqlite3` si faltan;
   - crea el usuario de servicio `buho`;
   - crea el entorno virtual en `/opt/buho/.venv` e instala las dependencias;
   - copia `config.yaml` y `.env` desde los ejemplos si no existen;
   - deja `.env` con permisos 600 y como dueño a root;
   - limita journald y habilita la espera de hora sincronizada (ver la sección 7);
   - instala y habilita el servicio `buho-bot`.

4. **Pon el token en `.env`:**

   ```bash
   sudo nano /opt/buho/.env        # pega el token en TELEGRAM_BOT_TOKEN=
   sudo systemctl restart buho-bot
   ```

5. **Obtén tu chat id.** En Telegram, abre tu bot y manda `/start`. Como `TELEGRAM_CHAT_ID` sigue
   vacío, Búho está en *modo configuración* y te responde con tu chat id.

6. **Guarda el chat id y reinicia:**

   ```bash
   sudo nano /opt/buho/.env        # pega el número en TELEGRAM_CHAT_ID=
   sudo systemctl restart buho-bot
   ```

7. **Comprueba que funciona.** Manda `/start` otra vez: ahora sí verás el menú de comandos. Prueba
   `/clima`, `/clima manana` y `/estado`.

Otras pruebas desde la Pi:

```bash
cd /opt/buho
sudo .venv/bin/python -m buho send-test      # manda un mensaje de prueba
.venv/bin/python -m buho preview-weather     # imprime el clima de hoy sin enviarlo
.venv/bin/python -m buho check-sources       # revisa las fuentes de noticias
```

El clima llega solo a las **06:00 de lunes a viernes** y a las **09:00 sábado y domingo**. Si la Pi
estaba apagada a esa hora y arranca antes de las 10:00, lo manda en cuanto enciende. Nunca lo manda
dos veces el mismo día.

## 4. Ver los logs

```bash
journalctl -u buho-bot -f                 # en vivo (Ctrl+C para salir)
journalctl -u buho-bot --since today      # lo de hoy
journalctl -u buho-bot -n 100             # las últimas 100 líneas
sudo systemctl status buho-bot            # ¿está corriendo?
```

## 5. Actualizar

Cuando haya cambios en GitHub, en la Pi:

```bash
/opt/buho/deploy/update.sh
```

`update.sh` hace `git pull` y vuelve a correr `install_pi.sh`, que instala dependencias nuevas y
reinicia el servicio. Tu `config.yaml` y tu `.env` no se tocan.

## 6. Respaldar la base de datos

La base de datos vive en `/var/lib/buho/buho.db`. El respaldo es seguro aunque Búho esté corriendo:

```bash
sudo sqlite3 /var/lib/buho/buho.db ".backup '$HOME/buho-$(date +%F).db'"
sudo chown "$USER": "$HOME"/buho-*.db
```

Para copiar el respaldo a tu PC (PowerShell):

```powershell
scp tu_usuario@buho.local:buho-*.db .
```

Para restaurar un respaldo:

```bash
sudo systemctl stop buho-bot
sudo cp ~/buho-AAAA-MM-DD.db /var/lib/buho/buho.db
sudo rm -f /var/lib/buho/buho.db-wal /var/lib/buho/buho.db-shm
sudo chown buho:buho /var/lib/buho/buho.db
sudo systemctl start buho-bot
```

## 7. Detalles de la Pi (ya los configura `install_pi.sh`)

- **Hora:** la Pi no tiene reloj propio y al encender cree que es la última hora que recuerda.
  - `install_pi.sh` habilita `systemd-time-wait-sync`, para que Búho arranque solo cuando la hora
    ya está sincronizada por internet.
  - Si lo quieres hacer a mano: `sudo systemctl enable systemd-time-wait-sync`.
  - Para revisar la hora: `timedatectl`.
- **Red:** si la Pi arranca sin Wi-Fi, Búho espera a que vuelva. Si la red se cae con el bot
  corriendo, se reconecta solo. Si el proceso llega a fallar, systemd lo reinicia a los 30 s.
- **Logs y microSD:** journald queda limitado a 50 MB en
  `/etc/systemd/journald.conf.d/buho.conf` (`SystemMaxUse=50M`). Búho no escribe archivos de log
  propios.
- **Memoria:** el servicio tiene un techo de 300 MB (`MemoryMax`). Si `install_pi.sh` avisa que el
  kernel tiene apagado el control de memoria, el techo no se aplica. Para activarlo, agrega
  `cgroup_enable=memory` al final de la línea de `/boot/firmware/cmdline.txt` y reinicia.
- **Seguridad:**
  - El servicio corre con el usuario `buho`, sin privilegios.
  - Solo puede escribir en `/var/lib/buho` (`ProtectSystem=strict`).
  - `.env` solo lo puede leer root; systemd le pasa las variables al servicio.

## 8. Desarrollo en la PC

Los comandos de desarrollo (pruebas, lint, modo simulación) están en [CLAUDE.md](CLAUDE.md). En
resumen:

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
$env:BUHO_DRY_RUN=1; .venv\Scripts\python -m buho run   # imprime en vez de enviar
```

La especificación completa está en [docs/ESPECIFICACION.md](docs/ESPECIFICACION.md), y el avance
en [PROGRESS.md](PROGRESS.md).

---

Datos del clima: [Open-Meteo.com](https://open-meteo.com/), bajo licencia
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
