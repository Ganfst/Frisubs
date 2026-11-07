"""Acceso a la herramienta Text+ (``TextPlus``) dentro de la comp de un clip.

IDs de entrada según Developer/Fusion/FusionToolReference.md (Resolve 21.2):
``StyledText``, ``Font``, ``Style``, ``Size``, ``Red1/Green1/Blue1`` (relleno),
``Center`` (Layout, punto [x, y]) y ``Start``/``End`` (Write On, 0..1).

Character Level Styling (color por rango de caracteres) NO es scriptable según
esa misma referencia; por eso el resaltado se hace con una segunda capa que
usa Write On para mostrar solo la palabra activa.
"""

from __future__ import annotations


def find_text_tool(comp, preferred: str = "Template"):
    """Nodo Text+ de la comp: por nombre (la plantilla por defecto se llama
    "Template") o, si no, el primero de tipo TextPlus."""
    if comp is None:
        return None
    tool = comp.FindTool(preferred) if preferred else None
    if tool:
        return tool
    try:
        tools = comp.GetToolList(False, "TextPlus") or {}
    except Exception:
        tools = {}
    for key in sorted(tools):
        return tools[key]
    return None


def set_input(tool, name: str, value) -> bool:
    try:
        r = tool.SetInput(name, value)
        return r is not False
    except Exception:
        try:
            setattr(tool, name, value)
            return True
        except Exception:
            return False


def get_input(tool, name: str):
    try:
        return tool.GetInput(name)
    except Exception:
        return None


def apply_clip(tool, text: str, style: dict, *, highlight: bool = False,
               writeon: tuple[float, float] | None = None) -> list[str]:
    """Aplica texto, estilo y (opcional) rango Write On. Devuelve las entradas que fallaron."""
    failed: list[str] = []

    def put(name, value):
        if not set_input(tool, name, value):
            failed.append(name)

    put("StyledText", text)
    if style.get("font"):
        put("Font", style["font"])
    if style.get("style"):
        put("Style", style["style"])
    if style.get("size") is not None:
        put("Size", float(style["size"]))
    if style.get("position"):
        x, y = style["position"][:2]
        put("Center", [float(x), float(y)])
    color = style.get("highlight_color") if highlight else style.get("color")
    if color:
        r, g, b = (float(c) for c in list(color)[:3])
        put("Red1", r)
        put("Green1", g)
        put("Blue1", b)
    if writeon:   # en los clips base no se toca: se respeta la plantilla
        put("Start", float(writeon[0]))
        put("End", float(writeon[1]))
    return failed


def list_inputs(tool) -> list[tuple[str, str, str]]:
    """(ID, nombre, tipo) de todas las entradas del nodo, para diagnóstico."""
    out = []
    try:
        inputs = tool.GetInputList() or {}
    except Exception:
        return out
    for key in sorted(inputs):
        try:
            attrs = inputs[key].GetAttrs() or {}
        except Exception:
            continue
        out.append((str(attrs.get("INPS_ID", "?")), str(attrs.get("INPS_Name", "")),
                    str(attrs.get("INPS_DataType", ""))))
    return out
