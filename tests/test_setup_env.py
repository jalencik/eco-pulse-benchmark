"""Environment setup must work on a reviewer's machine, not only on ours.

The failure this guards against was not hypothetical. On the Windows dev machine:

  - `uv` had created a managed CPython under %APPDATA%\\Roaming, then left PATH, so the
    environment could be run but not rebuilt;
  - the `py` launcher advertised a 3.12 runtime that failed to start with 0x80070003;
  - the default `python` was a 3.14 Store alias that cannot see %APPDATA%\\Roaming at all,
    so every subprocess into the venv died with a cryptic exit 103.

Each of those is a case where *metadata said yes and execution said no*, which is why
discovery probes by running candidates rather than reading a registry.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import setup_env  # noqa: E402

import tasks  # noqa: E402  (isort: after sys.path mutation)


class TestProbe:
    def test_probe_returns_version_for_a_real_interpreter(self):
        assert setup_env.probe([sys.executable]) == tuple(sys.version_info[:3])

    def test_probe_rejects_a_missing_binary(self):
        assert setup_env.probe(["definitely-not-a-real-binary-xyz"]) is None

    def test_probe_rejects_a_binary_that_exits_nonzero(self):
        """A launcher that resolves to an unopenable path exits nonzero, like py -3.12 did."""
        assert setup_env.probe([sys.executable, "-c", "raise SystemExit(1)", "--"]) is None

    def test_probe_rejects_unparseable_output(self, tmp_path):
        fake = tmp_path / "fake.py"
        fake.write_text("print('not a version')")
        assert setup_env.probe([sys.executable, str(fake)]) is None


class TestDiscovery:
    def test_candidates_are_deduplicated(self):
        cands = setup_env.candidates()
        assert len(cands) == len({tuple(c) for c in cands})

    def test_candidates_always_include_a_fallback(self):
        assert [sys.executable] in setup_env.candidates()

    def test_find_interpreter_returns_a_real_312(self):
        """Whatever it picks must actually run and actually be 3.12."""
        found = setup_env.find_interpreter()
        assert found is not None, "no 3.12 discoverable on this machine"
        assert setup_env.probe(found)[:2] == setup_env.TARGET

    def test_target_matches_pyproject_pin(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert 'requires-python = ">=3.12,<3.13"' in text
        assert setup_env.TARGET == (3, 12)


class TestVenvLayout:
    def test_venv_python_matches_platform_convention(self):
        p = setup_env.venv_python(Path("x"))
        assert p.parts[-2:] == (
            ("Scripts", "python.exe") if sys.platform == "win32" else ("bin", "python")
        )


@pytest.mark.slow
class TestVerifyGuard:
    def test_verify_rejects_an_environment_without_the_package(self, tmp_path):
        """A setup step that reports success without a working import is worse than failing."""
        interp = setup_env.find_interpreter()
        assert interp is not None
        venv = tmp_path / "v"
        subprocess.run([*interp, "-m", "venv", str(venv)], check=True, capture_output=True)
        assert setup_env.verify(str(setup_env.venv_python(venv))) == 2


class TestShimDiagnostics:
    def test_diagnose_passes_on_a_healthy_environment(self):
        """This suite runs under the venv, so the environment must diagnose clean."""
        assert tasks.diagnose() is None

    def test_base_invisible_is_false_for_a_visible_base(self):
        base = subprocess.run(
            [sys.executable, "-c", "import sys;print(sys.base_prefix)"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert not tasks._base_is_invisible(base)

    def test_base_invisible_is_true_for_a_path_that_is_not_there(self, tmp_path):
        assert tasks._base_is_invisible(str(tmp_path / "nope"))

    def test_venv_home_is_read_from_pyvenv_cfg(self):
        """Present iff a venv exists; the diagnostic depends on parsing it correctly."""
        home = tasks._venv_home()
        if (ROOT / ".venv" / "pyvenv.cfg").exists():
            assert home and Path(home).name
        else:
            assert home is None
