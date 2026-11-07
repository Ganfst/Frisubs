import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_path() -> Path:
    return FIXTURES / "sample_transcript.json"


@pytest.fixture
def sample(sample_path):
    from kresolve.exporters.json_io import load_transcript
    return load_transcript(sample_path)


@pytest.fixture
def cfg_file(tmp_path) -> Path:
    """config.yaml mínimo en una carpeta temporal (work_dir dentro de ella)."""
    styles = tmp_path / "styles"
    styles.mkdir()
    (styles / "presets.yaml").write_text(
        "plantilla:\n  highlight_color: [1, 0.85, 0.1]\n"
        "mayus:\n  uppercase: true\n  color: [1, 1, 1]\n",
        encoding="utf-8")
    p = tmp_path / "config.yaml"
    p.write_text("grouping:\n  strategy: per_line\n  options:\n    lead_in: 0.2\n    hold: 0.3\n"
                 "output:\n  work_dir: ./work\n", encoding="utf-8")
    return p
