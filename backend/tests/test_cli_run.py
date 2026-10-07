"""Tests for arc run: parsing, config errors, non-blocking execution."""

from pathlib import Path

from arc.cli.main import build_parser, run
from tests.conftest import write_contract


def test_run_parser_defaults() -> None:
    """run accepts optional contracts dir and interval."""
    args = build_parser().parse_args(["run"])

    assert args.command == "run"
    assert args.contracts is None
    assert args.interval == 5.0


def test_run_rejects_empty_directory(tmp_path: Path) -> None:
    """No contracts means refusal, not an idle loop."""
    assert run(["run", "--contracts", str(tmp_path)]) == 2


def test_run_rejects_bad_interval(tmp_path: Path) -> None:
    """Non-positive intervals fail fast with exit code 2."""
    write_contract(tmp_path, "relief.yaml")

    assert run(["run", "--contracts", str(tmp_path), "--interval", "0"]) == 2


def test_run_executes_one_step_then_shuts_down(tmp_path: Path, monkeypatch, capsys) -> None:
    """The runner wires engine start, steps, and shutdown without hanging."""
    import arc.cli.main as cli_main

    write_contract(tmp_path, "relief.yaml")
    stepped = {"count": 0}

    async def fake_serve(engine):
        engine.step()
        stepped["count"] += 1

    monkeypatch.setattr(cli_main, "_serve", fake_serve)

    code = run(["run", "--contracts", str(tmp_path), "--interval", "5"])

    assert code == 0
    assert stepped["count"] == 1
    out = capsys.readouterr().out
    assert "ARC engine starting" in out
    assert "loaded: compile-relief" in out
    assert "ARC engine stopped" in out


def test_run_reports_keyboard_interrupt(tmp_path: Path, monkeypatch, capsys) -> None:
    """Ctrl+C during serving still reaches shutdown cleanly."""

    import arc.cli.main as cli_main

    write_contract(tmp_path, "relief.yaml")

    async def raising_serve(engine):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_main, "_serve", raising_serve)

    code = run(["run", "--contracts", str(tmp_path)])

    assert code == 0
    assert "interrupted" in capsys.readouterr().out
