"""Crea los clips Text+ en la timeline. Todo lo frágil de la API vive aquí.

Estrategia (verificada contra la API de Resolve 21.2, ver docs/ANALISIS.md):

1. Plantilla: un Text+ diseñado por el usuario y arrastrado una vez al Media
   Pool (por defecto con el nombre ``kresolve_template``).
2. Cada clip se crea con ``MediaPool.AppendToTimeline`` indicando
   ``trackIndex``, ``recordFrame`` (posición) y ``startFrame``/``endFrame``
   (duración). Así no hace falta mover el cabezal ni recortar después, y no
   se toca ninguna pista del usuario: se crean pistas propias.
3. Antes del lote se inserta un clip de prueba para *calibrar*: se mide si
   ``recordFrame`` es absoluto o relativo y si ``endFrame`` es inclusivo, y se
   corrigen los demás. Después del lote se verifica cada clip y, si alguno
   quedó mal colocado, se recoloca con ``TimelineItem.SetPosition`` (21.1.2+).
4. Para cada clip se abre su comp Fusion y se fija el texto en el nodo Text+.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..models import LAYER_BASE, LAYER_HIGHLIGHT, TitleClip
from ..planning import FrameClip, plan_frames, writeon_range
from .textplus import apply_clip, find_text_tool

BUILDER_DEFAULTS = {
    "template": "kresolve_template",
    "tool_name": "Template",
    "track_name": "kresolve",
    "replace_existing": True,
    "name_clips": True,
    "highlight_clip_color": "Orange",
    "writeon_pad": 0.5,
    "writeon_count_spaces": True,
    "batch_size": 200,
}

PROBE_FRAMES = 12

TEMPLATE_HELP = """No encuentro la plantilla Text+ "{name}" en el Media Pool.
Créala una sola vez (ver docs/GUIA_PASO_A_PASO.md, paso 6):
  1. Página Edit > Effects > Toolbox > Titles > arrastra "Text+" a la timeline.
  2. Diséñalo en el Inspector: fuente, tamaño, color, contorno, sombra, posición.
  3. Alarga el clip en la timeline a 1 minuto o más.
  4. Arrástralo de la timeline al Media Pool y renómbralo exactamente "{name}".
  5. Ya puedes borrarlo de la timeline.
Clips de tipo título encontrados en el Media Pool: {found}"""


class TemplateNotFound(RuntimeError):
    pass


@dataclass
class LayerReport:
    layer: str
    track: int
    requested: int
    created: int = 0
    moved: int = 0
    wrong_duration: int = 0
    no_text_tool: int = 0
    failed_inputs: set = field(default_factory=set)


@dataclass
class BuildReport:
    layers: list[LayerReport] = field(default_factory=list)
    calibration: dict = field(default_factory=dict)
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return all(r.created == r.requested and not r.wrong_duration and not r.no_text_tool
                   and not r.failed_inputs for r in self.layers)

    def summary(self) -> str:
        lines = [f"Calibración: {self.calibration}"]
        for r in self.layers:
            lines.append(f"  capa {r.layer:9s} -> pista V{r.track}: {r.created}/{r.requested} clips"
                         + (f", {r.moved} recolocados" if r.moved else "")
                         + (f", {r.wrong_duration} con duración distinta" if r.wrong_duration else "")
                         + (f", {r.no_text_tool} sin nodo Text+" if r.no_text_tool else "")
                         + (f", entradas no aplicadas: {sorted(r.failed_inputs)}" if r.failed_inputs else ""))
        lines.append(f"Tiempo: {self.elapsed:.1f} s. {'OK' if self.ok else 'REVISAR avisos'}")
        return "\n".join(lines)


def iter_media_pool(folder):
    for clip in folder.GetClipList() or []:
        yield clip
    for sub in folder.GetSubFolderList() or []:
        yield from iter_media_pool(sub)


def clip_type(item) -> str:
    try:
        props = item.GetClipProperty() or {}
        return str(props.get("Type", "")) if isinstance(props, dict) else ""
    except Exception:
        return ""


class TitleBuilder:
    def __init__(self, client, style: dict, options: dict | None = None, log=print):
        self.c = client
        self.style = style or {}
        self.opt = {**BUILDER_DEFAULTS, **{k: v for k, v in (options or {}).items() if v is not None}}
        self.log = log

    # ------------------------------------------------------------ plantilla
    def find_template(self):
        name = str(self.opt["template"])
        titles = []
        for item in iter_media_pool(self.c.media_pool.GetRootFolder()):
            n = str(item.GetName())
            if n.lower() == name.lower():
                return item
            t = clip_type(item)
            if "title" in t.lower() or "fusion" in t.lower():
                titles.append(f"{n} ({t})")
        raise TemplateNotFound(TEMPLATE_HELP.format(name=name, found=", ".join(titles) or "ninguno"))

    # --------------------------------------------------------------- pistas
    def track_names(self) -> dict[str, str]:
        base = str(self.opt["track_name"])
        return {LAYER_BASE: base, LAYER_HIGHLIGHT: base + " HL"}

    def _tracks_named(self, name: str) -> list[int]:
        tl = self.c.timeline
        return [i for i in range(1, int(tl.GetTrackCount("video")) + 1)
                if str(tl.GetTrackName("video", i)) == name]

    def prepare_track(self, name: str) -> int:
        tl = self.c.timeline
        found = self._tracks_named(name)
        if found:
            idx = found[0]
            items = tl.GetItemListInTrack("video", idx) or []
            if items:
                if not self.opt["replace_existing"]:
                    raise RuntimeError(f'La pista "{name}" ya tiene {len(items)} clips. Bórralos ("kresolve 4 - '
                                       'Borrar titulos") o pon resolve.replace_existing: true.')
                tl.DeleteClips(list(items), False)
                self.log(f'Pista V{idx} "{name}": borrados {len(items)} clips anteriores.')
        else:
            if not tl.AddTrack("video"):
                raise RuntimeError("No se pudo añadir una pista de vídeo.")
            idx = int(tl.GetTrackCount("video"))
            tl.SetTrackName("video", idx, name)
            self.log(f'Creada pista V{idx} "{name}".')
        try:
            if tl.GetIsTrackLocked("video", idx):
                tl.SetTrackLock("video", idx, False)
        except Exception:
            pass
        return idx

    def clear(self, delete_tracks: bool = False) -> int:
        tl = self.c.timeline
        removed = 0
        indices = sorted({i for n in self.track_names().values() for i in self._tracks_named(n)}, reverse=True)
        for idx in indices:
            items = tl.GetItemListInTrack("video", idx) or []
            if items:
                tl.DeleteClips(list(items), False)
                removed += len(items)
            if delete_tracks:
                tl.DeleteTrack("video", idx)
        self.log(f"Borrados {removed} clips de {len(indices)} pistas kresolve.")
        return removed

    # ----------------------------------------------------------- calibración
    def _info(self, template, track: int, record: int, duration: int, cal: dict) -> dict:
        return {
            "mediaPoolItem": template,
            "startFrame": 0,
            "endFrame": duration - 1 - cal.get("dur_bias", 0),
            "mediaType": 1,
            "trackIndex": track,
            "recordFrame": record - cal.get("start_bias", 0),
        }

    def calibrate(self, template, track: int, record: int) -> dict:
        info = self._info(template, track, record, PROBE_FRAMES, {})
        items = self.c.media_pool.AppendToTimeline([info]) or []
        item = items[0] if items else None
        if not item:
            raise RuntimeError("AppendToTimeline no creó el clip de prueba. ¿La plantilla es un Text+ del "
                               "Media Pool y la pista no está bloqueada?")
        got_start = int(round(item.GetStart()))
        got_dur = int(round(item.GetDuration()))
        try:
            got_track = int(item.GetTrackTypeAndIndex()[1])
        except Exception:
            got_track = track
        self.c.timeline.DeleteClips([item], False)
        cal = {"start_bias": got_start - record, "dur_bias": got_dur - PROBE_FRAMES}
        if got_track != track:
            raise RuntimeError(f"El clip de prueba fue a la pista V{got_track} en vez de V{track}.")
        if abs(cal["dur_bias"]) > 1:
            raise RuntimeError(
                f"El clip de prueba debía durar {PROBE_FRAMES} frames y dura {got_dur}. "
                "Resolve no respeta startFrame/endFrame con esta plantilla; vuelve a crearla (Text+ normal, "
                "alargado a 1 minuto antes de arrastrarlo al Media Pool).")
        if cal["start_bias"] not in (0, -self.c.start_frame, self.c.start_frame) and abs(cal["start_bias"]) > 2:
            self.log(f"AVISO: desfase de posición inesperado ({cal['start_bias']} frames); se corrige.")
        return cal

    # ------------------------------------------------------------- creación
    def build(self, clips: list[TitleClip], offset_frames: int = 0) -> BuildReport:
        t0 = time.time()
        report = BuildReport()
        if not clips:
            raise ValueError("No hay clips que crear (¿transcripción vacía?).")
        template = self.find_template()
        plans = plan_frames(clips, self.c.fps, self.c.start_frame, offset_frames)
        layers = [layer for layer in (LAYER_BASE, LAYER_HIGHLIGHT) if layer in plans]
        names = self.track_names()
        tracks = {layer: self.prepare_track(names[layer]) for layer in layers}
        if len(layers) == 2 and tracks[LAYER_HIGHLIGHT] < tracks[LAYER_BASE]:
            # Las dos pistas están vacías aquí: basta con intercambiar nombres.
            tl = self.c.timeline
            tracks[LAYER_BASE], tracks[LAYER_HIGHLIGHT] = tracks[LAYER_HIGHLIGHT], tracks[LAYER_BASE]
            for layer in layers:
                tl.SetTrackName("video", tracks[layer], names[layer])
        first = plans[layers[0]][0]
        cal = self.calibrate(template, tracks[layers[0]], first.record_frame)
        report.calibration = cal
        self.log(f"Calibración: recordFrame {'absoluto' if cal['start_bias'] == 0 else 'con desfase'} "
                 f"({cal['start_bias']:+d}), endFrame {'inclusivo' if cal['dur_bias'] == 0 else 'ajustado'} "
                 f"({cal['dur_bias']:+d}).")
        for layer in layers:
            report.layers.append(self._build_layer(template, layer, tracks[layer], plans[layer], cal))
        report.elapsed = time.time() - t0
        return report

    def _build_layer(self, template, layer: str, track: int, plan: list[FrameClip], cal: dict) -> LayerReport:
        rep = LayerReport(layer, track, len(plan))
        self.log(f"Capa {layer}: creando {len(plan)} clips en V{track}...")
        expected = {fc.record_frame: fc for fc in plan}
        pairs: list[tuple] = []
        stray = []
        size = max(1, int(self.opt["batch_size"]))
        for i in range(0, len(plan), size):
            chunk = plan[i:i + size]
            infos = [self._info(template, track, fc.record_frame, fc.duration, cal) for fc in chunk]
            items = self.c.media_pool.AppendToTimeline(infos) or []
            for it in items:
                if not it:
                    continue
                fc = expected.pop(int(round(it.GetStart())), None)
                if fc is None:
                    stray.append(it)
                else:
                    pairs.append((it, fc))
        # Clips colocados donde no tocaba: se emparejan por orden y se recolocan.
        for it, fc in zip(stray, sorted(expected.values(), key=lambda f: f.record_frame)):
            try:
                if it.SetPosition({"trackIndex": track, "startFrame": fc.record_frame}):
                    rep.moved += 1
            except Exception:
                pass
            pairs.append((it, fc))
        rep.created = len(pairs)
        self._fill(pairs, layer, rep)
        return rep

    def _fill(self, pairs, layer: str, rep: LayerReport) -> None:
        highlight = layer == LAYER_HIGHLIGHT
        pad = float(self.opt["writeon_pad"])
        count_spaces = bool(self.opt["writeon_count_spaces"])
        for n, (it, fc) in enumerate(pairs, 1):
            if int(round(it.GetDuration())) != fc.duration:
                rep.wrong_duration += 1
            comp = it.GetFusionCompByIndex(1)
            tool = find_text_tool(comp, str(self.opt["tool_name"]))
            if tool is None:
                rep.no_text_tool += 1
                continue
            clip = fc.clip
            writeon = None
            if highlight and clip.highlight_span is not None:
                writeon = writeon_range(clip.text, clip.highlight_span, pad, count_spaces)
            locked = False
            try:
                comp.Lock()
                locked = True
            except Exception:
                pass
            try:
                rep.failed_inputs.update(apply_clip(tool, clip.text, self.style, highlight=highlight,
                                                    writeon=writeon))
            finally:
                if locked:
                    comp.Unlock()
            if self.opt["name_clips"]:
                label = clip.words[clip.highlight_index] if highlight and clip.highlight_index is not None \
                    else clip.text
                try:
                    it.SetName(label[:60])
                except Exception:
                    pass
            if highlight and self.opt["highlight_clip_color"]:
                try:
                    it.SetClipColor(str(self.opt["highlight_clip_color"]))
                except Exception:
                    pass
            if n % 50 == 0 or n == len(pairs):
                self.log(f"  {layer}: {n}/{len(pairs)}")
