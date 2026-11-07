"""Registro de motores de transcripción y estrategias de agrupación por nombre.

Añadir uno nuevo = crear un archivo en ``transcribe/`` o ``grouping/``, decorar
la clase e importarlo en el ``__init__.py`` de esa carpeta.
"""

from __future__ import annotations

TRANSCRIBERS: dict[str, type] = {}
GROUPERS: dict[str, type] = {}


def register_transcriber(name: str):
    def deco(cls):
        TRANSCRIBERS[name] = cls
        return cls
    return deco


def register_grouper(name: str):
    def deco(cls):
        GROUPERS[name] = cls
        return cls
    return deco


def _load_builtin_groupers() -> None:
    from . import grouping  # noqa: F401  (registra per_word, per_line, sliding...)


def _load_builtin_transcribers() -> None:
    # No importa faster_whisper: el motor lo carga al instanciarse.
    from . import transcribe  # noqa: F401


def get_grouper(name: str):
    _load_builtin_groupers()
    try:
        return GROUPERS[name]()
    except KeyError:
        raise KeyError(
            f"Estrategia de agrupación desconocida: {name!r}. Disponibles: {', '.join(sorted(GROUPERS))}"
        ) from None


def get_transcriber_class(name: str) -> type:
    _load_builtin_transcribers()
    try:
        return TRANSCRIBERS[name]
    except KeyError:
        raise KeyError(
            f"Motor de transcripción desconocido: {name!r}. Disponibles: {', '.join(sorted(TRANSCRIBERS))}"
        ) from None


def grouper_names() -> list[str]:
    _load_builtin_groupers()
    return sorted(GROUPERS)
