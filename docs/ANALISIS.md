# Análisis del diseño original y decisiones de implementación

Este documento compara el diseño inicial (`karaoke-resolve-app.md`) con la
API real de DaVinci Resolve 21.2 y explica qué se cambió y por qué.

## 1. Resumen

La arquitectura del diseño se mantiene: un pipeline por etapas, el JSON como
punto de corte, Resolve aislado en `resolve/` y un registry de estrategias.
Al contrastarlo con la documentación oficial instalada aparecieron tres
problemas de fondo:

| # | Problema | Gravedad | Solución |
|---|---|---|---|
| A | `InsertFusionTitleIntoTimeline` no permite fijar la pista ni la duración, y puede caer en pistas del usuario | Alta (bloqueaba el hito 3) | Plantilla en el Media Pool + `AppendToTimeline` con posición, pista y duración, con calibración |
| B | El color por rango de caracteres (Character Level Styling) **no es scriptable** | Alta (bloqueaba el hito 4) | Dos capas: la frase y, encima, la misma frase mostrando solo la palabra activa con *Write On* |
| C | La versión gratuita no admite scripting externo, y su Python no tiene pip | Alta (el proyecto se llama *FreeSubs*) | Scripts de menú en Resolve (solo stdlib) que delegan Whisper al `.venv` |

Además se corrigieron nombres de API inventados o ya obsoletos y se encontró
una incompatibilidad real entre faster-whisper y PyAV al probar (sección 3.11).

## 2. Fuentes verificadas

Todo se contrastó con la instalación de este equipo, Resolve **21.2.0.6** en
`Z:\Programs\Davinci`:

| Fuente | Ruta |
|---|---|
| README de scripting (31 ago 2026) | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\README.md` |
| Definición de la API | `...\Scripting\DaVinciResolveScript.pyi` |
| Cambios por versión (incluye 21.2) | `...\Scripting\CHANGELOG.md` |
| Referencia de nodos Fusion (Text+) | `...\Support\Developer\Fusion\FusionToolReference.md` |
| Ejemplo oficial de `AppendToTimeline` | `...\Scripting\Examples\7_add_subclips_to_timeline.py` |
| Python integrado de Resolve | `Z:\Programs\Davinci\ResolvePython\ResolvePython.exe` (3.14.4) |

## 3. Hallazgos, sección por sección

### 3.1 Requisitos: gratuito o Studio

- **Confirmado:** el scripting externo (*External scripting using: Local*)
  solo existe en Studio, según el README, sección *Configuration*. En la
  versión gratuita, `scriptapp("Resolve")` devuelve `None` desde fuera.
- **Nuevo en 21.1:** Resolve trae un **Python 3.14 propio** para los scripts
  del menú y la consola, en el que `import DaVinciResolveScript` funciona sin
  variables de entorno. Pero **no tiene pip**, así que no puede ejecutar
  faster-whisper.
- **Decisión:** la interfaz principal son 6 scripts de *Workspace > Scripts*
  (`kresolve install-scripts`). Funcionan en gratuito y en Studio. Los
  comandos de la CLI que hablan con Resolve quedan como atajo para Studio.

### 3.2 Variables de entorno

El diseño traía las de Linux; este equipo es Windows. Además,
`DaVinciResolveScript.py` solo busca `fusionscript.dll` en
`C:\Program Files\Blackmagic Design\DaVinci Resolve\`, y aquí Resolve está en
`Z:\`. `resolve/client.py` configura `RESOLVE_SCRIPT_LIB` a partir de
`resolve.install_dir` (de config.yaml) y añade la carpeta de módulos al
`sys.path`, así que no hace falta tocar variables de entorno a mano.

### 3.3 Dos procesos de Python (nueva regla de diseño)

| Proceso | Intérprete | Hace | Dependencias |
|---|---|---|---|
| Lado Resolve | ResolvePython 3.14 (o el Python externo en Studio) | Render de audio, crear Text+, diagnóstico | **Solo stdlib** |
| Lado proyecto | `.venv` (Python 3.12) | Leer config.yaml, Whisper, agrupar, exportar | faster-whisper, PyYAML, typer |

Los scripts de menú llaman a `python -m kresolve dump-config / transcribe / plan`
del `.venv` y leen JSON. `tests/test_config_cli.py::test_resolve_side_needs_only_stdlib`
bloquea las librerías de pip e importa todo el lado Resolve para garantizar la
regla.

### 3.4 `audio_export.py`

| Diseño | API 21.2 | Cambio |
|---|---|---|
| `SetCurrentRenderFormatAndCodec("wav", "LinearPCM")  # VERIFICAR` | 21.1 añadió `GetAudioRenderFormats()`, `GetAudioRenderCodecs(ext)` y las claves `AudioFormat` / `AudioCodec` de `SetRenderSettings` ("only if ExportVideo is False") | Se descubren los formatos y códecs y se elige WAV/PCM. Si falla, el error lista los disponibles |
| `StartRendering(job)` | `StartRendering(jobIds: list[str])` | Se prueba la lista y, si no, la firma antigua |
| `while IsRenderingInProgress()` | Desde 21.1.1 los render son *non-blocking*: justo después de `StartRendering` puede devolver False antes de empezar | Se consulta `GetRenderJobStatus(job)` hasta `Complete` / `Failed` |
| Devuelve `out_dir/name.wav` | La extensión la pone Resolve | Se busca el archivo real |
| Offset de `MarkIn` "a mano" | `GetMarkInOut()` da frames relativos al inicio | Se guarda en `kresolve_audio.meta.json` y build-titles lo suma solo |
| Sin limpieza | | Se borra el job y se restauran el formato y el modo de render |

### 3.5 `client.py`

- `Timeline.GetSetting(name)` está **obsoleto** (README, *Deprecated Calling
  Conventions*); se usa `GetSettings()[name]`, con la antigua como respaldo.
- `float("23.976")` no es 24000/1001: deriva ~0,014 frames cada 10 minutos.
  `planning.fps_fraction` usa fracciones exactas para 23.976, 29.97, 59.94, etc.
- Se mantiene la regla de un único sitio para pasar de segundos a frames
  (`planning.plan_frames`).

### 3.6 `title_builder.py`: duración y pista de los Text+ (riesgo A)

`InsertFusionTitleIntoTimeline("Text+")` inserta en el cabezal, en una pista
que elige Resolve, con la duración estándar de generadores. Repetirlo por
cada palabra supone cientos de movimientos de cabezal, y el clip puede caer
encima de tus clips. De las tres estrategias de respaldo del diseño:

1. Recortar tras insertar: 21.1.2 añadió `SetLeftOffset` / `SetRightOffset`
   y `SetPosition`, pero `SetRightOffset` está definido como "offset
   *disponible*", y su efecto en títulos es ambiguo. No se usa para la duración.
2. **`MediaPool.AppendToTimeline` con `recordFrame`/`startFrame`/`endFrame`: es la elegida.**
   `AppendClipInfo` acepta `mediaPoolItem`, `startFrame`, `endFrame`,
   `mediaType`, `trackIndex` y `recordFrame`. Hace falta un `MediaPoolItem`:
   un Text+ que el usuario arrastra una vez al Media Pool (la plantilla).
3. Convertir un SRT a Text+: no existe en la API.

Quedan dos ambigüedades, que se resuelven **midiendo**:

- ¿`recordFrame` es absoluto o relativo al inicio de la timeline (86400 en 01:00:00:00 a 24 fps)?
- ¿`endFrame` es inclusivo? El ejemplo oficial 7 usa `0..23` para 24 frames,
  es decir, inclusivo.

`TitleBuilder.calibrate()` inserta un clip de prueba de 12 frames, mide
`GetStart()` y `GetDuration()`, lo borra y corrige el resto. Después del lote
se verifica cada clip, y los que no estén en su sitio se recolocan con
`SetPosition` (21.1.2+). El test cubre las 4 combinaciones posibles.

Ventajas extra:

- Las pistas son propias (`kresolve`, `kresolve HL`); las del usuario no se tocan.
- Al rehacer, solo se vacían esas pistas.
- La plantilla funciona como diseño visual: lo que se ve en el Inspector es
  lo que sale, y los presets de YAML pasan a ser opcionales.

### 3.7 Resaltado de la palabra activa (riesgo B)

`FusionToolReference.md`, sección *Character Level Styling*: la entrada
`CharacterLevelStyling` es *"Not scriptable here"*, y seleccionar caracteres
*"is not verified from script"*. El plan del hito 4 ("cambiar el color de un
rango de caracteres") no se puede hacer por API.

Solución con entradas documentadas del Text+:

- Capa `base`: la frase completa.
- Capa `highlight`, una pista encima: **la misma frase**, con *Write On*
  (`Start`, `End`, 0..1, "the visible portion of the text") limitado a la
  palabra activa, en el color `highlight_color` (`Red1`/`Green1`/`Blue1`).
  Como el texto y la plantilla son idénticos, la maquetación coincide y la
  palabra cae exactamente encima.
- `planning.writeon_range` añade medio carácter de margen a cada lado. Como
  hay espacios entre palabras, el margen solo puede destapar espacios, y el
  resultado no depende de si Fusion redondea hacia arriba o hacia abajo (hay
  un test para cada convención).
- **Pendiente de ver en Resolve:** si *Write On* cuenta los espacios. Si no,
  se cambia `writeon_count_spaces: false`. El diagnóstico lo muestra.

Como vía garantizada se adelantó el hito 6: `kresolve overlay` genera un `.ass`
con el mismo modelo de dos capas (en libass las palabras no activas quedan
transparentes con `\alpha&HFF&`) y un ProRes 4444 con alfa.

### 3.8 Modelos y groupers

- `TitleClip` pasa de `text` a `words` + `layer` + `highlight_index`.
  Con las palabras se puede calcular el rango de caracteres después de
  transformar el texto (p. ej. `uppercase`).
- El `per_line` original creaba un clip por palabra con la frase completa;
  en Resolve eso daba N frases apiladas. Ahora son dos capas separadas.
- Un segmento de Whisper puede durar hasta ~30 s. `split_segment` lo parte en
  líneas por `max_chars`, `max_words` y silencios (`max_gap`), y prefiere
  cortar tras signos de puntuación.
- Nuevas opciones de tiempo: `lead_in` y `hold` sin solapes, y `fill_gaps`
  en `per_word` para que la palabra no parpadee.
- `per_line_single` (sugerido en el diseño) y `sliding` están implementados.

### 3.9 JSON editable

- Una palabra por línea; `_text` por segmento solo como referencia.
- La carga tolera ediciones a mano: ordena, corrige `end < start` con aviso e
  informa de números inválidos indicando la ruta (`segments[3].words[2].start`)
  y de errores de sintaxis con línea y columna.
- Un segmento con solo `text`, `start` y `end` reparte las palabras, para
  añadir frases que Whisper no detectó.

### 3.10 faster-whisper

- Los tiempos se guardan con `w.word.strip()` (Whisper antepone un espacio).
- `condition_on_previous_text: false` por defecto: reduce los bucles de
  frases repetidas en canciones.
- **GPU en Windows:** ctranslate2 4.8.5 trae `cudnn64_9.dll`, pero necesita
  `cublas64_12.dll`. Sin ella, el modelo carga en la GPU pero la
  transcripción falla al empezar (`Library cublas64_12.dll is not found`).
  Ahora se detecta el error y se sigue en CPU (int8) con un aviso, probado
  en este equipo. El extra `[cuda]` instala cuBLAS y cuDNN por pip, y
  `prepare_cuda_dlls()` registra sus carpetas con `os.add_dll_directory`.

### 3.11 Incompatibilidad encontrada al probar: PyAV 19

faster-whisper 1.2.1 llama a `av.open(..., metadata_errors="ignore")`, y PyAV
19.0.2 (la versión que instala pip hoy) ya no acepta ese argumento:

```
TypeError: open() got an unexpected keyword argument 'metadata_errors'
```

Se probaron 15.1, 16.1, 17.1 y 18.1, y todas funcionan. `pyproject.toml` fija `av>=11,<19`.

### 3.12 CLI

Añadidos: `doctor` (diagnóstico del entorno), `install-scripts`,
`extract-audio` (ffmpeg, sin Resolve), `plan`, `subs`, `overlay`,
`clear-titles` y `dump-config` (interno). `--config` funciona en todos.

### 3.13 Overlay: codificador

Medido en este equipo con 11,2 s de 1080p: `prores_ks` (perfil 4444) tarda
29,5 s y `prores_aw` (perfil 4) 14 s, con el mismo resultado visual y el mismo
perfil ProRes 4444 con alfa. Se usa `prores_aw`. La primera ejecución añade
hasta un minuto mientras libass crea la caché de fuentes.

## 4. Arquitectura final

```
                    Resolve (ResolvePython 3.14, solo stdlib)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ Workspace > Scripts > "kresolve N - ..."  ->  resolve/menu.py          │
 │   1 Exportar audio ── audio_export.py ──> work/kresolve_audio.wav      │
 │                                           work/kresolve_audio.meta.json│
 │   3 Crear titulos  ── title_builder.py <── work/plan.json              │
 └───────────┬───────────────────────────────────────▲──────────────────┘
             │ subprocess: .venv\Scripts\python -m kresolve ...           │
             ▼                                                            │
 ┌──────────────────────────────────────────────────────────────────────┐
 │ .venv (Python 3.12)                                                   │
 │   dump-config  config.yaml + styles/presets.yaml -> JSON              │
 │   transcribe   faster-whisper -> work/transcript.json (+ .srt)        │
 │   plan         grouping + estilo -> work/plan.json ───────────────────┘
 │   subs/overlay .srt / .ass / overlay.mov (ffmpeg)                     │
 └──────────────────────────────────────────────────────────────────────┘
```

Reglas:

1. Nada fuera de `resolve/` llama a la API de Resolve.
2. El JSON de transcripción es el punto de corte; `plan.json` es el contrato
   con Resolve (clips en segundos, estilo resuelto, opciones del builder).
3. Estrategias y motores se registran por nombre (`registry.py`).
4. **Nueva:** `resolve/`, `models.py`, `planning.py`, `grouping/` y
   `exporters/json_io.py` solo usan la librería estándar (lo comprueba un test).

Archivos de `work/`:

| Archivo | Lo crea | Lo usa |
|---|---|---|
| `kresolve_audio.wav` + `.meta.json` | Exportar audio | Transcribir (timeline, fps y desfase) |
| `transcript.json` / `.srt` | Transcribir | Tú (corrección), plan, subs, overlay |
| `plan.json` | plan | Crear títulos |
| `overlay.mov` / `.ass` | overlay | Importar en Resolve |
| `textplus_inputs.txt` | Diagnóstico | Consulta de IDs del Text+ |

## 5. Hitos actualizados

| # | Entrega | Estado |
|---|---|---|
| 1 | Modelos, transcriber, SRT/JSON, CLI `transcribe` | **Hecho y probado** (transcripción real en este equipo) |
| 2 | `export-audio` | Implementado según la API 21.2. **Falta ejecutarlo en Resolve** |
| 3 | `build-titles` con `per_word` | Implementado (AppendToTimeline + calibración). Probado con el Resolve simulado. **Falta el diagnóstico real** |
| 4 | `per_line` con resaltado | Implementado con dos capas y Write On. **Falta comprobarlo visualmente** |
| 5 | Presets de estilo | Hecho (`plantilla`, `karaoke_default`, `reels`). GUI y lotes: pendientes |
| 6 | `.ass` y overlay ProRes 4444 | **Hecho y probado** con ffmpeg |

## 6. Riesgos que siguen abiertos

- **Rendimiento:** cada Text+ es una comp de Fusion. Una canción de 4 min con
  `per_line` crea unos 40 clips base y unos 600 de resaltado. Si la
  reproducción va pesada: Render Cache (Playback > Render Cache > Smart),
  `per_line_single`, o el overlay.
- **Plantilla por proyecto:** el Media Pool es del proyecto. Un Power Bin
  ayuda a reutilizarla.
- **Canciones:** Whisper alinea peor con música. Si la letra ya existe, el
  siguiente paso natural es un segundo `Transcriber` con alineado forzado
  (stable-ts o WhisperX), registrado con `@register_transcriber`.
- **Cambios de API:** quedan acotados a `resolve/`. El script de diagnóstico
  sirve para comprobarlo tras cada actualización de Resolve.

## 7. Estado de verificación

| Qué | Cómo | Resultado |
|---|---|---|
| Agrupación, planificación, exportadores, config, CLI | `pytest` | pasan |
| TitleBuilder con las 4 semánticas posibles de `AppendToTimeline` | `pytest` + `tests/fake_resolve.py` | pasan |
| El lado Resolve no necesita dependencias de pip | test con bloqueo de imports | pasa |
| El lado Resolve corre en el Python de Resolve | ejecutado con `ResolvePython.exe` 3.14.4 | OK, calibración correcta |
| `DaVinciResolveScript` importable en ResolvePython | ejecutado | OK (con Resolve cerrado `scriptapp` devuelve `None`, lo esperado) |
| Transcripción real + caída a CPU | `kresolve transcribe` con modelo `base`, sin el extra `[cuda]` | OK: 24 palabras con tiempos; avisa y sigue en CPU |
| Transcripción en GPU | Igual, con el extra `[cuda]` (RTX 3060 Ti) | OK: `(cuda)` |
| Overlay ProRes 4444 con alfa | `kresolve overlay` + `ffprobe` + fotograma compuesto | OK: `prores 4444`, alfa; "prueba" resaltada encima de su sitio. 11 s de 1080p en ~14 s |
| Scripts del menú, cadena completa | Scripts instalados ejecutados con `ResolvePython.exe` | OK: `dump-config` y `plan` vía subprocess. Se para en la conexión (Resolve cerrado) |
| **Contra Resolve abierto** | — | **No ejecutado.** Lo cubre `kresolve 0 - Diagnostico` (ver abajo) |

Qué mirar en el primer diagnóstico real:

1. La línea `Calibración:`: los valores medidos de `start_bias` y `dur_bias`.
2. `capa ... N/N clips`, sin "recolocados" ni "duración distinta".
3. `entradas no aplicadas: [...]` vacío. Si aparece `Center`, el formato de
   punto no se aceptó; hay que revisarlo.
4. En el visor: el resaltado cae sobre la palabra (Write On y espacios).
5. `kresolve 1 - Exportar audio`: la línea `Render de audio: formato=... códec=...`
   confirma qué valor de `AudioFormat` acepta Resolve.
