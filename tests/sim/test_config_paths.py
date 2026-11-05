"""Path rules: YAML paths are relative to their file, CLI paths to the current directory, `repo:` to the repo root."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sim.config.loader import load_experiment_spec, load_sweep_spec, resolve_cli_path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_config_loads_the_same_from_any_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _FIXTURES / "dp_small.yaml"

    monkeypatch.chdir(_REPO_ROOT)
    from_root = load_experiment_spec(config_path="tests/fixtures/dp_small.yaml", overrides=[])
    monkeypatch.chdir(_FIXTURES)
    from_fixtures = load_experiment_spec(config_path="dp_small.yaml", overrides=[])
    monkeypatch.chdir(tmp_path)
    from_elsewhere = load_experiment_spec(config_path=str(config), overrides=[])
    from_repo_prefix = load_experiment_spec(config_path="repo:tests/fixtures/dp_small.yaml", overrides=[])

    assert from_root.to_mapping() == from_fixtures.to_mapping() == from_elsewhere.to_mapping() == from_repo_prefix.to_mapping()
    assert Path(from_root.run.results_dir) == _REPO_ROOT / "results"
    assert Path(from_root.run.log_dir) == _REPO_ROOT / "results" / "logs"


def test_cli_path_is_relative_to_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert resolve_cli_path("a/b.yaml") == (tmp_path / "a" / "b.yaml").resolve()
    assert resolve_cli_path("repo:results") == _REPO_ROOT / "results"


def test_yaml_paths_are_relative_to_the_file_that_contains_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Two levels of extends: each file's own relative paths resolve against its own directory.
    _write(
        tmp_path / "base" / "paths.yaml",
        {"extends": (_FIXTURES / "dp_small.yaml").as_posix(), "run": {"log_dir": "logs"}},
    )
    top = _write(
        tmp_path / "exp" / "top.yaml",
        {"extends": "../base/paths.yaml", "run": {"results_dir": "out"}},
    )

    monkeypatch.chdir(_REPO_ROOT)
    spec = load_experiment_spec(config_path=str(top), overrides=[])

    assert Path(spec.run.log_dir) == (tmp_path / "base" / "logs").resolve()
    assert Path(spec.run.results_dir) == (tmp_path / "exp" / "out").resolve()


def test_override_path_is_relative_to_the_top_level_config(tmp_path: Path) -> None:
    top = _write(tmp_path / "exp" / "top.yaml", {"extends": (_FIXTURES / "dp_small.yaml").as_posix()})

    spec = load_experiment_spec(config_path=str(top), overrides=["run.results_dir=out", "run.log_dir=repo:results/x"])

    assert Path(spec.run.results_dir) == (tmp_path / "exp" / "out").resolve()
    assert Path(spec.run.log_dir) == _REPO_ROOT / "results" / "x"


def test_extends_and_summary_out_accept_repo_prefix(tmp_path: Path) -> None:
    top = _write(
        tmp_path / "sweep.yaml",
        {
            "extends": "repo:tests/fixtures/dp_small_sweep.yaml",
            "sweep": {"summary_out": "here/summary.yaml"},
        },
    )

    sweep = load_sweep_spec(str(top))

    assert sweep is not None
    assert Path(sweep.summary_out) == (tmp_path / "here" / "summary.yaml").resolve()


def test_missing_extends_names_the_including_file(tmp_path: Path) -> None:
    top = _write(tmp_path / "top.yaml", {"extends": "nope.yaml"})

    with pytest.raises(FileNotFoundError, match="referenced from .*top.yaml"):
        load_experiment_spec(config_path=str(top), overrides=[])
