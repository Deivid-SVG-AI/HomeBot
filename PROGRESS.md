# Progreso de Búho

| Fase | Estado |
|---|---|
| 0 — Base y validación de fuentes | ✅ Terminada el 2026-09-27; esperando revisión |
| 1 — Clima y bot mínimo en la Pi | ⏳ Siguiente, cuando el usuario dé el OK |
| 2 — Noticias | — |
| 3 — Dashboard | — |
| 4 — IA opcional | — |

## Fase 0 — qué se hizo

- Especificación en `docs/ESPECIFICACION.md`; `CLAUDE.md`, `.gitignore` y dependencias fijadas.
- `buho/config.py`: modelos pydantic de `config.yaml`, con errores en español que dicen el campo y
  la causa. Valida tipos de fuente, horas "HH:MM", zona horaria, ids repetidos y referencias.
- `buho/db.py`: esquema v1 (ver abajo), WAL, `busy_timeout`, migraciones con `PRAGMA user_version`
  y FTS5 (si no existe, `/buscar` usará LIKE).
- `buho/sources.py`: cliente HTTP (User-Agent, timeout por fuente, GET condicional, máximo 3
  descargas a la vez) y lectores `rss`, `gnews`, `steam` y `unison`.
- `python -m buho check-sources`: 9 de 9 fuentes OK el 2026-09-27.
- Fixtures reales recortadas en `tests/fixtures/` (3 a 10 KB cada una). `open_meteo.json` es para la
  Fase 1.

## Cómo probarlo

```powershell
.venv\Scripts\python -m pytest                   # 27 pruebas, sin red
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m buho check-sources       # necesita config.yaml (copia del ejemplo)
```

## Decisiones vigentes

### Plan aprobado (2026-09-27)

- **Sin JobQueue ni APScheduler.** Un loop asyncio despierta cada minuto y le pregunta a una función
  pura `due(now, state)` qué toca: clima, resúmenes, revisión horaria del clima, fuentes vencidas y
  retención. El envío tardío (hasta las 10:00), "nunca dos veces" y los reinicios salen de esa regla.
- **Sin `pydantic-settings`.** En la Pi, systemd carga `.env` con `EnvironmentFile=`; en la PC, un
  lector de 5 líneas (Fase 1).
- **Sin `respx` ni `pytest-asyncio`.** Se usan `httpx.MockTransport` y `asyncio.run()`.
- **`difflib` en vez de `rapidfuzz`** para agrupar, con prefiltro `quick_ratio()`.
- **HTMX solo si hace falta** en la Fase 3; los filtros funcionan con formularios GET.
- **`buho/queries.py`** en lugar de `services/queries.py`.
- **Grupos:** todo item pertenece a un grupo (aunque sea de uno), y el estado de notificado o
  resumido vive en `clusters`. Los "medios distintos" se cuentan con `COUNT(DISTINCT outlet)`.
- **Una categoría por item.** Si menciona a la Unison va a `unison`, con el nivel más alto entre
  las reglas de ambas categorías.
- **Semilla por fuente:** la primera descarga exitosa de cada fuente se marca como vista sin
  notificar (`source_state.seeded_at`). Agregar una fuente después no inunda el chat.
- **Tras un apagón, sin modo especial:** las 🔴 de más de 6 h bajan al resumen y el excedente de la
  hora se agrupa.
- **Primero se envía y luego se registra.** Un corte de luz entre ambos pasos podría repetir un
  mensaje; se prefiere eso a perder una 🔴.

### Esquema de la BD (v1, `buho/db.py`)

`items`, `clusters`, `source_state`, `sent_messages`, `feedback` y `app_state` (clave/valor para
`quiet_until`, `weather_sent:<fecha>`, `digest_sent:<fecha hora>`, `cooldown:<cat>:<regla>`,
`weather_alert:<tipo>`). `UNIQUE(source, ext_id)`, donde `ext_id` es el guid o, si no hay, el link.
`feedback` copia el título y las reglas para sobrevivir a la retención.

### Fuentes (verificadas el 2026-09-27)

- **El Imparcial:** existen feeds por sección y se usan en lugar del general.
  - `/category/son/hermosillo/` trae 22 items (unos 1.5 días, 125 KB).
  - `/category/son/sonora/` trae 38 items: 18 de Sonora, 12 de Hermosillo, 4 de `/mexico/` y otros.
    Solo trae 13 de las 22 notas de Hermosillo, por eso son dos fuentes.
  - `/category/son/` devuelve 0 items.
  - El feed general trae 100 items que cubren apenas unas 9 h, con solo 10 de Sonora, y pesa 680 KB.
  - `If-Modified-Since` devuelve 304; con `If-None-Match` sola no. Se mandan las dos cabeceras.
  - Las menciones de la Unison fuera de `/son/` las cubre `gnews_unison`.
- **Unison: listado HTML `/noticias-anteriores/`**, leído con regex.
  - Por qué no WordPress:
    - En la API REST, los posts recientes son pruebas ("Murales prueba 3"); la categoría
      `noticias` no se actualiza desde agosto de 2024 y `avisos` desde febrero de 2025.
    - No hay tipos de post personalizados.
    - La API de `direcciondecomunicacion.unison.mx` funciona, pero su último post es del 12 de
      septiembre de 2025.
  - Las noticias reales están fuera de WordPress, en `/nota/?idnoti=N`. El listado trae unas 104
    notas del mes, con título y fecha, pero sin hora.
  - El id externo es `idnoti`. `published_at` es la medianoche local de esa fecha.
  - La portada pesa lo mismo (338 KB) y solo trae 5 notas, así que no conviene.
  - No hay ETag ni Last-Modified: son unos 340 KB cada 15 min, unos 33 MB al día.
  - Si desaparece el bloque `noti-anteriores`, el lector falla con un mensaje claro y la salud de
    fuentes avisa. Respaldo: `gnews_unison`.
- **Google News:** el medio viene en `<source>` (feedparser lo da en `entry.source.title`) y el
  título termina en " - Medio"; ambas cosas se confirmaron. Se guarda el medio en `outlet` y se
  quita el sufijo. No tiene validadores HTTP.
- **Steam:** `feedname == "steam_community_announcements"` separa lo oficial de PC Gamer, PCGamesN
  y PlayGround.ru. Ascendance (4829700) responde bien, con 0 noticias por ahora.
- **Open-Meteo:** todas las variables de la sección 2 existen con esos nombres; fixture guardada.

## Pendiente

- **Remoto:** `origin` (github.com/Deivid-SVG-AI/HomeBot) es privado: la API de GitHub responde
  404 sin autenticación. No se ha hecho push; se pregunta antes de cada push.
- **Pregunta abierta:** el proyecto está en OneDrive, que sincroniza `.venv` y la BD (riesgo de
  bloqueos con WAL). Conviene moverlo o excluir esas carpetas.
- **Fase 1:** antes de escribir los scripts de despliegue, preguntar cómo llega el código a la Pi
  (GitHub o SSH) y si hay SSH con llave. Confirmar el Python de la Pi (se espera 3.13 en Trixie).
- **Fase 2, notas para afinar reglas:**
  - `elimparcial_son` también trae notas de `/mexico/` y de otras ciudades; aplicarles la regla
    de `/son/sonora/` (entran solo si mencionan Hermosillo o la Unison, o si activan una regla roja).
  - Google News trae desmentidos ("Aclara SEC Sonora que es falsa la suspensión de clases"): una
    regla roja por palabra clave los dispararía. Revisar con `preview-digest`.
  - Los `summary` vienen con HTML (El Imparcial, PS LATAM) o BBCode (Steam); se limpian en `news.py`.
  - Los items de la Unison solo tienen fecha: para "hace X min" usar `seen_at`.
