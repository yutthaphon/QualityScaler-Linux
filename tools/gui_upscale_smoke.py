"""End-to-end GUI check: load files, press UPSCALE, wait for the batch to finish.

Run from the repository root under a display (or `xvfb-run -a python tools/gui_upscale_smoke.py`).
Creates its test image and clip with FFmpeg, upscales them through the real GUI
code path and prints the produced files and the final status message.
"""
import os, subprocess, sys, tempfile, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

def main():
    work = tempfile.mkdtemp(prefix="qs-gui-")
    image_path = os.path.join(work, "photo.png")
    video_path = os.path.join(work, "clip.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x180:duration=1", "-frames:v", "1", image_path], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=160x90:rate=10:duration=1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", video_path], check=True)
    os.makedirs(os.path.join(work, "out"), exist_ok=True)

    if True:
        import QualityScaler as q
        from QualityScaler import App, AppState, UserPreferences

        q.multiprocessing_set_start_method("spawn", force=True)
        q.set_appearance_mode("Dark")
        q.set_default_color_theme("dark-blue")
        q.apply_app_zoom(1.0)

        manager = q.multiprocessing_Manager()
        q.app_state = AppState(preferences=UserPreferences())
        q.app_state.ui_jobs = q.BackgroundJobs()
        q.app_state.process_status_q = manager.Queue()
        q.app_state.process_log_q = manager.Queue(1000)
        q.app_state.video_frames_and_info_q = manager.Queue(64)
        q.app_state.event_stop_upscale_process = manager.Event()
        q.configure_realtime_logging(q.app_state.process_log_q)

        root = q.CTk()
        q.app_state.window = root
        q.app_state.info_message = q.StringVar(master=root)
        q.app_state.selected_output_path = q.StringVar(master=root, value=os.path.join(work, "out"))
        q.app_state.selected_input_resize_factor = q.StringVar(master=root, value="50")
        q.app_state.selected_output_resize_factor = q.StringVar(master=root, value="100")
        q.app_state.selected_VRAM_limiter = q.StringVar(master=root, value="6")
        q.app_state.selected_video_codec = q.StringVar(master=root, value="x264")
        for size in (8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24):
            setattr(q, f"bold{size}", q.CTkFont(family=q.platform_services.ui_font_family(), size=size, weight="bold"))
        for name in ("clear_icon", "logo_git", "logo_telegram", "log_icon", "stop_icon", "upscale_icon", "info_icon"):
            setattr(q, name, None)

        q.GPU.detect()
        q.app_state.preferences.gpu = q.GPU.default()
        q.app_state.preferences.video_codec = q.video_codec_list[0]
        q.app_state.preferences.ai_model = "BSRGANx2"
        q.app_state.preferences.ai_multithreading = "2 threads"

        app = App(root)
        for _ in range(20):
            root.update(); time.sleep(0.01)
        print("engine", q.get_AI_engine_info(), "| gpu", q.GPU.menu_list(), flush=True)

        q.load_selected_files([image_path, video_path], source_root=work)
        for _ in range(40):
            root.update(); time.sleep(0.01)
        print("files loaded:", q.app_state.file_widget.get_selected_file_list(), flush=True)

        q.upscale_button_command()
        deadline = time.time() + 240
        last = None
        while time.time() < deadline:
            root.update(); time.sleep(0.02)
            message = q.app_state.info_message.get()
            if message != last:
                print("MESSAGE:", message, flush=True)
                last = message
            if message.startswith(("Completed", "Error")):
                break
        print("final:", q.app_state.info_message.get(), flush=True)

        for current, _dirs, files in os.walk(os.path.join(work, "out")):
            for name in sorted(files):
                print("out:", os.path.relpath(os.path.join(current, name), work), os.path.getsize(os.path.join(current, name)), flush=True)
        print("orchestrator alive:", q.app_state.process_upscale_orchestrator is not None and q.app_state.process_upscale_orchestrator.is_alive(), flush=True)
        q.on_app_close()
        for _ in range(60):
            root.update(); time.sleep(0.02)
        print("closed cleanly", flush=True)


if __name__ == '__main__':
    main()
