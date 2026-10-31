"""Проверить преобразование реальных GIF через стандартные потоки."""

import subprocess
import sys

import pytest
from imageio_ffmpeg import get_ffmpeg_exe

from examples.demo import SAMPLES, make_gif

WEBM_HEADER = bytes.fromhex("1a45dfa3")


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda sample: sample.name)
def test_gif_becomes_readable_webm(sample):
    """Проверить пять разных входов и декодирование результата."""
    result = subprocess.run(
        [sys.executable, "-m", "src.converter"],
        input=make_gif(sample), capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout.startswith(WEBM_HEADER)
    decoded = subprocess.run(
        [get_ffmpeg_exe(), "-v", "error", "-i", "pipe:0",
         "-f", "framecrc", "pipe:1"],
        input=result.stdout, capture_output=True,
    )
    assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")
    frames = [line for line in decoded.stdout.splitlines()
              if line and not line.startswith(b"#")]
    assert len(frames) == len(sample.colors)


def test_invalid_gif_reports_error_on_stderr():
    """Проверить код ошибки и отсутствие диагностик в stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "src.converter"],
        input=b"not a GIF", capture_output=True,
    )
    assert result.returncode != 0
    assert result.stderr
    assert not result.stdout
