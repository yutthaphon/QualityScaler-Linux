"""Host operating system integration for QualityScaler (Windows and Linux).

Everything that differs between the two platforms lives here so the application
module stays platform agnostic: binary discovery, configuration paths, process
priority, sleep inhibition, desktop notifications, window icon, UI font and GPU
enumeration.
"""

import os
import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX   = sys.platform.startswith("linux")

_FFMPEG_CAPABILITIES: dict[tuple[str, str], frozenset] = {}

# GPU -------------------

def gpu_adapters() -> list[dict]:
    """Detected GPUs as dicts: name, vram_gb, device_id, vendor_id.

    device_id is the index the inference runtime expects: the DirectML adapter
    position on Windows, the CUDA device index on Linux. Empty when nothing is
    usable, so the caller can fall back to its saved preference.
    """
    if IS_WINDOWS:
        return _list_windows_adapters()
    if IS_LINUX:
        return _list_linux_adapters()
    return []

def _list_windows_adapters() -> list[dict]:
    # Enumerate DirectX adapters via DXGI and read their dedicated VRAM.
    # Works for every GPU vendor (Intel / AMD / NVIDIA) without extra dependencies.
    if not IS_WINDOWS:
        return []

    import ctypes

    class _LUID(ctypes.Structure):
        _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _DXGI_ADAPTER_DESC1(ctypes.Structure):
        _fields_ = [
            ("Description",           ctypes.c_wchar * 128),
            ("VendorId",              ctypes.c_uint),
            ("DeviceId",              ctypes.c_uint),
            ("SubSysId",              ctypes.c_uint),
            ("Revision",              ctypes.c_uint),
            ("DedicatedVideoMemory",  ctypes.c_size_t),
            ("DedicatedSystemMemory", ctypes.c_size_t),
            ("SharedSystemMemory",    ctypes.c_size_t),
            ("AdapterLuid",           _LUID),
            ("Flags",                 ctypes.c_uint),
        ]

    DXGI_ADAPTER_FLAG_SOFTWARE = 2
    IID_IDXGIFactory1 = _GUID(
        0x770aae78, 0xf26f, 0x4dba,
        (ctypes.c_ubyte * 8)(0xa8, 0x29, 0x25, 0x3c, 0x83, 0xd1, 0xb3, 0x87)
    )

    def _com_method(obj_ptr, index, restype, argtypes):
        vtable    = ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
        func_addr = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))[index]
        return ctypes.WINFUNCTYPE(restype, *argtypes)(func_addr)

    adapters    = []
    hardware_id = 0

    try:
        factory = ctypes.c_void_p()
        hr = ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(IID_IDXGIFactory1), ctypes.byref(factory))
        if hr != 0 or not factory.value:
            return []

        # IDXGIFactory1::EnumAdapters1 -> vtable index 12 ; IUnknown::Release -> index 2
        EnumAdapters1  = _com_method(factory, 12, ctypes.c_int32, [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)])
        FactoryRelease = _com_method(factory, 2,  ctypes.c_ulong, [ctypes.c_void_p])

        try:
            adapter_index = 0
            while True:
                adapter = ctypes.c_void_p()
                if EnumAdapters1(factory, adapter_index, ctypes.byref(adapter)) != 0:
                    break

                # IDXGIAdapter1::GetDesc1 -> vtable index 10 ; IUnknown::Release -> index 2
                desc           = _DXGI_ADAPTER_DESC1()
                GetDesc1       = _com_method(adapter, 10, ctypes.c_int32, [ctypes.c_void_p, ctypes.POINTER(_DXGI_ADAPTER_DESC1)])
                AdapterRelease = _com_method(adapter, 2,  ctypes.c_ulong, [ctypes.c_void_p])
                GetDesc1(adapter, ctypes.byref(desc))

                # Skip software adapters (WARP / Microsoft Basic Render Driver)
                if not (desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE):
                    adapters.append({
                        "name":      desc.Description,
                        "vram_gb":   round(desc.DedicatedVideoMemory / (1024 ** 3), 1),
                        "device_id": hardware_id,
                        "vendor_id": desc.VendorId,
                    })
                    hardware_id += 1

                AdapterRelease(adapter)
                adapter_index += 1
        finally:
            FactoryRelease(factory)

    except Exception as exception:
        print(f"[QualityScaler] GPU detection failed: {exception}")
        return []

    return adapters

def _list_linux_adapters() -> list[dict]:
    # NVIDIA first: nvidia-smi indices are the CUDA device ids ONNX Runtime uses.
    adapters = _list_nvidia_smi_adapters()
    if adapters:
        return adapters
    # No NVIDIA driver: enumerate the DRM cards (AMD / Intel and their VRAM).
    return _list_drm_adapters()

def _list_nvidia_smi_adapters() -> list[dict]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return []

    try:
        completed = subprocess.run(
            [executable, "--query-gpu=index,name,memory.total",
             "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if completed.returncode != 0:
        return []

    adapters = []
    for line in completed.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 3:
            continue
        try:
            device_id = int(fields[0])
            vram_mb   = float(fields[2])
        except ValueError:
            continue
        adapters.append({
            "name":      fields[1],
            "vram_gb":   round(vram_mb / 1024, 1),
            "device_id": device_id,
            "vendor_id": 0x10DE,
        })

    return adapters

def _list_drm_adapters(sysfs_root: str = "/sys/class/drm") -> list[dict]:
    # One adapter per display-capable DRM card (card0, card1, ...), skipping
    # connector entries such as card0-DP-1 and the renderD* nodes.
    if not os.path.isdir(sysfs_root):
        return []

    vendor_names = {0x10DE: "NVIDIA", 0x1002: "AMD", 0x8086: "Intel"}
    adapters     = []
    seen_devices = set()

    for entry in sorted(os.listdir(sysfs_root)):
        if not entry.startswith("card") or not entry[4:].isdigit():
            continue

        device_path = os.path.join(sysfs_root, entry, "device")
        try:
            vendor_id = int(_read_first_line(os.path.join(device_path, "vendor")), 16)
        except (OSError, ValueError):
            continue

        pci_address = os.path.realpath(device_path)
        if pci_address in seen_devices:
            continue
        seen_devices.add(pci_address)

        vram_bytes = _read_vram_bytes(device_path)
        name       = _pci_device_name(pci_address) or f"{vendor_names.get(vendor_id, 'Unknown')} GPU"
        adapters.append({
            "name":      name,
            "vram_gb":   round(vram_bytes / (1024 ** 3), 1) if vram_bytes else 0.0,
            "device_id": len(adapters),
            "vendor_id": vendor_id,
        })

    return adapters

def _read_first_line(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as device_file:
        return device_file.readline().strip()

def _read_vram_bytes(device_path: str) -> int:
    # amdgpu exposes mem_info_vram_total; i915/xe expose lmem_total_bytes.
    for file_name in ("mem_info_vram_total", "lmem_total_bytes"):
        try:
            return int(_read_first_text(os.path.join(device_path, file_name)))
        except (OSError, ValueError):
            continue
    return 0

def _read_first_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as device_file:
        return device_file.read().strip()

def _pci_device_name(pci_address: str) -> str:
    # lspci -D -m -s 0000:01:00.0 prints: "0000:01:00.0" "VGA ..." "NVIDIA Corporation" "AD106 [GeForce RTX 4060]"
    lspci = shutil.which("lspci")
    if lspci is None:
        return ""
    try:
        completed = subprocess.run(
            [lspci, "-D", "-m", "-s", os.path.basename(pci_address)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    parts = [part.strip('"') for part in completed.stdout.split('" "')]
    if len(parts) >= 4:
        vendor, model = parts[2], parts[3]
        return f"{vendor} {model}".strip()
    return ""

# BINARIES -------------------

def find_binary(asset_directory: str, executable_name: str) -> str:
    """Bundled binary when present, otherwise the one installed on the system.

    Returns a path that may not exist; callers report the failure with the
    concrete name instead of failing later inside subprocess.
    """
    names = (f"{executable_name}.exe", executable_name) if IS_WINDOWS else (executable_name,)
    for name in names:
        bundled = os.path.join(asset_directory, name)
        if os.path.isfile(bundled):
            return bundled
    return shutil.which(executable_name) or executable_name

def binary_available(binary_path: str) -> bool:
    return os.path.isfile(binary_path) or shutil.which(binary_path) is not None

def ffmpeg_has_encoder(ffmpeg_path: str, encoder: str) -> bool:
    return encoder in _ffmpeg_capabilities(ffmpeg_path, "-encoders")

def ffmpeg_has_filter(ffmpeg_path: str, filter_name: str) -> bool:
    return filter_name in _ffmpeg_capabilities(ffmpeg_path, "-filters")

def _ffmpeg_capabilities(ffmpeg_path: str, listing_flag: str) -> frozenset:
    # A missing or broken FFmpeg yields an empty set, never an exception: the
    # menus then only offer what is still safe to attempt.
    key = (ffmpeg_path, listing_flag)
    cached = _FFMPEG_CAPABILITIES.get(key)
    if cached is not None:
        return cached
    try:
        completed = subprocess.run(
            [ffmpeg_path, "-hide_banner", listing_flag],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            text=True,
            check=False,
        )
        names = frozenset(completed.stdout.split()) if completed.returncode == 0 else frozenset()
    except (OSError, subprocess.SubprocessError):
        names = frozenset()
    _FFMPEG_CAPABILITIES[key] = names
    return names

# PATHS -------------------

def config_directory(app_name: str) -> str:
    """Per-user settings directory, created on demand.

    Windows keeps the historical ~/Documents location; Linux follows the XDG
    base directory spec so a headless server without ~/Documents still works.
    """
    if IS_WINDOWS:
        directory = os.path.join(os.path.expanduser("~"), "Documents")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        directory = os.path.join(base, app_name)
    os.makedirs(directory, exist_ok=True)
    return directory

# PROCESS PRIORITY -------------------

def set_idle_priority(pid: int) -> None:
    # Best effort: a restricted process may refuse the change, which is not fatal.
    try:
        import psutil
        process = psutil.Process(pid)
        if IS_WINDOWS:
            process.nice(psutil.IDLE_PRIORITY_CLASS)
        else:
            process.nice(19)
    except Exception:
        pass

# SLEEP -------------------

_SLEEP_INHIBITOR = None

def prevent_sleep() -> None:
    # Keep the machine awake while a batch runs; the display may still turn off.
    global _SLEEP_INHIBITOR
    if IS_WINDOWS:
        _windows_execution_state(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        return

    if _SLEEP_INHIBITOR is not None and _SLEEP_INHIBITOR.poll() is None:
        return
    systemd_inhibit = shutil.which("systemd-inhibit")
    if systemd_inhibit is None:
        print("[QualityScaler] Warning: systemd-inhibit not found, system sleep is not inhibited")
        return
    try:
        inhibitor = subprocess.Popen(
            [systemd_inhibit, "--what=sleep:idle", "--who=QualityScaler",
             "--why=Upscaling files", "--mode=block", "sleep", "infinity"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        print(f"[QualityScaler] Warning: could not prevent system sleep: {error}")
        return

    # systemd-inhibit exits immediately when logind refuses the lock (no user
    # session, forbidding environment, cgroup restrictions). A dead inhibitor
    # means nothing is holding the lock, so say so instead of pretending.
    try:
        inhibitor.wait(timeout=0.4)
    except subprocess.TimeoutExpired:
        _SLEEP_INHIBITOR = inhibitor
        return

    reason = (inhibitor.stderr.read() if inhibitor.stderr else b"").decode(errors="replace").strip()
    if inhibitor.stderr:
        inhibitor.stderr.close()
    print(f"[QualityScaler] Warning: system sleep is not inhibited"
          + (f" ({reason.splitlines()[0]})" if reason else ""))

def allow_sleep() -> None:
    global _SLEEP_INHIBITOR
    if IS_WINDOWS:
        _windows_execution_state(0x80000000)  # ES_CONTINUOUS
        return

    inhibitor, _SLEEP_INHIBITOR = _SLEEP_INHIBITOR, None
    if inhibitor is None:
        return
    try:
        if inhibitor.poll() is None:
            inhibitor.terminate()
            inhibitor.wait(timeout=5)
        if inhibitor.stderr:
            inhibitor.stderr.close()
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"[QualityScaler] Warning: could not restore system sleep: {error}")

def _windows_execution_state(flags: int) -> None:
    import ctypes
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception as error:
        print(f"[QualityScaler] Warning: could not change the system sleep state: {error}")

# NOTIFICATIONS -------------------

def notify_completion(title: str, message: str, icon_path: str) -> None:
    if IS_WINDOWS:
        try:
            from winotify import Notification as winotify_Notification
            winotify_Notification(app_id=title, title=title, msg=message, icon=icon_path).show()
        except Exception as error:
            print(f"[QualityScaler] Warning: could not show system notification: {error}")
        return

    notify_send = shutil.which("notify-send")
    if notify_send is None:
        print("[QualityScaler] Warning: notify-send not found, no desktop notification shown")
        return
    try:
        subprocess.run(
            [notify_send, f"--app-name={title}", f"--icon={icon_path}", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"[QualityScaler] Warning: could not show system notification: {error}")

# WINDOW / FONTS -------------------

def apply_window_icon(window, ico_path: str, png_path: str) -> None:
    # ICO is the Windows window-manager format; X11/Wayland wants a PNG.
    if IS_WINDOWS:
        window.iconbitmap(ico_path)
        return
    from tkinter import PhotoImage
    icon = PhotoImage(master=window, file=png_path)
    window.iconphoto(True, icon)
    window._qualityscaler_icon = icon  # keep a reference, Tk does not own it

def ui_font_family() -> str:
    # Segoe UI is the Windows 11 look; Linux desktops rarely ship it.
    if IS_WINDOWS:
        return "Segoe UI"
    try:
        from tkinter import font as tkfont
        available = set(tkfont.families())
    except Exception:
        return "DejaVu Sans"
    for candidate in ("Ubuntu", "Inter", "Noto Sans", "DejaVu Sans", "Liberation Sans", "Cantarell", "Arial"):
        if candidate in available:
            return candidate
    return "DejaVu Sans"

# CUDA LIBRARIES -------------------

_NVIDIA_WHEEL_LIBRARIES = ("cublas", "cuda_runtime", "cudnn", "cufft", "curand")
_CUDA_PRELOADED = False

def configure_cuda_environment() -> None:
    """Make CUDA libraries installed as pip wheels visible to ONNX Runtime.

    onnxruntime-gpu dlopen()s libcublas and cuDNN by soname, but the wheels
    install them into site-packages/nvidia/*/lib which is not on the loader
    path. Adding those directories to LD_LIBRARY_PATH lets every process spawned
    later find them; preloading here covers provider registration in this one.
    """
    global _CUDA_PRELOADED
    if _CUDA_PRELOADED or not IS_LINUX:
        return
    _CUDA_PRELOADED = True

    import sysconfig
    site_packages = sysconfig.get_paths().get("purelib", "")
    directories   = [
        os.path.join(site_packages, "nvidia", package, "lib")
        for package in _NVIDIA_WHEEL_LIBRARIES
    ]
    directories = [directory for directory in directories if os.path.isdir(directory)]
    if not directories:
        return

    current = os.environ.get("LD_LIBRARY_PATH", "")
    entries = current.split(os.pathsep) if current else []
    missing = [directory for directory in directories if directory not in entries]
    if missing:
        os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(missing + entries)

    import ctypes
    libraries = [
        os.path.join(directory, library)
        for directory in directories
        for library in sorted(os.listdir(directory))
        if ".so" in library
    ]
    # Longest name first: libcublasLt before libcublas, libcudnn sub-libraries
    # before the libcudnn front end. Two passes cover unsatisfied dependencies.
    libraries.sort(key=len, reverse=True)
    for _ in range(2):
        libraries = [
            library for library in libraries
            if not _preload_library(library)
        ]

def _preload_library(library_path: str) -> bool:
    import ctypes
    try:
        ctypes.CDLL(library_path, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        return False
    return True
