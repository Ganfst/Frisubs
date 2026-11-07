"""Diagnóstico dentro de Resolve: comprueba la API real en una timeline de prueba.

Crea una timeline nueva ``kresolve_test`` con una frase de ejemplo usando la
misma ruta de código que build-titles, verifica posiciones y duraciones y
vuelca la lista de entradas del nodo Text+ a ``work/textplus_inputs.txt``.
No toca la timeline del usuario.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..grouping.per_line import PerLine
from ..models import Segment, Transcript, Word
from .textplus import find_text_tool, get_input, list_inputs
from .title_builder import TemplateNotFound, TitleBuilder, clip_type

SAMPLE = [("Esto", 0.5, 0.9), ("es", 0.9, 1.2), ("una", 1.2, 1.6), ("prueba", 1.6, 2.4),
          ("de", 2.6, 2.8), ("karaoke", 2.8, 3.8)]


def sample_transcript() -> Transcript:
    return Transcript("es", [Segment([Word(t, s, e) for t, s, e in SAMPLE])])


def run_diagnostics(client, resolve_opts: dict, style: dict, work_dir, log=print) -> bool:
    log(f"{client.product} {client.version}")
    log(f"Proyecto: {client.project.GetName()} | timeline: {client.timeline_name} | "
        f"fps: {client.fps_raw} ({client.fps:.5f}) | frame inicial: {client.start_frame}")
    builder = TitleBuilder(client, style, resolve_opts, log)
    try:
        template = builder.find_template()
    except TemplateNotFound as exc:
        log(str(exc))
        return False
    log(f'Plantilla: "{template.GetName()}" tipo={clip_type(template)!r}')

    mp = client.media_pool
    name = "kresolve_test"
    tl = mp.CreateEmptyTimeline(name) or mp.CreateEmptyTimeline(f"{name}_{time.strftime('%H%M%S')}")
    if not tl:
        log("No se pudo crear la timeline de prueba.")
        return False
    client.project.SetCurrentTimeline(tl)
    client.refresh()
    log(f'Timeline de prueba creada: "{client.timeline_name}"')

    # max_words=4 parte la frase en dos líneas: también prueba el corte de líneas.
    clips = PerLine().group(sample_transcript(), hold=0.5, max_words=4)
    report = builder.build(clips)
    log(report.summary())

    out = Path(work_dir) / "textplus_inputs.txt"
    tracks = builder._tracks_named(builder.track_names()["base"])
    items = client.timeline.GetItemListInTrack("video", tracks[0]) if tracks else []
    if items:
        tool = find_text_tool(items[0].GetFusionCompByIndex(1), str(builder.opt["tool_name"]))
        if tool is not None:
            rows = list_inputs(tool)
            out.write_text("\n".join(f"{i}\t{n}\t{t}" for i, n, t in rows), encoding="utf-8")
            log(f"Entradas del Text+ ({len(rows)}) guardadas en {out}")
            for key in ("StyledText", "Font", "Size", "Center", "Start", "End", "Red1"):
                log(f"  {key} = {get_input(tool, key)!r}")
    log("")
    log("Revisa la timeline de prueba en el visor:")
    log('  - "Esto es una prueba" y "de karaoke" deben aparecer como dos líneas.')
    log("  - En cada momento solo la palabra que suena debe verse resaltada, justo encima.")
    log("  Si el resaltado cae una letra antes o después, ajusta resolve.writeon_pad en config.yaml.")
    log("Después vuelve a tu timeline (puedes borrar la de prueba).")
    return report.ok
