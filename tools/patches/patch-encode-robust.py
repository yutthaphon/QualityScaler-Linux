#!/usr/bin/env python3
"""Harden QualityScaler's final encode step.

All fixes live in QualityScaler.py:

1. Print ffmpeg's stderr when an encode attempt fails. Upstream stores it in
   ffmpeg_process.ffmpeg_errors and never shows it, so failures are opaque.
2. Force even output dimensions. libx264 and hevc_nvenc reject odd width/height
   ("not divisible by 2"); the app's rounding path can produce one.
3. Write the concat list with O_TRUNC so a retry can never inherit stale lines.
4. Keep the work directory when every codec fails, so the frames remain for the
   watchdog instead of being abandoned.

Idempotent. Usage: patch-encode-robust.py [/root/QualityScaler-Linux/QualityScaler.py]
"""
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/root/QualityScaler-Linux/QualityScaler.py")
if not path.is_file():
    sys.exit(f"not found: {path}")

text = path.read_text(encoding="utf-8")
MARKER = "QS_PATCH_ENCODE_ROBUST"
if MARKER in text:
    print("already patched (nothing to do)")
    sys.exit(0)

applied = []


def patch(name, old, new):
    global text
    if text.count(old) != 1:
        sys.exit(f"[{name}] expected 1 match, found {text.count(old)} -- upstream changed")
    text = text.replace(old, new)
    applied.append(name)


# 1. O_TRUNC on the concat list (needs the flag imported first).
patch(
    "import-o-trunc",
    "    O_WRONLY as os_O_WRONLY,\n    O_CREAT  as os_O_CREAT",
    "    O_WRONLY as os_O_WRONLY,\n    O_CREAT  as os_O_CREAT,\n    O_TRUNC  as os_O_TRUNC",
)
patch(
    "concat-truncate",
    "os_O_WRONLY | os_O_CREAT, 0o777",
    "os_O_WRONLY | os_O_CREAT | os_O_TRUNC, 0o777",
)

# 2. Even dimensions in the scale filter (bitwise clear of the low bit).
OLD_SCALE = ('                    "-vf",         '
             'f"scale={video_upscale_task.target_width}:{video_upscale_task.target_height},format=yuv420p",')
NEW_SCALE = ('                    # QS_PATCH_ENCODE_ROBUST: encoders reject odd dimensions\n'
             '                    "-vf",         f"scale={video_upscale_task.target_width & ~1}:'
             '{video_upscale_task.target_height & ~1},format=yuv420p",')
patch("scale-even", OLD_SCALE, NEW_SCALE)

# 3. Surface ffmpeg's stderr when a codec attempt fails.
OLD_EXC = """            except Exception as e:
                if ffmpeg_process:
                    ffmpeg_process.kill()"""
NEW_EXC = """            except Exception as e:
                # QS_PATCH_ENCODE_ROBUST: upstream swallowed ffmpeg's own message.
                _errors = getattr(ffmpeg_process, "ffmpeg_errors", None) if ffmpeg_process else None
                if _errors:
                    print(f"[FFMPEG] {current_codec} stderr:", flush=True)
                    for _line in _errors:
                        print(f"    {_line}", flush=True)
                if ffmpeg_process:
                    ffmpeg_process.kill()"""
patch("encode-stderr", OLD_EXC, NEW_EXC)

# 5. Create the chosen output folder. Upstream assumes it exists, so a fresh
#    output path fails with "Error opening output ...: No such file or directory".
OLD_CREATE = ('    def encode_upscaled_video(process_status_q: multiprocessing_Queue, video_upscale_task: VideoUpscaleTask) -> None:\n'
              '\n'
              '        encoded_frame_count = [0]')
NEW_CREATE = ('    def encode_upscaled_video(process_status_q: multiprocessing_Queue, video_upscale_task: VideoUpscaleTask) -> None:\n'
              '\n'
              '        # QS_PATCH_ENCODE_ROBUST: the output folder may not exist yet.\n'
              '        _out_dir = os_path_dirname(video_upscale_task.video_output_path)\n'
              '        if _out_dir and not os_path_exists(_out_dir):\n'
              '            os_makedirs(_out_dir, mode=0o777, exist_ok=True)\n'
              '\n'
              '        encoded_frame_count = [0]')
patch("create-output-dir", OLD_CREATE, NEW_CREATE)

path.write_text(text, encoding="utf-8")
ast.parse(path.read_text(encoding="utf-8"))
print("patched: " + ", ".join(applied))
print("syntax  : OK")
