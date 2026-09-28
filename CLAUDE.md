# Búho

Bot personal de Telegram, un solo usuario, que corre 24/7 en una Raspberry Pi 3 (1 GB de RAM,
Raspberry Pi OS Lite de 64 bits). Avisa del clima de Hermosillo y de noticias de la Unison, de
Hermosillo y de videojuegos.

- **Alcance y requisitos:** [docs/ESPECIFICACION.md](docs/ESPECIFICACION.md). Su sección 1 no se reabre.
- **Estado, decisiones y siguiente paso:** [PROGRESS.md](PROGRESS.md). Léelo antes de hacer nada.

## Comandos (PowerShell, en la raíz del repo)

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt   # dependencias (fijadas)
.venv\Scripts\python -m pytest                                  # pruebas, sin red
.venv\Scripts\python -m ruff format .; .venv\Scripts\python -m ruff check .
Copy-Item config.example.yaml config.yaml                       # primera vez
.venv\Scripts\python -m buho check-sources                      # valida las fuentes reales
$env:BUHO_DRY_RUN=1; .venv\Scripts\python -m buho run           # simulación: imprime en vez de enviar
```

## Convenciones

- En español: textos del bot, documentación, comentarios y commits. En inglés: identificadores.
- En la BD, fechas ISO en UTC; `America/Hermosillo` solo al mostrar.
- Reloj inyectable: la lógica recibe `now`; `datetime.now()` solo en los bordes.
- Pruebas sin red: fixtures recortadas de respuestas reales en `tests/fixtures/` y `httpx.MockTransport`.
- El contenido de las fuentes no es confiable: se escapa siempre (HTML de Telegram y Jinja).
- Nada de dependencias pesadas ni que compilen en ARM. Ruff apunta a Python 3.11.
- El token nunca va a los logs (el logger de httpx va en WARNING).
- Trabajo por fases. Al cerrar cada una: ruff + pytest, commit, actualizar PROGRESS.md y
  detenerse a revisión. No empezar la siguiente sin el OK del usuario.
- Preguntar antes de: instalar fuera del venv, ejecutar comandos en la Pi, ampliar el alcance o
  tomar decisiones difíciles de revertir. Nunca pedir secretos en el chat: decir en qué archivo van.
- Despliegue: hacer push a `origin/main` está autorizado (repo público en GitHub). El usuario
  actualiza la Pi con `deploy/update.sh` (`git pull` + reinstalar). No hay SSH de la PC a la Pi:
  los comandos en la Pi los corre el usuario siguiendo el README.
