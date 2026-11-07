"""Conexión con DaVinci Resolve y acceso a proyecto / timeline / Media Pool.

Tres formas de obtener el objeto ``resolve``, en este orden:

1. Se pasa explícitamente (los scripts de Workspace > Scripts lo reciben como
   variable global y lo entregan aquí).
2. Variable global ``resolve`` / ``bmd`` del script principal.
3. ``DaVinciResolveScript.scriptapp("Resolve")`` desde un Python externo.
   Solo funciona en Resolve **Studio** con Preferences > System > General >
   External scripting using = Local. Si Resolve no está en la ruta por
   defecto, se configura ``RESOLVE_SCRIPT_LIB`` a partir de
   ``resolve.install_dir`` de config.yaml.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ..planning import fps_fraction


class ResolveNotAvailable(RuntimeError):
    pass


NOT_AVAILABLE_HELP = """No se pudo conectar con DaVinci Resolve.
Comprueba:
  1. Resolve está abierto y con un proyecto cargado.
  2. Resolve Studio: Preferences > System > General > External scripting using = Local.
  3. Resolve GRATUITO: no admite scripting externo. Usa los scripts del menú
     Workspace > Scripts (instálalos con: kresolve install-scripts).
  4. Si Resolve no está en la ruta por defecto, pon resolve.install_dir en config.yaml."""


def scripting_api_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
    if sys.platform == "darwin":
        return Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting")
    return Path("/opt/resolve/Developer/Scripting")


def _lib_candidates(install_dir) -> list[Path]:
    names = ["fusionscript.dll"] if sys.platform.startswith("win") else ["fusionscript.so"]
    dirs: list[Path] = []
    if install_dir:
        d = Path(install_dir)
        dirs += [d, d / "Contents" / "Libraries" / "Fusion", d / "libs" / "Fusion"]
    if sys.platform.startswith("win"):
        dirs.append(Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve"))
    elif sys.platform == "darwin":
        dirs.append(Path("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion"))
    else:
        dirs.append(Path("/opt/resolve/libs/Fusion"))
    return [d / n for d in dirs for n in names]


def find_fusionscript(install_dir=None) -> Path | None:
    env = os.environ.get("RESOLVE_SCRIPT_LIB")
    if env and Path(env).is_file():
        return Path(env)
    for c in _lib_candidates(install_dir):
        if c.is_file():
            return c
    return None


def import_dvr(install_dir=None):
    """Importa DaVinciResolveScript configurando las variables de entorno si hace falta."""
    lib = find_fusionscript(install_dir)
    if lib:
        os.environ["RESOLVE_SCRIPT_LIB"] = str(lib)
        if sys.platform.startswith("win"):
            try:
                os.add_dll_directory(str(lib.parent))
            except (OSError, AttributeError):
                pass
    try:
        import DaVinciResolveScript as dvr  # Python integrado de Resolve (21.1+) o PYTHONPATH ya listo
        return dvr
    except ImportError:
        pass
    api = os.environ.get("RESOLVE_SCRIPT_API") or str(scripting_api_dir())
    os.environ["RESOLVE_SCRIPT_API"] = api
    modules = str(Path(api) / "Modules")
    if modules not in sys.path:
        sys.path.append(modules)
    try:
        import DaVinciResolveScript as dvr
    except ImportError as exc:
        raise ResolveNotAvailable(
            f"No se pudo importar DaVinciResolveScript ({exc}).\n"
            f"  RESOLVE_SCRIPT_API={api}\n  RESOLVE_SCRIPT_LIB={os.environ.get('RESOLVE_SCRIPT_LIB')}\n"
            + NOT_AVAILABLE_HELP
        ) from None
    return dvr


def connect(resolve=None, install_dir=None):
    if resolve is not None:
        return resolve
    import __main__
    r = getattr(__main__, "resolve", None)
    if r is not None and hasattr(r, "GetProjectManager"):
        return r
    bmd = getattr(__main__, "bmd", None)
    if bmd is not None:
        r = bmd.scriptapp("Resolve")
        if r:
            return r
    r = import_dvr(install_dir).scriptapp("Resolve")
    if not r:
        raise ResolveNotAvailable(NOT_AVAILABLE_HELP)
    return r


def get_setting(obj, key: str):
    """Timeline/Project: ``GetSettings()`` (21.x) con respaldo a ``GetSetting(key)``."""
    try:
        settings = obj.GetSettings()
        if isinstance(settings, dict) and key in settings:
            return settings[key]
    except Exception:
        pass
    return obj.GetSetting(key)


class ResolveClient:
    def __init__(self, resolve=None, install_dir=None):
        self.resolve = connect(resolve, install_dir)
        self.project = self.resolve.GetProjectManager().GetCurrentProject()
        if not self.project:
            raise ResolveNotAvailable("Resolve está abierto pero no hay ningún proyecto cargado.")
        self.media_pool = self.project.GetMediaPool()
        self.refresh()

    def refresh(self) -> None:
        self.timeline = self.project.GetCurrentTimeline()
        if not self.timeline:
            raise ResolveNotAvailable("No hay timeline activa. Abre la timeline en la página Edit.")

    @property
    def version(self) -> str:
        try:
            return str(self.resolve.GetVersionString())
        except Exception:
            return "?"

    @property
    def product(self) -> str:
        try:
            return str(self.resolve.GetProductName())
        except Exception:
            return "DaVinci Resolve"

    @property
    def fps_raw(self) -> str:
        return str(get_setting(self.timeline, "timelineFrameRate"))

    @property
    def fps(self) -> float:
        return float(fps_fraction(self.fps_raw))

    @property
    def start_frame(self) -> int:
        return int(self.timeline.GetStartFrame())

    @property
    def timeline_name(self) -> str:
        return str(self.timeline.GetName())

    def sec_to_frame(self, sec: float) -> int:
        """Frame absoluto de la timeline. Única conversión s->frame fuera de planning.plan_frames."""
        return self.start_frame + round(sec * self.fps)
