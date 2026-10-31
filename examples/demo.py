"""Создать пять GIF, преобразовать их и проверить полученные WebM."""

import io
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from imageio_ffmpeg import get_ffmpeg_exe
from PIL import Image


class Sample(NamedTuple):
    """Размер, кадры и длительности одного демонстрационного GIF."""

    name: str
    size: tuple[int, int]
    colors: tuple[str, ...]
    durations: tuple[int, ...]


SAMPLES = (
    Sample("still", (16, 16), ("red",), (100,)),
    Sample("two_frames", (32, 24), ("red", "blue"), (150, 150)),
    Sample("different_delays", (32, 24),
           ("red", "green", "blue"), (80, 160, 240)),
    Sample("odd_dimensions", (17, 15),
           ("red", "green", "blue", "yellow"), (100,) * 4),
    Sample("eight_frames", (96, 64),
           ("red", "orange", "yellow", "green", "cyan", "blue",
            "purple", "pink"), (70,) * 8),
)


def make_gif(sample: Sample) -> bytes:
    """Сформировать входной GIF в памяти без бинарных файлов в Git."""
    frames = [Image.new("RGB", sample.size, color)
              for color in sample.colors]
    stream = io.BytesIO()
    frames[0].save(
        stream, format="GIF", save_all=True, append_images=frames[1:],
        duration=sample.durations, loop=0,
    )
    return stream.getvalue()


def _check_webm(data: bytes, expected_frames: int) -> None:
    """Проверить декодирование WebM и число кадров."""
    command = [get_ffmpeg_exe(), "-v", "error", "-i", "pipe:0",
               "-f", "framecrc", "pipe:1"]
    result = subprocess.run(command, input=data, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    frames = [line for line in result.stdout.splitlines()
              if line and not line.startswith(b"#")]
    if len(frames) != expected_frames:
        raise RuntimeError("В WebM не сохранилось число кадров GIF")


def main() -> None:
    """Запустить CLI на пяти GIF и сохранить результаты в build/examples."""
    output_dir = Path("build/examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        gif = make_gif(sample)
        result = subprocess.run(
            [sys.executable, "-m", "src.converter"],
            input=gif, capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace"))
        _check_webm(result.stdout, len(sample.colors))
        (output_dir / f"{sample.name}.gif").write_bytes(gif)
        (output_dir / f"{sample.name}.webm").write_bytes(result.stdout)
        print(f"{sample.name}: GIF {len(gif)} байт -> "
              f"WebM {len(result.stdout)} байт")


if __name__ == "__main__":
    main()
