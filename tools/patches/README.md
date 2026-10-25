# Local patches applied to `QualityScaler.py`

This fork carries three changes on top of upstream. `QualityScaler.py` in the
repository root is already patched; the scripts in this folder exist so the same
changes can be re-applied after an upstream update. Each script is idempotent
and refuses to run when the anchor it expects is missing, so a silent
mis-patch is not possible.

Deliberately **not** included: any default output path and any temp/work folder
override. Output resolution and work directory follow upstream behaviour
(same folder as the input, or the folder chosen in the GUI).

```bash
git checkout upstream/main -- QualityScaler.py
python3 tools/patches/patch-batch-continue.py
python3 tools/patches/patch-encode-robust.py
python3 tools/patches/patch-concurrent.py
```

## patch-batch-continue.py — one bad file must not end the batch

Upstream wraps the whole file loop in a single `try/except`, so a failure on
file 3 of 189 aborts the remaining 186. This wraps each file instead: the error
is reported and the run continues to the next file. Pressing STOP still stops
everything, because the stop event is re-raised.

## patch-encode-robust.py — make encode failures diagnosable and survivable

| # | Upstream behaviour | After patch |
|---|---|---|
| 1 | concat list opened with `O_CREAT` but no `O_TRUNC` | truncated, so a retry cannot inherit stale entries |
| 2 | output folder must already exist | created from the output file path |
| 3 | `scale=W:H` can produce odd dimensions, which libx264 and hevc_nvenc reject | dimensions forced even (`& ~1`) |
| 4 | ffmpeg's stderr is captured into `ffmpeg_errors` and never shown, so every failure is a bare exit code | printed per codec attempt |

## patch-concurrent.py — process several files at once

Adds a **Concurrent** menu next to *Threads*:

| Concurrent | threads per task | workers total |
|---|---|---|
| `OFF` | 8 | 8 |
| `2 tasks` | 4 | 8 |
| `3 tasks` | 2 | 6 |

`Threads` is a total budget that is divided across the tasks, so the number of
ONNX sessions — and therefore VRAM use — stays roughly constant. The batch
orchestrator splits the file list across worker processes that share one status
queue, so there is still a single log, a single output folder and unchanged
resume behaviour.

Measured on a 48-core host with an RTX 5090, 854x470 sources scaled to 4K:

| Setting | per episode |
|---|---|
| 1 task, 8 threads | 15m49s |
| 2 tasks, 4 threads each | 11m37s (1.36x) |

The gain comes from encode overlapping the other task's upscale: NVENC leaves
the GPU idle while it runs.

Note: workers communicate through a `Manager().Queue()` proxy, not a raw
`Queue`. A raw queue can only reach a `Pool` worker through inheritance, which
`spawn` does not provide, and doing so fails with *"Queue objects should only be
shared between processes through inheritance"*.
