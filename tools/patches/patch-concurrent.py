#!/usr/bin/env python3
"""Add an in-app "Concurrent" mode to QualityScaler.

Upstream runs the whole batch sequentially inside one orchestrator process. This
patch splits the selected file list across N worker processes inside that same
orchestrator, so one program instance, one log, one watchdog and one output
folder handle several files at a time.

Total ONNX sessions stay `tasks x (threads / tasks)`, so raising the task count
does not raise VRAM use as long as the thread budget is divided.

Idempotent. Usage: patch-concurrent.py [/root/QualityScaler-Linux/QualityScaler.py]
"""
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/root/QualityScaler-Linux/QualityScaler.py")
if not path.is_file():
    sys.exit(f"not found: {path}")

text = path.read_text(encoding="utf-8")
MARKER = "QS_PATCH_CONCURRENT"
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


# ---------------------------------------------------------------- 1. constant
patch(
    "concurrency-list",
    'AI_multithreading_list = [ "OFF", "2 threads", "4 threads", "6 threads", "8 threads"]',
    'AI_multithreading_list = [ "OFF", "2 threads", "4 threads", "6 threads", "8 threads"]\n'
    '# QS_PATCH_CONCURRENT: files processed at the same time by one program instance\n'
    'concurrency_list      = [ "OFF", "2 tasks", "3 tasks" ]',
)

# ---------------------------------------------------------------- 2. preferences
patch(
    "pref-field",
    '    ai_multithreading:    str = AI_multithreading_list[0]',
    '    ai_multithreading:    str = AI_multithreading_list[0]\n'
    '    concurrency:          str = concurrency_list[0]',
)

# ---------------------------------------------------------------- 3. config field
patch(
    "config-field",
    '    selected_video_codec:       str\n',
    '    selected_video_codec:       str\n'
    '    selected_concurrency:       int = 1\n',
)

# ---------------------------------------------------------------- 4. getter
patch(
    "getter",
    'def get_current_ai_multithreading() -> int:\n'
    '    if app_state.preferences.ai_multithreading == "OFF":\n'
    '        return 1\n'
    '    return int(app_state.preferences.ai_multithreading.split()[0])',
    'def get_current_ai_multithreading() -> int:\n'
    '    if app_state.preferences.ai_multithreading == "OFF":\n'
    '        return 1\n'
    '    return int(app_state.preferences.ai_multithreading.split()[0])\n'
    '\n'
    'def get_current_concurrency() -> int:\n'
    '    # QS_PATCH_CONCURRENT: number of files handled at the same time\n'
    '    if app_state.preferences.concurrency == "OFF":\n'
    '        return 1\n'
    '    return int(app_state.preferences.concurrency.split()[0])',
)

# ---------------------------------------------------------------- 5. config build
patch(
    "config-build",
    '        selected_video_codec       = app_state.preferences.video_codec,\n    )',
    '        selected_video_codec       = app_state.preferences.video_codec,\n'
    '        selected_concurrency       = get_current_concurrency(),\n'
    '    )',
)

# ---------------------------------------------------------------- 6. save preference
patch(
    "save-pref",
    '        "default_AI_multithreading":    app_state.preferences.ai_multithreading,',
    '        "default_AI_multithreading":    app_state.preferences.ai_multithreading,\n'
    '        "default_concurrency":          app_state.preferences.concurrency,',
)

# ---------------------------------------------------------------- 7. load preference
patch(
    "load-pref",
    '            ai_multithreading    = json_data.get("default_AI_multithreading",    AI_multithreading_list[0]),',
    '            ai_multithreading    = json_data.get("default_AI_multithreading",    AI_multithreading_list[0]),\n'
    '            concurrency          = json_data.get("default_concurrency",          concurrency_list[0]) '
    'if json_data.get("default_concurrency", concurrency_list[0]) in concurrency_list else concurrency_list[0],',
)

# ---------------------------------------------------------------- 8. GUI menu
patch(
    "menu-callback",
    '    def select_AI_multithreading_from_menu(selected_option: str) -> None:\n'
    '        app_state.preferences.ai_multithreading = selected_option',
    '    def select_AI_multithreading_from_menu(selected_option: str) -> None:\n'
    '        app_state.preferences.ai_multithreading = selected_option\n'
    '\n'
    '    @staticmethod\n'
    '    def select_concurrency_from_menu(selected_option: str) -> None:\n'
    '        # QS_PATCH_CONCURRENT\n'
    '        app_state.preferences.concurrency = selected_option',
)

patch(
    "menu-row",
    '''        info_button = App.create_info_button(open_info_AI_multithreading, "AI multithreading")
        option_menu = App.create_option_menu(App.select_AI_multithreading_from_menu, AI_multithreading_list, app_state.preferences.ai_multithreading)

        App.place_single_row(row, option_menu, left_info = info_button)''',
    '''        def open_info_concurrent():
            option_list = [
                " How many files this program works on at the same time.",
                " Each task is a separate worker process with its own AI engine.",
                " Threads per task = AI multithreading / tasks, so the total number of",
                " workers stays the same: VRAM and GPU load do not grow with the task count.",
                " While one task encodes its video the others keep upscaling, which fills",
                " the idle time that a single task leaves between upscale and encode.",
                " Log, output folder and resume work exactly as they do with one task.",
            ]
            open_info_messagebox("Concurrent tasks", "Process several files at the same time", option_list)

        info_button = App.create_info_button(open_info_AI_multithreading, "Threads")
        option_menu = App.create_option_menu(App.select_AI_multithreading_from_menu, AI_multithreading_list, app_state.preferences.ai_multithreading)

        concurrent_info = App.create_info_button(open_info_concurrent, "Concurrent")
        concurrent_menu = App.create_option_menu(App.select_concurrency_from_menu, concurrency_list, app_state.preferences.concurrency)

        App.place_row(
            row,
            "Threads", option_menu, 171,
            "Concurrent", concurrent_menu, 111,
            left_info = info_button, right_info = concurrent_info,
        )''',
)

# ---------------------------------------------------------------- 9. start log + arg
patch(
    "start-print",
    '        print(f"    AI multithreading: {processing_config.selected_AI_multithreading}")',
    '        print(f"    AI multithreading: {processing_config.selected_AI_multithreading}")\n'
    '        print(f"    Concurrent tasks: {processing_config.selected_concurrency}")',
)

patch(
    "start-arg",
    '                processing_config.selected_video_codec,\n            )\n        )\n        prevent_sleep()',
    '                processing_config.selected_video_codec,\n'
    '                processing_config.selected_concurrency,\n'
    '            )\n        )\n        prevent_sleep()',
)

# ---------------------------------------------------------------- 10. orchestrator
OLD_SIGNATURE_TAIL = '        selected_video_codec:       str,\n        ) -> None:\n    configure_realtime_logging(process_log_q)\n'
NEW_SIGNATURE_TAIL = ('        selected_video_codec:       str,\n'
                      '        selected_concurrency:       int = 1,\n'
                      '        ) -> None:\n'
                      '    configure_realtime_logging(process_log_q)\n')

start = text.find("def upscale_orchestrator(")
if start == -1:
    sys.exit("upscale_orchestrator not found")
end = text.find("# IMAGES", start)
if end == -1:
    sys.exit("# IMAGES sentinel not found")

old_func = text[start:end]
if old_func.count(OLD_SIGNATURE_TAIL) != 1:
    sys.exit("orchestrator signature not in expected shape -- upstream changed")

# Reuse the existing body of the sequential loop by re-emitting it as a helper.
loop_start = old_func.find("        AI_instance_for_images = None")
loop_end = old_func.find('        if not event_stop_upscale_process.is_set(): write_process_status(process_status_q, f"{COMPLETED_STATUS}")')
if loop_start == -1 or loop_end == -1:
    sys.exit("orchestrator loop not in expected shape -- upstream changed")

loop_body = old_func[loop_start:loop_end].rstrip() + "\n"

new_func = (
    'def _run_file_batch(\n'
    '        process_status_q,\n'
    '        video_frames_and_info_q,\n'
    '        event_stop_upscale_process,\n'
    '        process_log_q,\n'
    '        file_list:                  list[str],\n'
    '        first_file_number:          int,\n'
    '        source_root,\n'
    '        selected_output_path,\n'
    '        selected_AI_model,\n'
    '        selected_AI_multithreading: int,\n'
    '        input_resize_factor:        float,\n'
    '        output_resize_factor:       float,\n'
    '        selected_gpu,\n'
    '        use_nvidia_deinterlace:     bool,\n'
    '        tiles_resolution:           int,\n'
    '        selected_sharpening_amount: float,\n'
    '        selected_keep_frames:       bool,\n'
    '        selected_deinterlace:       str,\n'
    '        selected_target_resolution: str,\n'
    '        selected_target_ratio:      str,\n'
    '        selected_image_extension:   str,\n'
    '        selected_video_extension:   str,\n'
    '        selected_video_codec:       str,\n'
    '        ) -> None:\n'
    '    # ' + MARKER + ': one worker\'s share of the queue. Runs inline when\n'
    '    # concurrency is OFF, or inside a child process when it is on.\n'
    '    if video_frames_and_info_q is None:\n'
    '        # A Manager proxy, not a raw Queue: raw queues can only reach a Pool\n'
    '        # worker through inheritance, and spawn has no inheritance to offer.\n'
    '        video_frames_and_info_q = multiprocessing_Manager().Queue(maxsize=64)\n'
    '    configure_realtime_logging(process_log_q)\n'
    '\n'
    '    try:\n'
    + loop_body.replace(
        "        AI_instance_for_images = None\n"
        "\n"
        "        how_many_files = len(selected_file_list)\n"
        "        for file_number in range(how_many_files):",
        "        AI_instance_for_images = None\n"
        "\n"
        "        how_many_files = len(file_list)\n"
        "        for _index in range(how_many_files):",
    ).replace(
        "            file_path   = selected_file_list[file_number]\n"
        "            source_key = get_file_cache_key(file_path)\n"
        "            file_number = file_number + 1",
        "            file_path   = file_list[_index]\n"
        "            source_key = get_file_cache_key(file_path)\n"
        "            file_number = first_file_number + _index",
    )
    + '\n'
    '    except Exception as exception:\n'
    '        error_message = str(exception)\n'
    '        write_process_status(process_status_q, f"{ERROR_STATUS} {error_message}")\n'
    '\n'
    'def upscale_orchestrator(\n'
    '        process_status_q:           multiprocessing_Queue,\n'
    '        video_frames_and_info_q:    multiprocessing_Queue,\n'
    '        event_stop_upscale_process: multiprocessing_Event, # type: ignore\n'
    '        process_log_q,\n'
    '\n'
    '        selected_file_list:         list[str],\n'
    '        source_root:                Optional[str],\n'
    '        selected_output_path:       str,\n'
    '        selected_AI_model:          str,\n'
    '        selected_AI_multithreading: int,\n'
    '        input_resize_factor:        float,\n'
    '        output_resize_factor:       float,\n'
    '        selected_gpu:               str,\n'
    '        use_nvidia_deinterlace:     bool,\n'
    '        tiles_resolution:           int,\n'
    '        selected_sharpening_amount: float,\n'
    '        selected_keep_frames:       bool,\n'
    '        selected_deinterlace:       str,\n'
    '        selected_target_resolution: str,\n'
    '        selected_target_ratio:      str,\n'
    '        selected_image_extension:   str,\n'
    '        selected_video_extension:   str,\n'
    '        selected_video_codec:       str,\n'
    '        selected_concurrency:       int = 1,\n'
    '        ) -> None:\n'
    '    configure_realtime_logging(process_log_q)\n'
    '\n'
    '    try:\n'
    '        tasks = max(1, min(int(selected_concurrency or 1), len(selected_file_list)))\n'
    '\n'
    '        if tasks <= 1 or len(selected_file_list) <= 1:\n'
    '            _run_file_batch(\n'
    '                process_status_q, video_frames_and_info_q, event_stop_upscale_process, process_log_q,\n'
    '                selected_file_list, 1, source_root, selected_output_path, selected_AI_model,\n'
    '                selected_AI_multithreading, input_resize_factor, output_resize_factor, selected_gpu,\n'
    '                use_nvidia_deinterlace, tiles_resolution, selected_sharpening_amount,\n'
    '                selected_keep_frames, selected_deinterlace, selected_target_resolution,\n'
    '                selected_target_ratio, selected_image_extension, selected_video_extension,\n'
    '                selected_video_codec,\n'
    '            )\n'
    '        else:\n'
    '            threads_per_task = max(1, int(selected_AI_multithreading) // tasks)\n'
    '            print(f"[Concurrent] {tasks} tasks x {threads_per_task} threads "\n'
    '                  f"= {tasks * threads_per_task} workers", flush=True)\n'
    '            write_process_status(process_status_q,\n'
    '                                 f"Concurrent: {tasks} tasks x {threads_per_task} threads")\n'
    '\n'
    '            children = []\n'
    '            first_file_number = 1\n'
    '            for chunk in (list(c) for c in numpy_array_split(selected_file_list, tasks)):\n'
    '                if not chunk:\n'
    '                    continue\n'
    '                child = multiprocessing_Process(\n'
    '                    target = _run_file_batch,\n'
    '                    args = (\n'
    '                        process_status_q, None, event_stop_upscale_process, process_log_q,\n'
    '                        chunk, first_file_number, source_root, selected_output_path,\n'
    '                        selected_AI_model, threads_per_task, input_resize_factor,\n'
    '                        output_resize_factor, selected_gpu, use_nvidia_deinterlace,\n'
    '                        tiles_resolution, selected_sharpening_amount, selected_keep_frames,\n'
    '                        selected_deinterlace, selected_target_resolution, selected_target_ratio,\n'
    '                        selected_image_extension, selected_video_extension, selected_video_codec,\n'
    '                    ),\n'
    '                )\n'
    '                child.start()\n'
    '                children.append(child)\n'
    '                first_file_number += len(chunk)\n'
    '\n'
    '            for child in children:\n'
    '                while child.is_alive() and not event_stop_upscale_process.is_set():\n'
    '                    child.join(timeout=0.5)\n'
    '            for child in children:\n'
    '                if child.is_alive():\n'
    '                    child.join(timeout=30)\n'
    '                if child.is_alive():\n'
    '                    child.terminate()\n'
    '                    child.join(timeout=10)\n'
    '\n'
    '        if not event_stop_upscale_process.is_set():\n'
    '            write_process_status(process_status_q, f"{COMPLETED_STATUS}")\n'
    '\n'
    '    except Exception as exception:\n'
    '        error_message = str(exception)\n'
    '        write_process_status(process_status_q, f"{ERROR_STATUS} {error_message}")\n'
    '\n'
)

text = text[:start] + new_func + text[end:]
applied.append("orchestrator-split")

path.write_text(text, encoding="utf-8")
ast.parse(path.read_text(encoding="utf-8"))
print("patched: " + ", ".join(applied))
print("syntax  : OK")
