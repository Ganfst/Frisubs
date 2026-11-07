import json
import subprocess
import sys
import textwrap

import pytest
from typer.testing import CliRunner

from conftest import ROOT, SRC
from kresolve.cli import app
from kresolve.config import Config
from kresolve.resolve import install

runner = CliRunner()


def test_repo_config_is_valid():
    cfg = Config.load(ROOT / "config.yaml")
    assert cfg.strategy == "per_line"
    assert cfg.style()["name"] == "plantilla"
    assert {"plantilla", "karaoke_default", "reels"} <= set(cfg.presets())


def test_relative_paths_resolve_from_config_dir(cfg_file):
    cfg = Config.load(cfg_file)
    assert cfg.work_dir == (cfg_file.parent / "work").resolve()
    assert cfg.grouping_options["lead_in"] == 0.2
    assert cfg.section("transcriber")["model"] == "large-v3"        # valor por defecto


def test_invalid_values_are_reported(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("grouping:\n  strategy: nope\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no existe"):
        Config.load(p)
    p.write_text("grouping:\n  options:\n    max_charz: 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_charz"):
        Config.load(p)


def test_cli_plan_and_subs(cfg_file, sample_path, tmp_path):
    out = tmp_path / "plan.json"
    r = runner.invoke(app, ["-c", str(cfg_file), "plan", str(sample_path), "--out", str(out), "--style", "mayus"])
    assert r.exit_code == 0, r.output
    plan = json.loads(out.read_text(encoding="utf-8"))
    assert plan["strategy"] == "per_line" and plan["style"]["name"] == "mayus"
    assert plan["clips"][0]["text"].startswith("HOLA QUE TAL")
    assert {c["layer"] for c in plan["clips"]} == {"base", "highlight"}

    local = tmp_path / "t.json"
    local.write_text(sample_path.read_text(encoding="utf-8"), encoding="utf-8")
    r = runner.invoke(app, ["-c", str(cfg_file), "subs", str(local)])
    assert r.exit_code == 0, r.output
    assert local.with_suffix(".srt").exists() and local.with_suffix(".ass").exists()


def test_cli_dump_config_is_json(cfg_file):
    r = runner.invoke(app, ["-c", str(cfg_file), "dump-config"])
    assert r.exit_code == 0, r.output
    d = json.loads(r.stdout)
    assert d["_style"]["name"] == "plantilla" and d["_work_dir"].endswith("work")


def test_install_scripts_writes_valid_stubs(tmp_path):
    paths = install.install(ROOT, sys.executable, tmp_path)
    assert len(paths) == len(install.SCRIPTS)
    for p in paths:
        compile(p.read_text(encoding="utf-8"), str(p), "exec")
    assert "build-titles" in (tmp_path / "kresolve 3 - Crear titulos.py").read_text(encoding="utf-8")
    assert len(install.uninstall(tmp_path)) == len(paths)


def test_resolve_side_needs_only_stdlib():
    """Lo que corre dentro de Resolve no puede importar dependencias de pip."""
    code = textwrap.dedent(f"""
        import sys, importlib.abc
        BLOCK = {{"yaml", "typer", "faster_whisper", "ctranslate2", "numpy", "av", "click", "rich"}}
        class Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name.split(".")[0] in BLOCK:
                    raise ImportError("bloqueado: " + name)
        sys.meta_path.insert(0, Blocker())
        sys.path.insert(0, {str(SRC)!r})
        import kresolve.resolve.menu, kresolve.resolve.diagnostics, kresolve.resolve.install
        import kresolve.grouping, kresolve.exporters.json_io, kresolve.planning
        print("ok")
    """)
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
