<html>
<body>
    <div align="center">    
        <img src="https://github.com/Djdefrag/QualityScaler/blob/main/Assets/logo.png" width="175"> 
        <br><br> QualityScaler - image/video AI upscaler app <br><br>
        <a href="https://jangystudio.itch.io/qualityscaler">
            <button>
                <img src="https://static.itch.io/images/badge-color.svg" width="225" height="70">
            </button>     
        </a>
        <a href="https://store.steampowered.com/app/2463110/QualityScaler/">
            <button>
                 <img src="https://images.squarespace-cdn.com/content/v1/5b45fae8b98a78d9d80b9c5c/1531959264455-E7B8MJ3VMPX0593VGCZG/button-steam-available-fixed-2.png" width="250" height="70">
            </button>                 
        </a>
    </div>
    <br>
    <div align="center">
        <img src="https://github.com/user-attachments/assets/040e3880-3adb-478a-9a82-df2c5dc12fad">
    </div>
</body>
</html>

<div align="center">

[![Upstream](https://img.shields.io/badge/upstream-Djdefrag%2FQualityScaler-blue?style=flat-square)](https://github.com/Djdefrag/QualityScaler)
[![Platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Linux-informational?style=flat-square)](#-linux-specifics)
[![License](https://img.shields.io/github/license/Djdefrag/QualityScaler?style=flat-square&color=success)](https://github.com/Djdefrag/QualityScaler/blob/main/LICENSE)

</div>

## 📑 Table of Contents
- [What is QualityScaler?](#-what-is-qualityscaler)
- [Features](#-features)
- [How to use QualityScaler?](#-how-to-use-qualityscaler)
- [Other AI projects](#-other-ai-projects)
- [Credits](#-credits)
- [Citations](#️-citations)
- [How is made](#️-how-is-made)
- [Make it work by yourself](#-make-it-work-by-yourself-)
- [Linux specifics](#-linux-specifics)
- [Requirements](#-requirements)
- [Roadmap](#️-roadmap)
- [Examples](#️-examples)

## ❓ What is QualityScaler?
QualityScaler is an AI app that enhances, upscales and de-noises photographs and videos.

This repository is the **Ubuntu / Linux port** of [Djdefrag/QualityScaler](https://github.com/Djdefrag/QualityScaler),
the original Windows app. One code base runs on both: DirectML on Windows, CUDA on Linux.
All credit for the application and the AI models belongs to the upstream author; see
[Credits](#-credits) and the MIT [LICENSE](LICENSE).

The port changes platform plumbing only - the AI engine, the upscale pipeline and the GUI are the
upstream ones. See [Linux specifics](#-linux-specifics) for the exact list.

## ✨ Features
- Elegant and easy to use GUI
- Image and video upscale
- Multiple GPUs support
- Compatible images - jpg, png, tif, bmp, webp, heic
- Compatible video - mp4, webm, mkv, flv, gif, avi, mov, mpg, qt, 3gp
- Automatic image tiling to avoid GPU VRAM limitation
- Resize image/video before upscaling
- Interpolation between the original file and the upscaled file
- Video upscaling STOP & RESUME
- 🔒 Privacy focused - no internet connection required, everything runs on your PC

## 🎬 How to use QualityScaler?
[movie_max_vp9.webm](https://github.com/user-attachments/assets/4a1984be-c8c8-464b-a3d1-43445635b165)

## 🤖 Other AI projects
- [RealScaler](https://github.com/Djdefrag/RealScaler) - image/video AI upscaler (Real-ESRGAN)
- [FluidFrames.RIFE](https://github.com/Djdefrag/FluidFrames.RIFE) - video AI frame generation

## 🙏 Credits
- [BSRGAN](https://github.com/cszn/BSRGAN)
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)
- [IRCNN](https://github.com/lipengFu/IRCNN)

## ❤️ Citations
- [80.lv - Great AI-powered tools for upscaling images](https://80.lv/articles/80-level-digest-great-ai-powered-tools-for-upscaling-images/)
- [TimeSaverVFX - AI Upscale](https://timesavervfx.com/ai-upscale/)

## 🛠️ How is made
QualityScaler is completely written in Python, from backend to frontend.
- [PyTorch](https://github.com/pytorch/pytorch)
- [ONNX](https://github.com/onnx/onnx)
- [onnxconverter-common](https://github.com/microsoft/onnxconverter-common)
- [onnxruntime-directml](https://github.com/microsoft/onnxruntime) (Windows) / [onnxruntime-gpu](https://github.com/microsoft/onnxruntime) (Linux)
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- [OpenCV](https://github.com/opencv/opencv)
- [PyInstaller](https://github.com/pyinstaller/pyinstaller)

## 🧑‍💻 Make it work by yourself
### Ubuntu / Linux

**Prerequisites**
- Python 3.10 – 3.13 with `venv` (`sudo apt install python3 python3-venv python3-tk`)
- FFmpeg 6 or newer (`sudo apt install ffmpeg`)
- NVIDIA driver for GPU inference (`nvidia-smi` must work); CPU inference works without it
- AI models: shipped in `AI-onnx/` and cloned with the repository (~120 MB)

**Getting started**

```bash
git clone https://github.com/yutthaphon/QualityScaler-Linux.git
cd QualityScaler-Linux

# The .onnx models are committed in AI-onnx/ and arrive with the clone.

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-linux.txt

.venv/bin/python QualityScaler.py
```

`requirements-linux.txt` installs `onnxruntime-gpu` plus the CUDA 12 / cuDNN 9 wheels it needs, so
nothing has to be downloaded from NVIDIA manually. If the driver or GPU is missing, the app starts
with the CPU provider and says so in the window title.

Headless server: prepend an X forward (`ssh -X`) or run under VNC/Xvfb.

Run the regression suite with:

```bash
.venv/bin/python -m unittest discover -s tests -v
# without a display:
xvfb-run -a -s '-screen 0 1920x1080x24' .venv/bin/python -m unittest discover -s tests -v
```

Two smoke tools exercise the real pipeline (they create their own test media and write to a
temporary directory):

```bash
.venv/bin/python tools/upscale_smoke.py                     # image + video, headless
xvfb-run -a .venv/bin/python tools/gui_upscale_smoke.py     # same through the GUI
```

Build a single-file binary with `tools/build-linux.sh` (needs `requirements-linux.txt`, writes
`dist/QualityScaler`).

### Windows / development

**Prerequisites**
- [Python](https://www.python.org/downloads/) installed on your PC
- [VSCode](https://code.visualstudio.com/) installed on your PC
- [ffmpeg.exe](https://www.gyan.dev/ffmpeg/builds/) downloaded (release build > ffmpeg-release-essentials.7z)

**Getting started**
- Download the project on your PC (green button Code > Download ZIP)
- Extract the project from the .zip (the `.onnx` models are already inside `AI-onnx/`)
- Extract `ffmpeg.exe` in the `/Assets` folder
- Open the project with VSCode (drag & drop the project directory onto VSCode)
- Click on `QualityScaler.py` in the left sidebar (VSCode will ask to install the Python extension)
- Install dependencies: open the VSCode "Terminal" panel and run `pip install -r requirements.txt`
- Close VSCode and re-open it (this refreshes all the installed dependencies)
- Click the "Play" button in the upper right corner of VSCode

## 🐧 Linux specifics

| Area | Windows | Ubuntu / Linux |
|---|---|---|
| AI engine | `onnxruntime-directml`, any DirectX 12 GPU | `onnxruntime-gpu`, NVIDIA GPU via CUDA (CPU fallback otherwise) |
| GPU enumeration | DXGI adapters | `nvidia-smi` (CUDA indexes), DRM/sysfs for AMD and Intel |
| FFmpeg | bundled `Assets/ffmpeg.exe` | system FFmpeg (`apt install ffmpeg`); a binary dropped in `Assets/` also wins |
| Hardware encode | NVENC / AMF / QSV | NVENC only — AMF and QSV are not in the Ubuntu FFmpeg build |
| CUDA deinterlacing | bundled FFmpeg | needs an FFmpeg with CUDA filters (the Ubuntu package has them) |
| Settings file | `~/Documents/QualityScaler_<version>_userpreference.json` | `~/.config/QualityScaler/QualityScaler_<version>_userpreference.json` |
| Sleep inhibition | `SetThreadExecutionState` | `systemd-inhibit` |
| Completion ping | Windows toast | `notify-send` (optional: `apt install libnotify-bin`) |

Only the encoders and filters that the installed FFmpeg actually provides are listed in the GUI, so a
missing driver cannot be selected by accident.

### Remote GPU servers (SSH / no monitor)
The app is a desktop GUI and needs an X server. For a rented GPU box without a display, forward one
from your workstation:

```bash
ssh -X user@gpu-host            # or: ssh -Y
# on the server, inside the project directory
python3 QualityScaler.py
```

Anything simpler (VNC, Xvfb + screenshots, batch scripts) works too; only Tk needs a display.

## 💻 Requirements
| Requirement | Minimum |
|---|---|
| OS | Ubuntu 22.04 / 24.04 LTS (tested on Debian 13), or Windows 10 / 11 |
| RAM | 8 GB or more |
| GPU (Linux) | NVIDIA GPU with a driver supporting CUDA 12 (tested: RTX 4050, driver 620) |
| GPU (Windows) | Any DirectX12 compatible GPU with ≥ 4GB VRAM |

## 🗺️ Roadmap

<details>
<summary>Click to expand full changelog</summary>

- [x] 1.X versions
    - [x] Switch to Pytorch-directml to support all Directx12 compatible gpu (AMD, Intel, Nvidia)
    - [x] New GUI with Windows 11 style
    - [x] Include audio for upscaled video
    - [x] Optimizing video frame resize and extraction speed
    - [x] Multi GPU support (for pc with double GPU, integrated + dedicated)
    - [x] Python 3.10 (expecting ~10% more performance)
- [x] 2.X versions
    - [x] New, completely redesigned graphical interface based on @customtkinter
    - [x] Upscaling images and videos at once (currently it is possible to upscale images or single video)
    - [x] Upscale multiple videos at once
    - [x] Choose upscaled video extension
    - [x] Interpolation between the original and upscaled image/video
    - [x] More Interpolation levels (Low, Medium, High)
    - [x] Show the remaining time to complete video upscaling
    - [x] Support for SRVGGNetCompact AI architecture
    - [x] Metadata extraction and application from original file to upscaled file (via exiftool)
- [x] 3.X versions
    - [x] New AI engine powered by onnxruntime-directml (https://github.com/microsoft/onnxruntime))
    - [x] Python 3.11 (performance improvements)
    - [x] Python 3.12 (performance improvements)
    - [x] Display images/videos upscaled resolution in the GUI
    - [x] Updated FFMPEG to version 7.x (latest release)
    - [x] Saving user settings (AI model, GPU, CPU  etc.)
    - [x] Video AI multi-threading upscale 
    - [x] Video upscaling STOP&RESUME
- [x] 4.X version
    - [x] Hardware accelerated video encoding (nvenc / amf / qsv)
    - [x] More video extensions (.mp4 / .mkv / .avi / .mov)
    - [x] Choose output resolution scaling
    - [x] Video AI multi-threading improvements
    - [x] Updated AI-engine (onnxruntime-directml)
    - [x] Video frames extraction by FFMPEG (x10 times faster)
- [ ] 2026.X version
    - [x] Implement new AI models
    - [x] App interface % scaling
    - [ ] TTA upscale mode

</details>

## 🖼️ Examples

#### Videos
![original](https://user-images.githubusercontent.com/32263112/209139620-bdd028f8-d5fc-40de-8f3d-6b80a14f8aab.gif)

https://user-images.githubusercontent.com/32263112/209139639-2b123b83-ac6e-4681-b94a-954ed0aea78c.mp4

#### Images
![test](https://user-images.githubusercontent.com/32263112/166690007-f1601487-7b94-4f2c-b4e2-436bc189a26e.png)

![ORIGINAL](https://user-images.githubusercontent.com/32263112/226847190-e4dbda21-8896-456d-8120-3137f3d2ac62.png)

![Bsrgan x4](https://user-images.githubusercontent.com/32263112/168884625-c869baee-4cca-4a33-bdad-b65d9c29889d.png)

![Bsrgan x4 (2)](https://user-images.githubusercontent.com/32263112/197983965-40785dbd-78c6-48a0-a1eb-39d9c3278f42.png)

![Bsrgan x4 (3)](https://user-images.githubusercontent.com/32263112/197983979-5857a855-d402-4fab-9217-ee5bd057bd01.png)

![Bsrgan x4](https://user-images.githubusercontent.com/32263112/198290909-277e176e-ccb4-4a4b-8531-b182a18d566a.png)


