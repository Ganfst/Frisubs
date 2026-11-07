# Guía paso a paso: kresolve en Windows

Esta guía lleva de cero a tener un karaoke editable en la timeline de DaVinci
Resolve. Los comandos son para **PowerShell**, ejecutados en la carpeta del
proyecto:

```powershell
cd "E:\Portafolio - Coding\Davinci FreeSubs"
```

Índice:

1. [Requisitos](#paso-1-requisitos)
2. [Crear el entorno de Python](#paso-2-crear-el-entorno-de-python)
3. [GPU NVIDIA (opcional)](#paso-3-gpu-nvidia-opcional)
4. [Revisar config.yaml](#paso-4-revisar-configyaml)
5. [Comprobar la instalación](#paso-5-comprobar-la-instalación)
6. [Crear la plantilla Text+ en Resolve](#paso-6-crear-la-plantilla-text-en-resolve)
7. [Instalar los scripts del menú](#paso-7-instalar-los-scripts-del-menú)
8. [Diagnóstico en Resolve](#paso-8-diagnóstico-en-resolve)
9. [Flujo de trabajo normal](#paso-9-flujo-de-trabajo-normal)
10. [Corregir la transcripción](#paso-10-corregir-la-transcripción)
11. [Estrategias y estilos](#paso-11-estrategias-y-estilos)
12. [Resolve Studio: todo desde la terminal](#paso-12-resolve-studio-todo-desde-la-terminal)
13. [Alternativas: overlay con alfa y SRT](#paso-13-alternativas-overlay-con-alfa-y-srt)
14. [Problemas frecuentes](#paso-14-problemas-frecuentes)
15. [Desinstalar](#paso-15-desinstalar)

---

## Paso 1. Requisitos

| Qué | Para qué | Cómo comprobarlo |
|---|---|---|
| DaVinci Resolve 21.1 o posterior, gratuito o Studio | Destino de los títulos | Help > About. En este PC: **21.2**, en `Z:\Programs\Davinci` |
| [uv](https://docs.astral.sh/uv/) o Python 3.10 o posterior | Entorno del proyecto | `uv --version` o `py -0p` |
| ffmpeg (opcional) | `extract-audio` y `overlay` | `ffmpeg -version` |
| GPU NVIDIA con driver reciente (opcional) | Transcribir rápido con `large-v3` | `nvidia-smi` |

No hace falta instalar Python para Resolve. Desde la 21.1, Resolve trae su
propio Python 3.14 para los scripts del menú, y kresolve no le instala nada.
Las dependencias (Whisper, etc.) viven en el entorno `.venv` del proyecto.

Si no tienes uv:

```powershell
winget install astral-sh.uv
# o bien:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

uv se instala en `%USERPROFILE%\.local\bin`. Si `uv` no se reconoce, abre una
terminal nueva o añade esa carpeta al PATH.

Para ffmpeg: `winget install Gyan.FFmpeg`.

---

## Paso 2. Crear el entorno de Python

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\Activate.ps1
```

uv descarga Python 3.12 si no lo tienes. Se ha probado con 3.12, y el
Python 3.14 de tu sistema no hace falta tocarlo.

Si PowerShell no deja ejecutar `Activate.ps1`, hay dos opciones:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # una vez
# o, sin activar, llama directamente a:
.venv\Scripts\kresolve.exe --help
```

Sin uv:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

> **Nota:** `pyproject.toml` fija `av<19`. PyAV 19 quitó un argumento que
> faster-whisper 1.2.1 usa al leer el audio, y la transcripción fallaba con
> `TypeError: open() got an unexpected keyword argument 'metadata_errors'`.

---

## Paso 3. GPU NVIDIA (opcional)

Sin GPU todo funciona igual, pero más lento. Para usar la GPU, instala las
librerías CUDA 12 (cuBLAS y cuDNN 9, ~1,2 GB, solo dentro de `.venv`):

```powershell
uv pip install --python .venv\Scripts\python.exe -e ".[dev,cuda]"
kresolve doctor
```

`doctor` debe mostrar `[OK] GPU 1 GPU CUDA`. kresolve añade solo esas DLL al
buscador de Windows; no hay que tocar el PATH.

Si la GPU falla al transcribir, kresolve lo avisa y **sigue en CPU** sin
detenerse:

```
AVISO: la GPU no está disponible (Library cublas64_12.dll is not found or cannot be loaded).
       Sigo en CPU (int8). ...
```

Modelo según el hardware (`transcriber.model` en `config.yaml`):

| Hardware | Modelo recomendado | Comentario |
|---|---|---|
| GPU con 6 GB o más (p. ej. RTX 3060 Ti) | `large-v3` | La mejor calidad. La primera vez descarga ~3 GB |
| GPU pequeña o CPU potente | `large-v3-turbo` o `medium` | Buen equilibrio |
| CPU modesta | `small` | Rápido; revisa más el JSON |

---

## Paso 4. Revisar `config.yaml`

Los valores importantes:

```yaml
transcriber:
  model: large-v3
  language: es               # idioma fijo: mejor que autodetectar
grouping:
  strategy: per_line         # frase + palabra resaltada
resolve:
  install_dir: "Z:/Programs/Davinci"   # donde está Resolve.exe en este PC
  template: kresolve_template          # nombre de la plantilla del paso 6
style: plantilla             # respeta el diseño de la plantilla
```

Cada clave tiene un comentario en el propio archivo. Si escribes mal una
opción o una estrategia, cualquier comando lo indica al arrancar.

---

## Paso 5. Comprobar la instalación

```powershell
kresolve doctor
pytest
```

Salida esperada de `doctor`, más o menos:

```
[OK] Python           3.12.x (...\.venv\Scripts\python.exe)
[OK] config.yaml      E:\Portafolio - Coding\Davinci FreeSubs\config.yaml
[OK] faster_whisper   1.2.1
[OK] GPU              1 GPU CUDA            (o [--] ... se usará CPU)
[OK] ffmpeg           C:\...\ffmpeg.exe
[OK] fusionscript     Z:\Programs\Davinci\fusionscript.dll
[--] scripts de menú  0/6 en C:\Users\...\Scripts\Utility (kresolve install-scripts)
```

`[!!]` es un error que hay que corregir. `[--]` es opcional o todavía no está
hecho.

Para probar la transcripción sin Resolve, con cualquier vídeo o audio:

```powershell
kresolve extract-audio "C:\ruta\a\video.mp4"
kresolve transcribe work\kresolve_audio.wav --model small
```

---

## Paso 6. Crear la plantilla Text+ en Resolve

kresolve no fija la duración de un título "insertado" en la timeline: copia
una **plantilla Text+ del Media Pool** con la duración y posición exactas que
necesita. Esa plantilla se crea **una vez por proyecto**, y lo que diseñes en
ella es lo que saldrá en cada clip.

1. Abre el proyecto y ve a la página **Edit**.
2. Abre **Effects** (arriba a la izquierda) > **Toolbox** > **Titles** y
   arrastra **Text+** a una pista vacía de la timeline.
3. Con el clip seleccionado, en el **Inspector** > pestaña del título:
   - Escribe un texto de ejemplo ("Texto de prueba") para ver el diseño.
   - Elige la fuente, el estilo, el tamaño y el color **base** (el del texto
     no resaltado).
   - En **Shading**, activa el contorno y la sombra si los quieres.
   - En **Layout**, coloca el texto (p. ej. abajo y centrado).
   - **No** animes nada (sin keyframes) y **no** uses Character Level Styling.
4. **Alarga el clip** en la timeline a 1 minuto o más (arrastra su borde
   derecho). Así las frases largas no se quedan cortas.
5. **Arrastra el clip desde la timeline al Media Pool.** Aparece como un clip
   nuevo.
6. Renómbralo exactamente **`kresolve_template`**: haz clic en el nombre en el
   Media Pool o usa clic derecho > Rename. Si prefieres otro nombre, cambia
   `resolve.template` en `config.yaml`.
7. Ya puedes borrar el clip de la timeline. La plantilla queda en el Media Pool.

Para reutilizarla en otros proyectos, cópiala a un **Power Bin** y arrástrala
desde ahí al Media Pool de cada proyecto.

> **Consejo para `sliding`:** si vas a usar el karaoke acumulado, pon en la
> plantilla el anclaje horizontal a la izquierda (**H Anchor** a la izquierda)
> para que el texto no se recentre con cada palabra nueva.

---

## Paso 7. Instalar los scripts del menú

Con el entorno activado:

```powershell
kresolve install-scripts
```

Se crean 6 scripts en
`%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility`.
Cada uno guarda la ruta del proyecto y la de `.venv\Scripts\python.exe`.

**Reinicia DaVinci Resolve**: solo busca scripts nuevos al arrancar. Después
aparecen en **Workspace (Espacio de trabajo) > Scripts**:

| Script | Qué hace |
|---|---|
| `kresolve 0 - Diagnostico` | Prueba la API en una timeline nueva `kresolve_test` (paso 8) |
| `kresolve 1 - Exportar audio` | Renderiza el audio de la timeline activa en `work\kresolve_audio.wav` |
| `kresolve 2 - Transcribir` | Abre una ventana con el progreso de Whisper y deja `work\transcript.json` |
| `kresolve 3 - Crear titulos` | Crea o rehace los Text+ en las pistas `kresolve` y `kresolve HL` |
| `kresolve 4 - Borrar titulos` | Vacía esas dos pistas |
| `kresolve 5 - Todo (1+2+3)` | Las tres etapas seguidas |

Abre **Workspace > Console** antes de ejecutarlos. Ahí aparece todo lo que
hacen, y los errores con la explicación.

Si mueves la carpeta del proyecto o recreas `.venv`, vuelve a ejecutar
`kresolve install-scripts`.

---

## Paso 8. Diagnóstico en Resolve

Hazlo la primera vez y cada vez que actualices Resolve:

1. Abre un proyecto que tenga la plantilla del paso 6.
2. **Workspace > Scripts > kresolve 0 - Diagnostico**.
3. En la consola verás algo así:

```
[kresolve] DaVinci Resolve 21.2.0.6
[kresolve] Plantilla: "kresolve_template" tipo='Fusion Title'
[kresolve] Timeline de prueba creada: "kresolve_test"
[kresolve] Calibración: recordFrame absoluto (+0), endFrame inclusivo (+0).
[kresolve]   capa base      -> pista V2: 2/2 clips
[kresolve]   capa highlight -> pista V3: 6/6 clips
[kresolve] Tiempo: 1.3 s. OK
[kresolve] DIAGNÓSTICO OK
```

4. Reproduce la timeline `kresolve_test` y comprueba en el visor:
   - Salen dos líneas: "Esto es una prueba" y "de karaoke".
   - En cada momento hay una sola palabra resaltada, **justo encima** de la
     misma palabra de la frase.
5. Vuelve a tu timeline. La de prueba se puede borrar.

Si el resaltado cae una letra antes o después de la palabra, cambia
`resolve.writeon_pad` en `config.yaml`. Prueba con `0.3`, o con
`writeon_count_spaces: false`. Luego repite el diagnóstico. La lista completa
de entradas del nodo Text+ queda en `work\textplus_inputs.txt`.

---

## Paso 9. Flujo de trabajo normal

1. Abre la timeline en la página **Edit** y la consola (**Workspace > Console**).
2. **kresolve 1 - Exportar audio**. Renderiza el audio de toda la timeline.
   Con `resolve.use_in_out: true`, solo el rango In/Out.
   *Ojo:* deja cambiados el nombre y la carpeta de render de la página Deliver.
3. **kresolve 2 - Transcribir**. Se abre una ventana con el progreso. La
   primera vez descarga el modelo (`large-v3` ~3 GB). Al terminar, la ventana
   se cierra; si hay un error, espera a que pulses Enter.
4. *(Opcional)* Corrige `work\transcript.json` ([paso 10](#paso-10-corregir-la-transcripción)).
5. **kresolve 3 - Crear titulos**. Crea dos pistas de vídeo nuevas encima de
   las tuyas:
   - `kresolve`: un Text+ por línea, con el nombre del clip igual a su texto.
   - `kresolve HL`: un Text+ por palabra (clips naranjas) con la palabra
     resaltada.
6. ¿Algo mal? Corrige el JSON y vuelve a ejecutar **3**. Las pistas `kresolve`
   se vacían y se rehacen; no hay que transcribir otra vez.

kresolve **no modifica tus pistas**. Solo escribe en las suyas. Aun así, para
la primera prueba conviene duplicar la timeline.

Los clips son Text+ normales: puedes moverlos, recortarlos y cambiar el texto
o el estilo de cualquiera en el Inspector. Pero si vuelves a ejecutar **3**,
esos cambios se pierden, porque las pistas se regeneran. Haz las correcciones
de texto en el JSON y los retoques a mano al final.

---

## Paso 10. Corregir la transcripción

`work\transcript.json` tiene una palabra por línea:

```json
{
  "version": 1,
  "language": "es",
  "meta": { "...": "..." },
  "segments": [
    {
      "_text": "Hola, esto es una prueba de karaoke en Davin Sirisalve.",
      "words": [
        {"text": "Hola,", "start": 0.000, "end": 0.320, "prob": 0.611},
        {"text": "esto", "start": 0.680, "end": 0.960, "prob": 0.965},
        ...
        {"text": "Davin", "start": 2.580, "end": 2.840, "prob": 0.376},
        {"text": "Sirisalve.", "start": 2.840, "end": 3.560, "prob": 0.689}
      ]
    }
  ]
}
```

(Este ejemplo es real: es la salida del modelo `base` con una frase de prueba
sintetizada. El modelo pequeño confundió "DaVinci Resolve").

Reglas:

- **Cambia `text`** para corregir una palabra. En el ejemplo: `"DaVinci"` y
  `"Resolve."`.
- **Ajusta `start` / `end`** (segundos desde el inicio del audio) si una
  palabra entra antes o después de tiempo.
- **Une palabras** borrando una y alargando el `end` de la otra. **Sepáralas**
  duplicando la línea y repartiendo el tiempo.
- **`_text` no se lee**: se regenera al guardar. Lo que cuenta son `words`.
- `prob` bajo (< 0.7) indica que Whisper dudó: revisa esas palabras primero.
  En el ejemplo, los dos errores tienen 0.376 y 0.689.
- Para **añadir una frase que falta** sin tiempos por palabra, añade un
  segmento con solo `text`, `start` y `end`. kresolve reparte las palabras en
  ese intervalo:

  ```json
  {"text": "frase que faltaba", "start": 12.0, "end": 14.5}
  ```

- Cada segmento es una frase de Whisper. Al crear los títulos se parte en
  líneas según `max_chars`, `max_words` y `max_gap` de `config.yaml`.

Si el archivo tiene un error, el comando lo dice con línea y columna.

Para regenerar los subtítulos tras corregir: `kresolve subs work\transcript.json`.

**Mejorar la transcripción de partida:**

- Pon nombres propios o la letra en `transcriber.initial_prompt`.
- Para canciones: usa un modelo grande. Si se come partes cantadas, prueba
  `vad_filter: false`. Deja `condition_on_previous_text: false`, que evita
  bucles de frases repetidas.
- Una pista de voz limpia (sin música) da tiempos mucho mejores. Exporta el
  audio con la música silenciada si la tienes en otra pista.

---

## Paso 11. Estrategias y estilos

**Estrategia** (`grouping.strategy`, o `--strategy` en la CLI):

| Estrategia | Pistas | Para qué |
|---|---|---|
| `per_line` | `kresolve` + `kresolve HL` | Karaoke clásico: frase + palabra activa en color |
| `per_line_single` | `kresolve` | Subtítulos normales, una frase por clip |
| `per_word` | `kresolve` | Una palabra cada vez (reels/TikTok) |
| `sliding` | `kresolve` (+ `HL`) | Las palabras van apareciendo; `window` = cuántas se ven |

Opciones de tiempo (`grouping.options`): `lead_in` (la línea aparece antes de
cantarla), `hold` (se queda al acabar), `max_gap` (silencio que corta la
línea) y `fill_gaps` (`per_word`: la palabra se mantiene hasta la siguiente).

**Estilo** (`style:` en `config.yaml`, presets en `styles/presets.yaml`):

- `plantilla` (por defecto): respeta la plantilla. Solo define el color de
  resaltado.
- `karaoke_default`: fuerza la fuente Open Sans Bold, el tamaño 0.08, blanco
  y amarillo, abajo.
- `reels`: grande, en mayúsculas y centrado.

En un preset, una clave con valor sobrescribe la plantilla en cada clip, y
una clave ausente o `null` la respeta. Añade tus propios presets copiando uno
existente.

---

## Paso 12. Resolve Studio: todo desde la terminal

Solo en **Studio**: Preferences > System > General > **External scripting
using: Local**. Con Resolve abierto:

```powershell
kresolve doctor --connect     # debe decir [OK] conexión Resolve
kresolve run                  # exportar audio + transcribir + crear títulos
# o por etapas:
kresolve export-audio
kresolve transcribe work\kresolve_audio.wav
kresolve build-titles work\transcript.json --strategy per_word
kresolve clear-titles
```

En la versión gratuita esos comandos responden "No se pudo conectar con
DaVinci Resolve". Es lo esperado: usa los scripts del menú.

---

## Paso 13. Alternativas: overlay con alfa y SRT

**Overlay ProRes 4444 con alfa** (color por palabra garantizado, sin depender de
Text+):

```powershell
kresolve overlay work\transcript.json --fps 25
```

Tarda algo menos que la duración del audio (en este PC, 11 s de 1080p en ~14 s).
La primera vez añade hasta un minuto mientras se crea la caché de fuentes.
Genera `work\overlay.mov` (y `overlay.ass`) con fondo transparente. Impórtalo
al Media Pool y ponlo en una pista por encima del vídeo, empezando en el
primer frame de la timeline. El estilo sale del preset (`font`, `ass_size`,
`outline`, `shadow`, `color`, `highlight_color`, `position`). No es editable
en Resolve: para cambiar un texto, corrige el JSON y vuelve a renderizar.

**SRT:** `work\transcript.srt` se genera siempre. Se importa como pista de
subtítulos (File > Import > Subtitle) si solo necesitas subtítulos normales.

---

## Paso 14. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Los scripts no aparecen en Workspace > Scripts | Reinicia Resolve. Comprueba con `kresolve doctor` que están instalados (`scripts de menú 6/6`). |
| Ejecuto un script y no pasa nada | Abre **Workspace > Console**: toda la salida y los errores salen ahí. |
| `No existe el Python del proyecto` | Moviste la carpeta o recreaste `.venv`. Vuelve a ejecutar `kresolve install-scripts`. |
| `No encuentro la plantilla Text+ "kresolve_template"` | Falta el paso 6 en **este** proyecto, o el nombre no coincide. El mensaje lista los títulos que sí encontró. |
| `El clip de prueba debía durar 12 frames y dura N` | La plantilla no es un Text+ normal. Créala de nuevo con el paso 6 y alárgala antes de arrastrarla. |
| `N con duración distinta` en el resumen | Hay clips más largos que la plantilla. Alarga la plantilla (paso 6.4) y vuelve a crearla. |
| El resaltado no cae sobre la palabra | La plantilla tiene keyframes o Character Level Styling: créala limpia. Si solo se desvía una letra, ajusta `writeon_pad` (paso 8). |
| `No se pudo conectar con DaVinci Resolve` (terminal) | Versión gratuita, o Studio sin *External scripting = Local*. Usa los scripts del menú. |
| `Resolve rechazó la configuración de render de audio` | Renderiza a mano en Deliver: *Audio only*, WAV, nombre `kresolve_audio`, carpeta `work\`. O usa `kresolve extract-audio`. |
| `AVISO: la GPU no está disponible` | Falta el extra `[cuda]` (paso 3). Mientras tanto se usa la CPU. |
| La transcripción tarda mucho | Usa la GPU (paso 3), o `--model small` / `large-v3-turbo`. |
| `metadata_errors` / `TypeError` al transcribir | PyAV 19 o posterior. Reinstala: `uv pip install --python .venv\Scripts\python.exe -e .` (fija `av<19`). |
| La letra sale mal en canciones | Paso 10: `initial_prompt`, `vad_filter: false`, voz sin música, o corrige el JSON. |
| Los títulos aparecen desplazados | ¿Exportaste el audio de otra timeline? El script avisa si no coincide. Con `extract-audio`, el clip debe empezar en el primer frame de la timeline. |
| Aviso de symlinks de Hugging Face | Es inofensivo. Para quitarlo: `setx HF_HUB_DISABLE_SYMLINKS_WARNING 1`. |

---

## Paso 15. Desinstalar

```powershell
kresolve install-scripts --uninstall    # quita los scripts del menú
deactivate
Remove-Item -Recurse -Force .venv, work
```

Los modelos de Whisper están en `%USERPROFILE%\.cache\huggingface\hub`
(`models--Systran--faster-whisper-*`). Bórralos si quieres recuperar espacio.
