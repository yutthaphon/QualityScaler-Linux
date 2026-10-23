import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import quality_scaler_platform as platform
import QualityScaler as quality_scaler

class GpuAdapterTests(unittest.TestCase):

    @unittest.skipUnless(platform.IS_LINUX, "Linux GPU enumeration")
    def test_nvidia_smi_output_becomes_cuda_device_ids(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="0, NVIDIA GeForce RTX 4090, 24564\n1, NVIDIA GeForce RTX 3060, 12288\n",
        )
        with patch.object(platform.shutil, "which", return_value="/usr/bin/nvidia-smi"), \
             patch.object(platform.subprocess, "run", return_value=completed):
            adapters = platform.gpu_adapters()

        self.assertEqual([adapter["device_id"] for adapter in adapters], [0, 1])
        self.assertEqual(adapters[0]["name"], "NVIDIA GeForce RTX 4090")
        self.assertAlmostEqual(adapters[0]["vram_gb"], 24.0, places=1)
        self.assertAlmostEqual(adapters[1]["vram_gb"], 12.0, places=1)
        self.assertTrue(all(adapter["vendor_id"] == 0x10DE for adapter in adapters))

    @unittest.skipUnless(platform.IS_LINUX, "Linux GPU enumeration")
    def test_missing_nvidia_driver_falls_back_to_drm_cards(self):
        completed = subprocess.CompletedProcess(args=[], returncode=127, stdout="")
        with tempfile.TemporaryDirectory() as sysfs:
            card = os.path.join(sysfs, "card0", "device")
            os.makedirs(card)
            with open(os.path.join(card, "vendor"), "w") as vendor_file:
                vendor_file.write("0x1002\n")
            with open(os.path.join(card, "mem_info_vram_total"), "w") as vram_file:
                vram_file.write(str(8 * 1024 ** 3))
            # Connector entries and render nodes must not become adapters.
            os.makedirs(os.path.join(sysfs, "card0-DP-1"))

            with patch.object(platform.shutil, "which", side_effect=lambda name: None if name == "nvidia-smi" else f"/usr/bin/{name}"), \
                 patch.object(platform.subprocess, "run", return_value=completed), \
                 patch.object(platform, "_pci_device_name", return_value="AMD Radeon RX 6600"):
                adapters = platform._list_drm_adapters(sysfs)

        self.assertEqual(len(adapters), 1)
        self.assertEqual(adapters[0]["name"], "AMD Radeon RX 6600")
        self.assertEqual(adapters[0]["vendor_id"], 0x1002)
        self.assertEqual(adapters[0]["vram_gb"], 8.0)
        self.assertEqual(adapters[0]["device_id"], 0)

class FfmpegCapabilityTests(unittest.TestCase):

    def setUp(self):
        # The listings are cached per binary; clear them so a real probe from an
        # earlier test cannot answer for the mocked one.
        platform._FFMPEG_CAPABILITIES.clear()

    def test_missing_ffmpeg_reports_no_encoders(self):
        self.assertFalse(platform.ffmpeg_has_encoder("/nonexistent/ffmpeg", "h264_nvenc"))
        self.assertFalse(platform.ffmpeg_has_filter("/nonexistent/ffmpeg", "yadif_cuda"))

    def test_encoder_and_filter_listings_are_read_from_ffmpeg_output(self):
        listings = {
            "-encoders": subprocess.CompletedProcess(args=[], returncode=0,
                                                    stdout=" V....D libx264  H.264\n V....D h264_nvenc  NVENC\n"),
            "-filters":  subprocess.CompletedProcess(args=[], returncode=0,
                                                    stdout=" ..C yadif_cuda  Deinterlace\n"),
        }
        with patch.object(platform.subprocess, "run", side_effect=lambda command, **kwargs: listings[command[-1]]):
            self.assertTrue(platform.ffmpeg_has_encoder("/usr/bin/ffmpeg", "h264_nvenc"))
            self.assertFalse(platform.ffmpeg_has_encoder("/usr/bin/ffmpeg", "h264_amf"))
            self.assertTrue(platform.ffmpeg_has_filter("/usr/bin/ffmpeg", "yadif_cuda"))
            self.assertFalse(platform.ffmpeg_has_filter("/usr/bin/ffmpeg", "bwdif_cuda"))

    def test_codec_menu_only_lists_available_encoders(self):
        available = {"libx264", "libx265", "h264_nvenc", "hevc_nvenc"}
        with patch.object(platform, "ffmpeg_has_encoder", side_effect=lambda path, name: name in available):
            codecs = quality_scaler._available_video_codecs()

        self.assertEqual(codecs, ["x264", "x265", "----", "h264_nvenc", "hevc_nvenc"])

    def test_codec_menu_falls_back_to_software_when_ffmpeg_is_absent(self):
        with patch.object(platform, "ffmpeg_has_encoder", return_value=False):
            self.assertEqual(quality_scaler._available_video_codecs(), ["x264", "x265"])

class SleepInhibitorTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.fake_binary = os.path.join(self.directory, "systemd-inhibit")
        self._which = platform.shutil.which

    def tearDown(self):
        platform.allow_sleep()
        platform.shutil.which = self._which

    def write_fake(self, body):
        with open(self.fake_binary, "w") as handle:
            handle.write(body)
        os.chmod(self.fake_binary, 0o755)
        platform.shutil.which = lambda name: self.fake_binary if name == "systemd-inhibit" else self._which(name)

    @unittest.skipUnless(platform.IS_LINUX, "logind sleep inhibition")
    def test_inhibitor_is_held_while_running_and_stopped_afterwards(self):
        self.write_fake("#!/bin/sh\nwhile true; do sleep 1; done\n")
        platform.prevent_sleep()
        platform.prevent_sleep()   # a second call must reuse the running inhibitor

        inhibitor = platform._SLEEP_INHIBITOR
        self.assertIsNotNone(inhibitor)
        self.assertIsNone(inhibitor.poll())

        platform.allow_sleep()
        self.assertIsNone(platform._SLEEP_INHIBITOR)
        self.assertIsNotNone(inhibitor.poll())

    @unittest.skipUnless(platform.IS_LINUX, "logind sleep inhibition")
    def test_refused_inhibitor_is_reported_and_not_retained(self):
        # systemd-inhibit exits immediately when logind refuses the lock.
        self.write_fake("#!/bin/sh\necho 'Failed to inhibit: Access denied' >&2\nexit 1\n")

        output = io.StringIO()
        with redirect_stdout(output):
            platform.prevent_sleep()

        self.assertIsNone(platform._SLEEP_INHIBITOR)
        self.assertIn("not inhibited", output.getvalue())
        self.assertIn("Access denied", output.getvalue())

class BinaryAndPathTests(unittest.TestCase):

    def test_bundled_binary_wins_over_the_system_one(self):
        with tempfile.TemporaryDirectory() as assets:
            executable_name = "ffmpeg.exe" if platform.IS_WINDOWS else "ffmpeg"
            bundled = os.path.join(assets, executable_name)
            open(bundled, "w").close()

            with patch.object(platform.shutil, "which", return_value="/usr/bin/ffmpeg"):
                self.assertEqual(platform.find_binary(assets, "ffmpeg"), bundled)

    def test_system_binary_is_used_when_nothing_is_bundled(self):
        with tempfile.TemporaryDirectory() as assets:
            with patch.object(platform.shutil, "which", return_value="/usr/bin/ffmpeg"):
                self.assertEqual(platform.find_binary(assets, "ffmpeg"), "/usr/bin/ffmpeg")

    def test_unresolved_binary_keeps_the_plain_name(self):
        with tempfile.TemporaryDirectory() as assets:
            with patch.object(platform.shutil, "which", return_value=None):
                self.assertEqual(platform.find_binary(assets, "ffprobe"), "ffprobe")
                self.assertFalse(platform.binary_available("ffprobe"))

    @unittest.skipUnless(platform.IS_LINUX, "Linux config directory")
    def test_config_directory_follows_xdg_config_home(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": home}):
                directory = platform.config_directory("QualityScaler")

        self.assertEqual(directory, os.path.join(home, "QualityScaler"))

class ProviderOptionTests(unittest.TestCase):

    def test_cuda_options_target_the_selected_device(self):
        options = quality_scaler.build_AI_provider_options("CUDAExecutionProvider", "1")
        self.assertEqual(options["device_id"], "1")

    def test_cuda_auto_leaves_device_selection_to_onnxruntime(self):
        options = quality_scaler.build_AI_provider_options("CUDAExecutionProvider", "Auto")
        self.assertNotIn("device_id", options)

    def test_cpu_provider_takes_no_options(self):
        self.assertEqual(quality_scaler.build_AI_provider_options("CPUExecutionProvider", "0"), {})

    def test_directml_auto_requests_high_performance(self):
        options = quality_scaler.build_AI_provider_options("DmlExecutionProvider", "Auto")
        self.assertEqual(options, {"performance_preference": "high_performance"})

if __name__ == "__main__":
    unittest.main()
