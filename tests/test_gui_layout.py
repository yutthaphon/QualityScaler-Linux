"""GUI layout regression: no label may clip or be overpainted by the next widget.

The original layout used column slots measured for Segoe UI. Every Linux desktop
font is wider, so those slots made labels run under the value beside them. The
rows are now placed from measured text; these tests fail if that regresses.
"""

import unittest

import QualityScaler as q

class GuiLayoutTests(unittest.TestCase):

    def setUp(self):
        self.old_state = q.app_state
        self.root = q.CTk()
        self.root.geometry("1000x675+10000+10000")
        self.root.resizable(False, False)
        q.apply_app_zoom(1.0)
        for size in (8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24):
            setattr(q, f"bold{size}", q.CTkFont(family=q.platform_services.ui_font_family(),
                                                size=size, weight="bold"))
        for name in ("clear_icon", "logo_git", "logo_telegram", "log_icon",
                     "stop_icon", "upscale_icon", "info_icon"):
            setattr(q, name, None)

        state = q.AppState(q.UserPreferences())
        state.window = self.root
        state.info_message = q.StringVar(master=self.root)
        state.selected_output_path = q.StringVar(master=self.root, value=q.OUTPUT_PATH_CODED)
        state.selected_input_resize_factor = q.StringVar(master=self.root, value="50")
        state.selected_output_resize_factor = q.StringVar(master=self.root, value="100")
        state.selected_VRAM_limiter = q.StringVar(master=self.root, value="6")
        state.selected_video_codec = q.StringVar(master=self.root, value="h264_nvenc")
        state.ui_jobs = q.BackgroundJobs()
        q.app_state = state

        # Worst case: the longest GPU name the menu has to display.
        q.GPU.detected = [q.GPU(name="RTX 4090 Laptop GPU", vram_gb=16.0,
                                device_id=0, vendor_id=q.GPU.VENDOR_NVIDIA)]
        state.preferences.gpu = q.GPU.default()

        # These cached widget groups belong to the previous test's window.
        q.App._load_widgets = None
        q.App._action_button = None
        self.app = q.App(self.root)
        self.pump()

    def tearDown(self):
        q.cancel_tk_callbacks(self.root)
        self.root.destroy()
        q.app_state = self.old_state

    def pump(self, duration=0.35):
        import time
        end = time.monotonic() + duration
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.005)

    def text_widgets(self):
        found = []
        def walk(widget):
            for child in widget.winfo_children():
                try:
                    text = child.cget("text")
                except Exception:
                    text = None
                if (isinstance(text, str) and text.strip() and text != "----"
                        and child.winfo_width() > 1 and child.winfo_height() > 1):
                    try:
                        scale = child._apply_widget_scaling(1)
                        needed = max(child._font.measure(line) for line in text.split("\n")) * scale
                    except Exception:
                        needed = None
                    found.append((child, text, needed))
                walk(child)
        walk(self.root)
        return found

    def test_no_label_is_clipped_by_its_own_widget(self):
        clipped = []
        for widget, text, needed in self.text_widgets():
            if needed is None:
                continue
            if needed > widget.winfo_width() + 1:
                clipped.append(f"{text!r} needs {needed:.0f}px, has {widget.winfo_width()}px")
        self.assertEqual(clipped, [])

    def test_no_label_runs_under_the_widget_to_its_right(self):
        overpainted = []
        entries = self.text_widgets()
        for widget, text, needed in entries:
            if needed is None or "\n" in text:
                continue
            x, y, height = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_height()
            for other, other_text, _ in entries:
                if other is widget or str(other).startswith(str(widget)) or str(widget).startswith(str(other)):
                    continue      # a button paints its own inner label
                if "\n" in other_text:
                    continue
                other_x, other_y, other_height = other.winfo_rootx(), other.winfo_rooty(), other.winfo_height()
                if other_x <= x:
                    continue
                if min(y + height, other_y + other_height) - max(y, other_y) <= 2:
                    continue
                if other_x < x + needed:
                    overpainted.append(f"{text!r} reaches into {other_text!r}")
        self.assertEqual(overpainted, [])

    def test_widest_gpu_name_fits_its_menu(self):
        menu_width = q.App.menu_width_for_texts(q.GPU.menu_list(), q.little_menu_width, 150)
        self.assertGreaterEqual(menu_width, q.bold11.measure("RTX 4090 Laptop GPU"))
        # and the row still fits: the GPU menu must not reach the right column
        left_start = q.COL_INFO_L * q.APP_DESIGN_WIDTH - q.ROW_INFO_MIN_WIDTH / 2 + q.ROW_LABEL_OFFSET
        left_value = left_start + q.bold13.measure("GPU") + q.ROW_GAP
        right_label_start = (q.APP_DESIGN_WIDTH - q.ROW_PANEL_RIGHT_MARGIN
                             - (q.little_textbox_width + 2) - q.ROW_GAP
                             - q.bold13.measure("GPU VRAM (GB)"))
        self.assertLessEqual(left_value + menu_width + 2, right_label_start)

if __name__ == "__main__":
    unittest.main()
