# Búho — Especificación para Claude Code

> Bot personal de notificaciones que corre 24/7 en una Raspberry Pi 3 y me avisa por Telegram de cuatro cosas: el clima de Hermosillo, noticias de la Universidad de Sonora (Unison), noticias de Hermosillo y noticias de videojuegos. Lee este documento completo antes de empezar.

---

## 0. Cómo trabajar conmigo

1. **Primero el plan.** Propón:
   - estructura de carpetas;
   - esquema de la base de datos;
   - dependencias con versión;
   - cómo resolverás lo marcado *por verificar*.

   No escribas código hasta que yo lo apruebe.
2. **Contexto que sobreviva entre sesiones.** Mi plan de Claude tiene límites de uso y esto tomará varias sesiones.
   - Mueve este archivo a `docs/ESPECIFICACION.md`.
   - Crea un `CLAUDE.md` breve con:
     - el propósito del proyecto;
     - los comandos (venv, pruebas, modo simulación, validar fuentes);
     - las convenciones;
     - referencias a `docs/ESPECIFICACION.md` y `PROGRESS.md`.
   - Una sesión nueva debe poder continuar leyendo solo esos archivos.
3. **Trabaja por fases** (sección 11). Al cerrar cada una:
   - corre `ruff` y `pytest`;
   - haz commit;
   - actualiza `PROGRESS.md` con lo hecho, lo pendiente, las decisiones y cómo probarlo;
   - detente para que yo revise.

   No empieces la siguiente fase sin mi OK.
4. **No inventes.** URLs, endpoints, campos y selectores se verifican con peticiones reales. Si una fuente falla o cambió, repórtamelo con alternativas. Dímelo también, con una alternativa, si algo de este documento choca con la realidad técnica.
5. **Pregúntame antes de:**
   - instalar algo fuera del venv del proyecto;
   - hacer push a un remoto;
   - ejecutar comandos en la Pi;
   - ampliar el alcance;
   - tomar decisiones difíciles de revertir.
6. **Entorno.** Desarrollas en mi PC y el destino es la Pi. Antes de escribir los scripts de despliegue, pregúntame:
   - cómo paso el código a la Pi (repo privado en GitHub o copia por SSH);
   - si tengo SSH con llave configurado.

   Si lo tengo, puedes desplegar y revisar logs por SSH, confirmando conmigo los comandos que modifiquen la Pi.
7. **Idioma.**
   - En español: textos del bot, README, documentación, comentarios y mensajes de commit.
   - En inglés: identificadores de código.

---

## 1. Decisiones ya tomadas (no las reabras)

- **Hardware:** Raspberry Pi 3 Model B v1.2 (1 GB de RAM, microSD) con Raspberry Pi OS Lite de 64 bits. Sin ESP32, sin Arduino, sin pantallas ni sensores.
- **Canal:** solo Telegram, con un único usuario (yo). Nada de WhatsApp, SMS ni correo.
- **Costo cero:** solo servicios gratuitos que no pidan tarjeta.
- **IA:** no se usa por defecto. Es la última fase y queda apagada salvo que yo la active.
- **Redes sociales:** no se leen Facebook ni X, porque no hay acceso gratuito y confiable. Se cubren con medios y sitios oficiales.
- **Ruido:** alertas rojas inmediatas más 2 resúmenes al día. El resto se consulta bajo demanda.
- **Zona horaria:** `America/Hermosillo` (UTC−7, sin horario de verano). Guarda las fechas en UTC y muéstralas en hora local.
- **Nombre:** Búho, como la mascota de la Unison.

---

## 2. Módulo de clima

### Fuente y datos

- **Fuente:** Open-Meteo Forecast API (`https://api.open-meteo.com/v1/forecast`).
  - No pide API key.
  - Es gratis para uso no comercial, con menos de 10,000 llamadas al día.
  - Exige atribución CC BY 4.0: ponla en el README y en el dashboard.
- **Ubicación** (configurable): Hermosillo, lat 29.07, lon −110.96.
- **Variables** (verifica los nombres contra la documentación vigente):
  - `daily`: `temperature_2m_max`, `temperature_2m_min`, `apparent_temperature_max`, `precipitation_probability_max`, `wind_gusts_10m_max`, `uv_index_max`, `sunrise`, `sunset`, `weather_code`.
  - `hourly`: `temperature_2m`, `precipitation_probability`, `wind_gusts_10m`, `weather_code`.
  - Parámetros: `timezone=America/Hermosillo` y `forecast_days=2`.

### Mensaje programado

- **Horario:** 06:00 de lunes a viernes; 09:00 sábado y domingo.
- **Si la Pi arrancó tarde:** envíalo igual, siempre que no pasen de las 10:00.
- **Nunca dos veces el mismo día:** registra el envío en la BD.
- **Formato de ejemplo:**

```
☀️ Buenos días · Hermosillo, mar 29 sep
Máx 36° / Mín 25° · Sensación 39°
🌧️ Lluvia: mañana 70% · tarde 40% · noche 10%
💨 Rachas hasta 65 km/h · UV 9 (muy alto)
🌅 06:15 · 🌇 18:13
⚠️ Rachas fuertes por la mañana: asegura objetos sueltos.
```

- **Consejos de la última línea:** salen de reglas simples:
  - calor ≥ 40 °C;
  - UV ≥ 8;
  - lluvia ≥ 60 %;
  - rachas ≥ 50 km/h.

  Máximo dos consejos. Si no aplica ninguno, se omite la línea.

### Alerta 🔴 de clima

- Revisa el pronóstico cada hora.
- Si en las próximas 12 h se cruzan los umbrales de `weather_alerts` (sección 10), envía una alerta roja.
- Una sola alerta por evento: no la repitas mientras siga vigente.

### Comandos

- `/clima`: ahora y el resto del día.
- `/clima manana`: pronóstico de mañana.

---

## 3. Módulo de noticias

### 3.1 Fuentes iniciales

Estado verificado el 27 de septiembre de 2026. Lo marcado *por verificar* lo resuelves en la Fase 0.

**`elimparcial`** — Hermosillo y Sonora
- URL: `https://www.elimparcial.com/arc/outboundfeeds/rss/?outputType=xml`
- Funciona y se actualiza al minuto, pero:
  - mezcla Tijuana, Mexicali, nacional y deportes;
  - trae el HTML completo de cada nota.
- Conserva solo los items cuyo link contenga `/son/hermosillo/` o `/son/sonora/`, más cualquier item que mencione a la Unison.
- Usa solo título, link, descripción, fecha y autor. No guardes el contenido.
- *Por verificar:* si existe un feed por sección, p. ej. `/arc/outboundfeeds/rss/category/son/hermosillo/?outputType=xml`. Si existe, prefiérelo.

**`unison`** — noticias oficiales (*por verificar*)
- `https://www.unison.mx/feed/` existe (WordPress), pero trae ruido: sus entradas más recientes eran páginas de prueba ("Murales prueba 3"), con galerías enormes y categoría "Sin categoría".
- Investiga en este orden:
  1. La API REST de WordPress (`/wp-json/wp/v2/posts`), filtrando por categoría.
  2. Los feeds por categoría (`/category/<slug>/feed/`).
  3. El listado de noticias del sitio (`/noticias-anteriores/`).
  4. `https://direcciondecomunicacion.unison.mx`.
- Elige lo más estable y documenta la decisión.

**`gnews_unison`** — la Unison en otros medios, vía Google News RSS
- Base: `https://news.google.com/rss/search`. Construye la URL con urlencode.
- Búsqueda: `"Universidad de Sonora" OR Unison when:1d`.
- Parámetros: `hl=es-419&gl=MX&ceid=MX:es-419`.
- Formato no oficial: puede romperse.
- Devuelve como máximo unos 100 items.
- Los links son redirecciones de Google: no las resuelvas.
- *Por verificar:* el medio viene en el elemento `<source>` y los títulos terminan en " - Medio"; quita ese sufijo antes de comparar títulos.
- Intervalo mínimo: 30 min.

**`gnews_hmo`**
- Igual que la anterior, con la búsqueda `Hermosillo when:1d`.
- Alimenta la detección de "noticia caliente".

**`ps_latam`**
- `https://blog.latam.playstation.com/feed/`
- Oficial, en español.

**`nintendolife`**
- `https://www.nintendolife.com/feeds/latest`
- En inglés y publica mucho: solo pasa a 🟡 con palabra clave.

**`steam_mhwilds`** — Monster Hunter Wilds
- `https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=2246340&count=10&maxlength=300`
- API pública de Steam, sin llave.
- *Por verificar:* quédate solo con los anuncios oficiales (campo `feedname` = `steam_community_announcements`), no con notas de prensa externas.

**`steam_mhascendance`** — Monster Hunter Wilds: Ascendance
- Igual que la anterior, con `appid=4829700`.
- Es la expansión anunciada para 2027.

#### Reglas para todas las fuentes

- **Fuentes nuevas:** agregar una fuente RSS debe requerir solo una entrada en `config.yaml`.
- **Aislamiento:** cada fuente tiene su propio intervalo, timeout y categoría, y su falla nunca afecta a las demás.
- **Intervalos por defecto:**
  - El Imparcial: 10 min.
  - Unison: 15 min.
  - Google News y feeds de videojuegos: 30 min.
  - Steam: 60 min.
- **Buenas prácticas de red:**
  - GET condicional (ETag / Last-Modified).
  - User-Agent claro: `BuhoBot/1.0 (uso personal)`.
  - Timeouts de 10 a 20 s.
  - Backoff exponencial con jitter.
  - Máximo 3 descargas simultáneas.
- **Fixtures de prueba:** guarda respuestas reales pero recortadas (pocos items, sin el HTML completo de las notas). El repo debe ser privado.

### 3.2 Procesamiento

**Normalización**
- Limpia HTML y entidades, y recorta espacios.
- Quita los parámetros de rastreo de las URLs (`utm_*`, `fbclid`) y calcula una URL canónica.

**Coincidencias de palabras clave**
- Sin distinguir mayúsculas ni acentos: "suspensión" = "suspension". Por eso el config usa palabras sin acentos.
- Por palabra o frase completa: que "paro" no coincida dentro de otra palabra.

**Categorías:** `unison`, `hermosillo` y `videojuegos`.
- Los items de `/son/sonora/` entran a `hermosillo` solo si mencionan Hermosillo o activan una regla roja.
- Todo item que mencione Unison o "Universidad de Sonora" también cuenta para `unison`.

**Niveles**
- 🔴 **Inmediato:** activa una regla roja de su categoría, o viene de una fuente listada en `official_red_sources`.
- 🟡 **Resumen:** coincide con una palabra amarilla, o viene de una fuente oficial de su categoría (Unison, PS LATAM).
- ⚪ **Solo registro:** todo lo demás que pasó los filtros. No se notifica, pero se puede consultar.

**Puntaje** (sirve para ordenar el resumen)
- Las coincidencias en el título pesan más que en la descripción.
- Las palabras de `low_weight` suman poco y por sí solas no alcanzan 🟡.
- Las fuentes oficiales y `personal_keywords` suman.
- `deprioritize` resta, excepto en reglas rojas.

**Enfriamiento de reglas rojas**
- Después de disparar, cada regla roja manda sus siguientes coincidencias a 🟡 durante 12 h (configurable).
- Así un Nintendo Direct no genera diez alertas.

**Agrupación y dedupe**
- La misma historia publicada en varios medios forma un grupo.
  - Criterio: similitud de títulos normalizados en una ventana de 48 h.
  - Herramienta: `difflib`, o `rapidfuzz` si tiene wheel para aarch64.
- Se notifica una sola vez, indicando cuántos medios la publicaron.
- Si un medio nuevo se suma a un grupo ya notificado, no hay aviso nuevo.

**Noticia caliente**
- 2 o más medios distintos en 3 h: sube de ⚪ a 🟡.
- 3 o más medios, en `unison` o `hermosillo`: sube de 🟡 a 🔴.

**Casos especiales**
- **Antigüedad:** ignora items de más de 48 h.
- **Primer arranque (modo semilla):**
  - marca todo lo existente como visto, sin notificar;
  - envía "🦉 Búho activo" con el estado de las fuentes.
- **Tras un apagón de la Pi:**
  - envía las 🔴 de menos de 6 h (agrupadas si son varias);
  - lo demás pasa al siguiente resumen.

### 3.3 Política de envío

**🔴 Inmediato**
- Máximo 6 por hora; el excedente se agrupa en un solo mensaje.
- Botones:
  - "🔕 Silenciar fuente 24 h".
  - "👎 No me interesa" (se registra en la BD para afinar reglas después).

**🟡 Resúmenes** (14:00 y 20:00)
- Agrupados por categoría, máximo 8 por categoría, ordenados por puntaje.
- Al final de cada categoría: "y N más → /buscar".
- Si no hay nada nuevo, no se envía nada.
- Si el mensaje pasa de 4,096 caracteres, se divide en varios.

**Horario silencioso** (23:00 a 06:00)
- Solo pasan las 🔴.
- Las alertas del sistema (fuentes caídas) esperan a las 06:00.

**`/silencio <duración>`**
- Pausa todo, incluidas las 🔴.
- Al terminar el silencio:
  - las 🔴 pendientes llegan juntas en un solo mensaje;
  - los resúmenes perdidos se suman al siguiente.
- `/activar` termina el silencio antes de tiempo.

**Formato**
- HTML, escapando siempre el texto de las fuentes.
- Sin vista previa de links en los resúmenes.

**Límites de Telegram**
- Aproximadamente 1 mensaje por segundo por chat.
- Ante un error 429, espera lo que indique `retry_after`.

**Ejemplos**

```
🔴 Hermosillo · suspensión de clases
Suspenden clases presenciales en todo el estado por lluvias
El Imparcial · hace 5 min · +2 medios
[🔕 Silenciar fuente 24 h] [👎 No me interesa]
```

```
🟡 Resumen de las 14:00
🎓 Unison (2)
• Título de la nota — Unison
• Título de la nota — El Imparcial · +1 medio
🏙️ Hermosillo (3)
• …
🎮 Videojuegos (4)
• …
```

---

## 4. Bot de Telegram

**Librería**
- `python-telegram-bot`, versión estable más reciente (async), con el extra `job-queue`.
- Long polling: sin webhooks ni puertos abiertos.

**Seguridad**
- Solo responde al chat de `TELEGRAM_CHAT_ID`.
- Cualquier otro chat se ignora y queda en el log.

**Modo configuración**
- Si falta `TELEGRAM_CHAT_ID`, `/start` responde con el chat id para que yo lo copie al `.env`.

**Comandos** (regístralos con `set_my_commands` para que aparezcan en el menú de Telegram)
- `/clima [manana]`
- `/unison`, `/hmo`, `/juegos`: lo del día por categoría, incluidos los ⚪.
- `/resumen`: muestra lo que traerá el próximo resumen, sin marcarlo como enviado.
- `/buscar <texto>`: con FTS5 de SQLite si está disponible; si no, con LIKE.
- `/silencio <2h|30m|manana>` y `/activar`.
- `/fuentes`: estado de cada fuente, con botones para silenciarla o reactivarla.
- `/estado`, que muestra:
  - versión y tiempo encendido;
  - última lectura y fallas por fuente;
  - tamaño de la BD y memoria;
  - temperatura del CPU (`/sys/class/thermal/thermal_zone0/temp`);
  - avisos de bajo voltaje (`vcgencmd get_throttled`, si existe).
- `/ayuda`

**Salud de fuentes**
- Si una fuente falla 3 veces seguidas, avísame una sola vez.
- Avísame también cuando se recupere.

**Botones**
- `callback_data` admite máximo 64 bytes: usa ids cortos.

---

## 5. Arquitectura

### Base

- Python 3.11 o superior, compatible con el Python de la versión actual de Raspberry Pi OS.
- Un venv del proyecto con dependencias fijadas.
- Sin Docker.

### Dependencias sugeridas

- **Núcleo:** `python-telegram-bot[job-queue]`, `httpx`, `feedparser`, `pydantic`, `pydantic-settings`, `PyYAML`.
- **Dashboard (Fase 3):** `fastapi`, `uvicorn`, `jinja2`.
- **Desarrollo:** `pytest`, `pytest-asyncio`, `respx` (o `httpx.MockTransport`), `ruff`.
- **Evita** dependencias pesadas o que tengan que compilarse en ARM: nada de pandas ni navegadores headless.

### Procesos

- **`buho-bot`:** un solo loop asyncio con el bot, el scheduler (JobQueue), los colectores y el notificador. Es el único proceso que escribe en la BD.
- **`buho-web`** (Fase 3): abre la BD en solo lectura.
- SQLite en modo WAL, con `busy_timeout`.

### Capa de consultas compartida

- `services/queries.py`: la usan los comandos de Telegram, el dashboard y, a futuro, un servidor MCP.
- Sin lógica duplicada entre ellos.

### Scheduler

- Zona horaria `America/Hermosillo` explícita.
- Ojo: en `run_daily` de python-telegram-bot, el parámetro `days` usa 0 = domingo. Verifícalo en la versión que instales y cúbrelo con pruebas.

### Idempotencia

- Restricción UNIQUE sobre fuente + guid o URL canónica.
- Registro de todo lo enviado.
- Reiniciar nunca debe duplicar notificaciones ni el clima.
- Apagado limpio al recibir SIGTERM.

### Esquema mínimo (tú propones el detalle)

- `items`: fuente, id externo, URL canónica, título, resumen, fechas, categoría, nivel, puntaje, reglas que coincidieron, grupo, estado de notificado/resumido.
- `clusters`.
- `source_state`: etag, last_modified, último OK, fallas seguidas, último error, silenciada hasta.
- `sent_messages`: el `message_id` de Telegram ligado a su item, para los botones.
- `feedback`.
- `app_state`: silencio activo y envíos programados por fecha.

### Retención

- Borra items de más de 30 días (configurable).

### CLI (`python -m buho <comando>`)

- `run`
- `check-sources`: prueba cada fuente e imprime estado, número de items y tres títulos de ejemplo.
- `send-test`
- `preview-weather` y `preview-digest`: imprimen en consola sin enviar.

### Modo simulación

- Con `BUHO_DRY_RUN=1`, los mensajes se imprimen en consola en vez de enviarse.
- Es para desarrollar en mi PC.

### Configuración

- **`config.yaml`:** fuentes, horarios, umbrales y palabras clave. Se valida con pydantic y los errores se explican en español.
- **`.env`:** secretos:
  - `TELEGRAM_BOT_TOKEN`;
  - `TELEGRAM_CHAT_ID`;
  - `GEMINI_API_KEY` (solo en la Fase 4).
- **En git** solo van `config.example.yaml` y `.env.example`.

---

## 6. Restricciones de la Pi 3

**Memoria**
- Objetivo: bot por debajo de 150 MB; web por debajo de 100 MB.
- Techo en systemd: `MemoryMax=300M` para el bot y `200M` para la web.

**Cuidado de la microSD**
- Escrituras en lote por ciclo.
- Logs a stdout/journald, sin archivos de log propios.
- Documenta cómo limitar journald (`SystemMaxUse=50M`).
- Nada de VACUUM frecuente.

**Hora y red** (la Pi no tiene reloj propio)
- Las unidades arrancan después de `network-online.target` y `time-sync.target`.
- Documenta cómo habilitar `systemd-time-wait-sync`.
- Si se cae el Wi-Fi, el bot se recupera solo.
- `Restart=on-failure` en las unidades.

---

## 7. Seguridad

**Secretos**
- `.env` con permisos 600 y nunca en git.
- El token nunca aparece en los logs.
- Nunca me pidas pegar secretos en la conversación: dime en qué archivo van.

**Servicios**
- Corren con un usuario sin privilegios (`buho`).
- Endurecimiento básico de systemd:
  - `NoNewPrivileges`;
  - `ProtectSystem=strict`;
  - `ReadWritePaths` solo para el directorio de datos.

**Contenido de las fuentes**
- Trátalo como no confiable.
- Escápalo siempre, tanto en Telegram como en las plantillas (Jinja con autoescape).

**Dashboard**
- Escucha solo en `127.0.0.1`.
- Se expone únicamente a mis dispositivos con `tailscale serve` (solo tailnet).
- Nada de puertos abiertos ni de Funnel.

---

## 8. Dashboard web (Fase 3)

**Tecnología**
- FastAPI + Jinja2 + HTMX, servido localmente (sin CDN).
- Solo lectura, pensado primero para celular y con modo oscuro.

**Páginas**
- **Inicio:** clima de hoy, últimas 🔴 y lo del día por categoría.
- **Noticias:** filtros por categoría, nivel y fecha, más búsqueda.
- **Fuentes:** salud de cada una.

**Además**
- Incluye la atribución de Open-Meteo.
- Deja un punto de extensión para agregar tarjetas cuando sume módulos nuevos.

---

## 9. IA opcional (Fase 4, apagada por defecto)

**Diseño**
- `llm.enabled: false` por defecto.
- Interfaz `LLMProvider`; la primera implementación usa la API de Gemini por REST con httpx.
- Modelo configurable, de la familia Flash-Lite (verifica el nombre vigente).

**Usos**
- Traducir al español los titulares en inglés del resumen, en una sola llamada por resumen.
- Opcional: tres viñetas de síntesis al inicio del resumen.

**Reglas**
- Nunca bloquea ni retrasa una notificación: timeout corto y, ante cualquier error, sale el resultado sin IA.
- Tope diario de llamadas configurable (20 por defecto).
- Solo se envían titulares públicos.

**Futuro (no implementar)**
- Un servidor MCP sobre `services/queries.py` para consultar a Búho desde Claude.

---

## 10. Configuración inicial

```yaml
timezone: America/Hermosillo
location: {name: Hermosillo, lat: 29.07, lon: -110.96}

schedule:
  weather_weekdays: "06:00"      # lunes a viernes
  weather_weekends: "09:00"      # sabado y domingo
  weather_late_limit: "10:00"    # si la Pi arranco tarde, enviar hasta esta hora
  digests: ["14:00", "20:00"]
  quiet_hours: {start: "23:00", end: "06:00"}

limits:
  max_red_per_hour: 6
  red_rule_cooldown_hours: 12
  digest_max_per_category: 8
  max_item_age_hours: 48
  catchup_red_max_age_hours: 6
  retention_days: 30

hot_news:
  window_hours: 3
  to_yellow_min_sources: 2
  to_red_min_sources: 3          # solo unison y hermosillo

weather_alerts:
  gust_kmh: 60
  heat_c: 43
  rain_probability: 70
  storm_weather_codes: [95, 96, 99]

categories:
  unison:
    red: ["suspension de clases", "suspenden clases", "suspension de actividades",
          "paro", "huelga", "cierre de campus", "reinscripcion", "resultados de admision"]
    yellow: ["unison", "universidad de sonora", "convocatoria", "becas",
             "calendario escolar", "inscripciones"]
    personal_keywords: []        # mi carrera o division
    deprioritize: ["navojoa", "cajeme", "nogales", "caborca", "santa ana"]
  hermosillo:
    red: ["suspenden clases", "proteccion civil", "huracan", "tormenta tropical",
          "evacuacion", "corte de agua", "sin agua", "apagon"]
    yellow: ["hermosillo", "agua de hermosillo", "cfe", "cierre vial", "lluvia"]
    exclude: ["horoscopo"]
  videojuegos:
    red: ["nintendo direct", "state of play"]
    yellow: ["monster hunter", "capcom", "playstation", "ps5", "switch 2",
             "zelda", "mario", "pokemon"]
    low_weight: ["announced", "anuncia", "release date", "fecha de lanzamiento", "trailer"]
    official_red_sources: ["steam_mhwilds", "steam_mhascendance"]

sources:                         # ejemplo; incluye todas las de la seccion 3.1
  - id: ps_latam
    type: rss
    url: https://blog.latam.playstation.com/feed/
    category: videojuegos
    interval_minutes: 30
    official: true
```

---

## 11. Fases y criterios de aceptación

### Fase 0 — Base y validación de fuentes

**Entregables**
- `git init`, `.gitignore`, `CLAUDE.md` y `PROGRESS.md`.
- Esqueleto del proyecto, config validada y esquema de la BD.
- `check-sources` y fixtures reales recortadas.
- Decisión documentada sobre cómo leer la Unison.

**Lista cuando**
- `check-sources` reporta todas las fuentes (las que fallen, con una alternativa propuesta).
- `ruff` y `pytest` pasan.

### Fase 1 — Clima y bot mínimo, corriendo en la Pi

**Entregables**
- Bot restringido a mi chat, con modo configuración.
- Comandos `/start`, `/ayuda`, `/clima` y `/estado`.
- Clima programado con idempotencia y envío tardío.
- `send-test` y `preview-weather`.
- `deploy/install_pi.sh` idempotente, script de actualización y unidades systemd.
- README en español desde cero, que cubra:
  - Raspberry Pi Imager y SSH;
  - crear el bot con @BotFather y obtener el chat id;
  - configurar `.env` e instalar;
  - ver logs con `journalctl`;
  - actualizar;
  - respaldar la BD con `sqlite3 .backup`.

**Lista cuando**
- Pasan las pruebas de horarios (qué hora toca cada día de la semana).
- Recibo el clima en Telegram desde la Pi.

### Fase 2 — Noticias

**Entregables**
- Colectores, normalización y reglas.
- Niveles, enfriamiento, agrupación y noticia caliente.
- 🔴 con botones, resúmenes, horario silencioso y `/silencio`.
- Modo semilla, recuperación tras un apagón y salud de fuentes.
- Comandos `/unison`, `/hmo`, `/juegos`, `/resumen`, `/buscar`, `/silencio`, `/activar` y `/fuentes`.
- `preview-digest`.

**Lista cuando**
- Una prueba de integración con fixtures, sin red, produce las 🔴 y el resumen esperados.
- Reiniciar no duplica nada.
- Revisamos juntos la salida de `preview-digest` con datos reales para afinar las palabras clave.

### Fase 3 — Dashboard

**Entregables**
- `buho-web` y su unidad systemd.
- Guía de Tailscale (`tailscale serve`, solo tailnet).

**Lista cuando**
- Lo abro desde mi celular fuera de casa y se ve bien.

### Fase 4 — IA opcional

**Lista cuando**
- Con `enabled: false` no hay ninguna llamada a la API.
- Con `enabled: true` aparecen traducciones y síntesis.
- Si la API falla, el resumen sale igual, sin IA.

---

## 12. Calidad

**Código**
- Type hints en todo.
- `ruff` para lint y formato.

**Pruebas**
- `pytest` sin red, con fixtures y reloj inyectable.
- Como mínimo deben cubrir:
  - normalización y coincidencias sin acentos;
  - niveles, enfriamiento, agrupación y noticia caliente;
  - horario silencioso y `/silencio`;
  - armado y división de resúmenes;
  - formato del clima y horarios por día;
  - idempotencia tras reinicio.

**Logs**
- Concisos: fuente, cantidad de items, duración y errores.

**Commits**
- Pequeños.

---

## 13. Fuera de alcance

- Otros dispositivos y canales: ESP32, Arduino, WhatsApp, SMS y correo.
- Redes sociales: Facebook y X/Twitter.
- Infraestructura: servicios de pago, Docker y navegadores headless.
- Exposición pública del dashboard.
- IA encendida por defecto.
