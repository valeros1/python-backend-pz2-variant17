"""Преобразовать GIF из стандартного ввода в WebM на стандартном выводе."""

import subprocess
import sys

from imageio_ffmpeg import get_ffmpeg_exe


def _ffmpeg_command(executable: str) -> list[str]:
    """Подготовить команду кодирования с потоковым вводом и выводом."""
    return [
        executable, "-hide_banner", "-loglevel", "error",
        "-f", "gif", "-i", "pipe:0", "-an",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p",
        "-f", "webm", "pipe:1",
    ]


def main() -> int:
    """Передать двоичные потоки FFmpeg и вернуть его код завершения."""
    try:
        command = _ffmpeg_command(get_ffmpeg_exe())
        result = subprocess.run(
            command,
            stdin=sys.stdin.buffer,
            stdout=sys.stdout.buffer,
            stderr=sys.stderr.buffer,
            check=False,
        )
    except (OSError, RuntimeError) as error:
        print(f"Ошибка запуска FFmpeg: {error}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
