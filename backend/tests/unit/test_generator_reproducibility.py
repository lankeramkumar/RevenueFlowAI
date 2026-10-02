"""Byte-reproducibility test: same seed/args/as-of must yield identical CSV bytes."""

import subprocess
import sys
from pathlib import Path


def _run_generate(output_dir: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "revenueflowai.seed", "generate",
            "--profile", "small", "--seed", "42", "--as-of", "2026-10-02",
            "--output", str(output_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_small_profile_is_byte_reproducible(tmp_path):
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    _run_generate(run1)
    _run_generate(run2)

    files1 = sorted(p.name for p in run1.iterdir())
    files2 = sorted(p.name for p in run2.iterdir())
    assert files1 == files2

    for name in files1:
        assert (run1 / name).read_bytes() == (run2 / name).read_bytes(), f"{name} differs between runs"
