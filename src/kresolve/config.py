"""Carga y valida config.yaml (y styles/presets.yaml).

Orden de búsqueda del archivo de configuración:
1. ruta explícita (``--config``)
2. variable de entorno ``KRESOLVE_CONFIG``
3. ``./config.yaml`` en el directorio actual
4. ``config.yaml`` en la raíz del proyecto (junto a ``src/``)

Las rutas relativas dentro del archivo se resuelven respecto a la carpeta
del propio config.yaml, no respecto al directorio actual.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .planning import STYLE_DEFAULTS, resolve_style

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULTS: dict = {
    "transcriber": {
        "engine": "faster-whisper",
        "model": "large-v3",
        "device": "auto",
        "compute_type": "auto",
        "language": "es",
        "vad_filter": True,
        "beam_size": 5,
        "condition_on_previous_text": False,
        "initial_prompt": None,
        "download_root": None,
    },
    "grouping": {"strategy": "per_line", "options": {}},
    # transcript.json se guarda siempre: es el punto de corte del pipeline.
    "output": {"work_dir": "./work", "save_srt": True, "save_ass": False},
    "style": "plantilla",
    "styles_file": "./styles/presets.yaml",
    "resolve": {
        "install_dir": None,
        "template": "kresolve_template",
        "tool_name": "Template",
        "track_name": "kresolve",
        "replace_existing": True,
        "use_in_out": False,
        "audio_name": "kresolve_audio",
        "name_clips": True,
        "highlight_clip_color": "Orange",
        "writeon_pad": 0.5,
        "writeon_count_spaces": True,
    },
    "overlay": {"width": 1920, "height": 1080, "fps": None},
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_mapping(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return json.loads(text) or {}
    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            f"Para leer {path.name} hace falta PyYAML (pip install pyyaml). "
            "Instala el proyecto con: pip install -e ."
        ) from None
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: se esperaba un diccionario en la raíz del YAML")
    return data


def find_config(explicit: str | os.PathLike | None = None) -> Path | None:
    candidates = []
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FileNotFoundError(f"No existe el archivo de configuración: {p}")
        return p.resolve()
    if os.environ.get("KRESOLVE_CONFIG"):
        candidates.append(Path(os.environ["KRESOLVE_CONFIG"]))
    candidates += [Path.cwd() / "config.yaml", PROJECT_ROOT / "config.yaml"]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


@dataclass
class Config:
    data: dict
    base_dir: Path
    path: Path | None = None

    @classmethod
    def load(cls, explicit=None) -> "Config":
        path = find_config(explicit)
        raw = _read_mapping(path) if path else {}
        cfg = cls(_deep_merge(DEFAULTS, raw), path.parent if path else Path.cwd(), path)
        cfg.validate()
        return cfg

    # ------------------------------------------------------------ accesos
    def section(self, name: str) -> dict:
        return self.data.get(name) or {}

    def resolve_path(self, value) -> Path:
        p = Path(os.path.expandvars(os.path.expanduser(str(value))))
        return p if p.is_absolute() else (self.base_dir / p).resolve()

    @property
    def work_dir(self) -> Path:
        d = self.resolve_path(self.section("output").get("work_dir") or "./work")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def work_file(self, name: str) -> Path:
        return self.work_dir / name

    @property
    def strategy(self) -> str:
        return str(self.section("grouping").get("strategy") or "per_line")

    @property
    def grouping_options(self) -> dict:
        return dict(self.section("grouping").get("options") or {})

    def presets(self) -> dict:
        path = self.resolve_path(self.data.get("styles_file") or "./styles/presets.yaml")
        if not path.is_file():
            return {"plantilla": {}}
        data = _read_mapping(path)
        data.setdefault("plantilla", {})
        return data

    def style(self, name: str | None = None) -> dict:
        return resolve_style(self.presets(), name or str(self.data.get("style") or "plantilla"))

    # ---------------------------------------------------------- validación
    def validate(self) -> None:
        from .grouping.base import DEFAULT_OPTIONS
        from .registry import grouper_names
        names = grouper_names()
        if self.strategy not in names:
            raise ValueError(f"grouping.strategy = {self.strategy!r} no existe. Opciones: {', '.join(names)}")
        unknown = set(self.grouping_options) - set(DEFAULT_OPTIONS)
        if unknown:
            raise ValueError(f"grouping.options tiene claves desconocidas: {', '.join(sorted(unknown))}")
        unknown_style = set()
        for name, preset in self.presets().items():
            unknown_style |= {f"{name}.{k}" for k in (preset or {}) if k not in STYLE_DEFAULTS}
        if unknown_style:
            raise ValueError(f"styles: claves desconocidas: {', '.join(sorted(unknown_style))}")

    def to_json_dict(self) -> dict:
        """Configuración resuelta (rutas absolutas) para el lado Resolve."""
        d = copy.deepcopy(self.data)
        d["_config_path"] = str(self.path) if self.path else None
        d["_work_dir"] = str(self.work_dir)
        d["_style"] = self.style()
        return d
