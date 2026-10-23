"""End-to-end headless check: upscale one image and one video through the real orchestrator.

Run from the repository root (needs FFmpeg and the AI models in AI-onnx/):

    python tools/upscale_smoke.py

Environment switches, all optional:
    CODEC=x264|h264_nvenc   encoder used for the upscaled video
    DEINT=Auto|Bwdif        deinterlacing mode
    INTERLACED=1            generate an interlaced source instead of progressive
    SOURCE=<ffmpeg filter>  lavfi source for the test clip

Writes into a fresh temporary directory and prints every output file it produced.
"""
import os, subprocess, sys, tempfile, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import QualityScaler as q
from multiprocessing import set_start_method

if __name__ == "__main__":
    set_start_method("spawn", force=True)
    work = tempfile.mkdtemp(prefix="qs-e2e-")
    print("work", work, flush=True)

    image_path = os.path.join(work, "still.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x180:duration=1", "-frames:v", "1", image_path], check=True)
    video_path = os.path.join(work, "clip.mp4")
    if os.environ.get("INTERLACED") == "1":
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        os.environ["SOURCE"], "-c:v", "libx264", "-flags", "+ilme+ildct",
                        "-x264opts", "tff=1", "-pix_fmt", "yuv420p", video_path], check=True)
    else:
        source_filter = os.environ.get("SOURCE", "testsrc=size=160x90:rate=10:duration=1")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", source_filter,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", video_path], check=True)

    print("engine:", q.get_AI_engine_info(), "| codecs:", q.video_codec_list, "| cuda filters:", q.CUDA_DEINTERLACE_SUPPORTED, flush=True)
    q.GPU.detect()
    print("gpus:", q.GPU.menu_list(), flush=True)

    manager = q.multiprocessing_Manager()
    status_q = manager.Queue()
    frame_q = manager.Queue(maxsize=64)
    stop_event = manager.Event()
    log_q = manager.Queue(100)

    config = q.ProcessingConfig(
        selected_file_list=[image_path, video_path],
        source_root=None,
        selected_output_path=work,
        selected_AI_model="BSRGANx2",
        selected_AI_multithreading=2,
        input_resize_factor=1.0,
        output_resize_factor=1.0,
        selected_gpu=q.GPU.device_id_for(q.GPU.default()),
        use_nvidia_deinterlace=(os.environ.get("NVIDIA_DEINT", "1") == "1") and q.CUDA_DEINTERLACE_SUPPORTED and q.GPU.detected[0].vendor_id == q.GPU.VENDOR_NVIDIA,
        tiles_resolution=512,
        selected_sharpening_amount=0.0,
        selected_keep_frames=False,
        selected_deinterlace=os.environ.get("DEINT", "Auto"),
        selected_target_resolution="OFF",
        selected_target_ratio="Auto",
        selected_image_extension=".png",
        selected_video_extension=".mp4",
        selected_video_codec=os.environ.get("CODEC", "x264"),
    )

    started = time.time()
    process = q.multiprocessing_Process(target=q.upscale_orchestrator, args=(
        status_q, frame_q, stop_event, log_q,
        config.selected_file_list,
        config.source_root,
        config.selected_output_path,
        config.selected_AI_model,
        config.selected_AI_multithreading,
        config.input_resize_factor,
        config.output_resize_factor,
        config.selected_gpu,
        config.use_nvidia_deinterlace,
        config.tiles_resolution,
        config.selected_sharpening_amount,
        config.selected_keep_frames,
        config.selected_deinterlace,
        config.selected_target_resolution,
        config.selected_target_ratio,
        config.selected_image_extension,
        config.selected_video_extension,
        config.selected_video_codec,
    ))
    process.start()

    last = None
    while process.is_alive() or not status_q.empty():
        try:
            message = status_q.get(timeout=0.5)
        except Exception:
            continue
        print("STATUS:", message, flush=True)
        last = message
        if isinstance(message, str) and (message.startswith("Completed") or message.startswith("Error")):
            break
    process.join(timeout=120)
    print("exitcode", process.exitcode, "elapsed", round(time.time() - started, 1), flush=True)

    for root, _dirs, files in os.walk(work):
        for name in sorted(files):
            path = os.path.join(root, name)
            size = os.path.getsize(path)
            info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,codec_name",
                                   "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
            print(f"{os.path.relpath(path, work):60s} {size:9d} {info}"[:140], flush=True)
