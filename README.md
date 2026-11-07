# kresolve: karaoke editable en DaVinci Resolve

kresolve exporta el audio de la timeline de Resolve, lo transcribe con
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) con tiempos por
palabra y crea clips **Text+ editables** en la timeline: la frase completa y,
encima, la palabra que suena resaltada en otro color.

Funciona con **DaVinci Resolve gratuito** (scripts en Workspace > Scripts) y
con **Studio** (también desde la terminal). Desarrollado y comprobado contra la
API de Resolve 21.2 en Windows.

```
 Resolve                     Python del proyecto (.venv)                 Resolve
┌──────────────┐  wav  ┌───────────────┐  transcript.json  ┌─────────┐  plan.json  ┌──────────────┐
│ 1 Exportar   │──────▶│ 2 Transcribir │──────────────────▶│ plan    │────────────▶│ 3 Crear      │
│   audio      │       │ faster-whisper│   (editable)      │ grouper │             │   títulos    │
└──────────────┘       └───────────────┘        │          └─────────┘             │ Text+ x capa │
                                                ▼                                   └──────────────┘
                                   .srt / .ass / overlay ProRes 4444 con alfa
```

## Inicio rápido (Windows)

```powershell
# 1. Entorno (Python 3.12 recomendado)
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\activate

# 2. Comprobar
kresolve doctor
pytest

# 3. Scripts de menú para Resolve (luego reinicia Resolve)
kresolve install-scripts
```

En Resolve, una sola vez: crea la plantilla Text+ `kresolve_template` en el
Media Pool ([guía, paso 6](docs/GUIA_PASO_A_PASO.md#paso-6-crear-la-plantilla-text-en-resolve)).
Después, con la timeline abierta y la consola visible (Workspace > Console):

1. **Workspace > Scripts > kresolve 0 - Diagnostico**, solo la primera vez.
2. **kresolve 1 - Exportar audio**
3. **kresolve 2 - Transcribir**: abre una ventana con el progreso.
4. *(opcional)* corrige `work/transcript.json`.
5. **kresolve 3 - Crear titulos**

La guía completa, paso a paso y con solución de problemas, está en
**[docs/GUIA_PASO_A_PASO.md](docs/GUIA_PASO_A_PASO.md)**.

## Comandos

| Comando | Qué hace | Requiere |
|---|---|---|
| `kresolve doctor [--connect]` | Comprueba Python, dependencias, GPU, ffmpeg, Resolve y config | |
| `kresolve install-scripts [--uninstall]` | Instala los scripts de Workspace > Scripts | |
| `kresolve extract-audio VIDEO` | Audio de un archivo con ffmpeg (sin Resolve) | ffmpeg |
| `kresolve transcribe AUDIO` | Transcribe y genera `work/transcript.json` y `.srt` | |
| `kresolve plan TRANSCRIPT` | Agrupa y escribe `work/plan.json` (lo que lee Resolve) | |
| `kresolve subs TRANSCRIPT` | Regenera `.srt` y `.ass` tras corregir el JSON | |
| `kresolve overlay TRANSCRIPT` | Overlay ProRes 4444 con alfa y color por palabra | ffmpeg |
| `kresolve export-audio` | Render de audio de la timeline | Studio |
| `kresolve build-titles TRANSCRIPT` | Crea los Text+ en la timeline activa | Studio |
| `kresolve clear-titles` | Borra los clips de las pistas kresolve | Studio |
| `kresolve run` | export-audio, transcribe y build-titles seguidos | Studio |

"Studio" significa que el comando se conecta a Resolve desde fuera, cosa que
la versión gratuita no permite. En la versión gratuita esas acciones se
lanzan desde los scripts del menú, que hacen lo mismo.

## Estrategias de agrupación

| `grouping.strategy` | Resultado en la timeline |
|---|---|
| `per_line` (por defecto) | Pista `kresolve` con la frase + pista `kresolve HL` con la palabra activa resaltada |
| `per_line_single` | Una frase por clip, sin resaltado (subtítulos normales) |
| `per_word` | Una palabra por clip (estilo reels) |
| `sliding` | Las palabras van apareciendo (ventana de N palabras), con resaltado opcional |

## Estructura

```
config.yaml               configuración (modelo, idioma, estrategia, Resolve)
styles/presets.yaml       presets de estilo (plantilla, karaoke_default, reels)
src/kresolve/
  models.py               Word, Segment, Transcript, TitleClip
  config.py               carga y valida config.yaml
  registry.py             @register_transcriber / @register_grouper
  planning.py             segundos -> frames, estilo, rango Write On
  pipeline.py             orquesta las etapas
  cli.py                  comandos
  overlay.py              overlay ProRes 4444 con ffmpeg
  transcribe/             faster_whisper_engine.py
  grouping/               per_word, per_line, per_line_single, sliding
  exporters/              json_io (transcript/plan), srt, ass
  resolve/                capa Resolve (solo stdlib)
    client.py             conexión, proyecto, timeline, fps
    audio_export.py       render de solo audio
    title_builder.py      crea los Text+ (AppendToTimeline + calibración)
    textplus.py           entradas del nodo Text+
    diagnostics.py        prueba en una timeline aparte
    menu.py               entrada de los scripts de Workspace > Scripts
    install.py            instala esos scripts
tests/                    51 tests; incluye un Resolve simulado (fake_resolve.py)
docs/
  GUIA_PASO_A_PASO.md     instalación y uso
  ANALISIS.md             análisis del diseño original y decisiones
```

## Estado

- Probado en este equipo: transcripción real en GPU y en CPU, agrupación,
  exportadores, planificación en frames, overlay con ffmpeg, el TitleBuilder
  contra un Resolve simulado, y los scripts del menú ejecutados con el Python
  3.14 integrado de Resolve.
- Falta probar con Resolve abierto: la parte que habla con Resolve no se ha
  ejecutado contra la aplicación real. El script **kresolve 0 - Diagnostico**
  sirve para eso; qué revisar y por qué está en
  [docs/ANALISIS.md](docs/ANALISIS.md#7-estado-de-verificación).
