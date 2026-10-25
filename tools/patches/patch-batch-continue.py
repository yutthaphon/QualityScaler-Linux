#!/usr/bin/env python3
"""Make QualityScaler continue with the next file when one file fails.

Upstream wraps the entire batch in a single try/except, so one encode failure
ends a 189-file run. This patch wraps each file's work in its own try/except:
the failing file is reported and skipped, its frames stay in the work directory
for recovery, and the remaining files still run.

Idempotent. Usage: patch-batch-continue.py [/root/QualityScaler-Linux/QualityScaler.py]
"""
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/root/QualityScaler-Linux/QualityScaler.py")
if not path.is_file():
    sys.exit(f"not found: {path}")

text = path.read_text(encoding="utf-8")
MARKER = "QS_PATCH_BATCH_CONTINUE"

if MARKER in text:
    print("already patched (nothing to do)")
    sys.exit(0)

LOOP_HEAD = "        for file_number in range(how_many_files):"
COMPLETION = ('        if not event_stop_upscale_process.is_set(): '
              'write_process_status(process_status_q, f"{COMPLETED_STATUS}")')
DISPATCH = "            if check_if_file_is_video(file_path):"

start = text.find(LOOP_HEAD)
end = text.find(COMPLETION)
if start == -1 or end == -1 or end <= start:
    sys.exit("orchestrator loop not found -- upstream changed")

body = text[start:end]
split = body.find(DISPATCH)
if split == -1:
    sys.exit("video/image dispatch not found -- upstream changed")

preamble = body[:split]          # header, per-file variables, FileNotFoundError guard
dispatch = body[split:]          # the actual video/image work

# Guard the FileNotFoundError too: wrap from the os_path_exists check onwards.
guard = preamble.find("            if not os_path_exists(file_path):")
if guard == -1:
    sys.exit("file-existence guard not found -- upstream changed")

head = preamble[:guard]
inside = preamble[guard:] + dispatch

indented = "".join(
    ("    " + line if line.strip() else line) for line in inside.splitlines(keepends=True)
)

new_block = (
    head
    + "            # " + MARKER + ": one bad file must not end the whole run.\n"
    + "            try:\n"
    + indented
    + "            except Exception as file_error:\n"
    + "                if event_stop_upscale_process.is_set():\n"
    + "                    raise\n"
    + '                write_process_status(process_status_q, f"{ERROR_STATUS} [{file_number}] '
      '{os_path_basename(file_path)}: {file_error}")\n'
    + '                print(f"[Batch] file {file_number} failed, continuing: {file_error}", flush=True)\n'
    + "                continue\n\n"
)

text = text[:start] + new_block + text[end:]
path.write_text(text, encoding="utf-8")

ast.parse(path.read_text(encoding="utf-8"))
print("patched: per-file isolation (batch continues after a failure)")
print("syntax  : OK")
