"""Estrategias de agrupación. Importar este paquete las registra todas."""

from . import per_line, per_word, sliding  # noqa: F401
from .base import DEFAULT_OPTIONS, iter_lines, split_segment  # noqa: F401
