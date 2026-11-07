"""Instala los scripts de menú (Workspace > Scripts) en la carpeta de usuario de Resolve.

Cada script es un lanzador mínimo que añade ``src/`` al ``sys.path`` y llama a
``kresolve.resolve.menu.run``. Funcionan en Resolve gratuito y en Studio.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPTS = [
    ("kresolve 0 - Diagnostico", "diagnose"),
    ("kresolve 1 - Exportar audio", "export-audio"),
    ("kresolve 2 - Transcribir", "transcribe"),
    ("kresolve 3 - Crear titulos", "build-titles"),
    ("kresolve 4 - Borrar titulos", "clear"),
    ("kresolve 5 - Todo (1+2+3)", "all"),
]

STUB = '''# Generado por "kresolve install-scripts". Ejecútalo desde Workspace > Scripts.
# Si mueves el proyecto o el entorno virtual, vuelve a ejecutar: kresolve install-scripts
PROJECT_DIR = {project_dir!r}
PYTHON_EXE = {python_exe!r}
ACTION = {action!r}

import os
import sys

_src = os.path.join(PROJECT_DIR, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
for _m in [m for m in list(sys.modules) if m == "kresolve" or m.startswith("kresolve.")]:
    del sys.modules[_m]  # recarga el código por si lo has editado

from kresolve.resolve.menu import run

run(ACTION, resolve=globals().get("resolve"), project_dir=PROJECT_DIR, python_exe=PYTHON_EXE)
'''


def user_scripts_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility"
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve"
                / "Fusion" / "Scripts" / "Utility")
    return Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / "Scripts" / "Utility"


def install(project_dir, python_exe, target=None) -> list[Path]:
    target = Path(target) if target else user_scripts_dir()
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for title, action in SCRIPTS:
        path = target / f"{title}.py"
        path.write_text(STUB.format(project_dir=str(Path(project_dir).resolve()),
                                    python_exe=str(python_exe), action=action), encoding="utf-8")
        written.append(path)
    return written


def uninstall(target=None) -> list[Path]:
    target = Path(target) if target else user_scripts_dir()
    removed = []
    for title, _ in SCRIPTS:
        path = target / f"{title}.py"
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def installed(target=None) -> list[Path]:
    target = Path(target) if target else user_scripts_dir()
    return [target / f"{t}.py" for t, _ in SCRIPTS if (target / f"{t}.py").exists()]
