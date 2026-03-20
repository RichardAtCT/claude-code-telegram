# Local Voice Transcription with whisper.cpp

This guide explains how to build and configure [whisper.cpp](https://github.com/ggerganov/whisper.cpp) for **offline** voice message transcription — no API keys or cloud services required.

## Overview

When `VOICE_PROVIDER=local` the bot transcribes Telegram voice messages entirely on your machine using:

| Component | Purpose |
|---|---|
| **ffmpeg** | Converts Telegram OGG/Opus audio to 16 kHz mono WAV |
| **whisper.cpp** | Runs OpenAI's Whisper model locally via optimised C/C++ |
| **GGML model** | Quantised model weights (downloaded once) |

## Prerequisites

- A C/C++ toolchain (`gcc`/`clang`, `cmake`, `make`)
- `ffmpeg` installed and on PATH
- ~400 MB disk space for the `base` model (~1.5 GB for `medium`)

## 1. Install ffmpeg

### Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y ffmpeg
```

### macOS (Homebrew)

```bash
brew install ffmpeg
```

### Alpine

```bash
apk add ffmpeg
```

Verify:

```bash
ffmpeg -version
```

## 2. Build whisper.cpp from source

```bash
# Clone the repository
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp

# Build with CMake (recommended)
cmake -B build
cmake --build build --config Release

# The binary is at build/bin/whisper-cli (or build/bin/main on older versions)
ls build/bin/whisper-cli
```

> **Tip:** For GPU acceleration add `-DWHISPER_CUBLAS=ON` (NVIDIA) or `-DWHISPER_METAL=ON` (Apple Silicon) to the cmake configure step.

### Install system-wide (optional)

```bash
sudo cp build/bin/whisper-cli /usr/local/bin/whisper-cpp
```

Or add the build directory to your `PATH`:

```bash
export PATH="$PWD/build/bin:$PATH"
```

## 3. Download a GGML model

Models are hosted on Hugging Face. Pick one based on your hardware:

| Model | Size | RAM (approx.) | Quality |
|---|---|---|---|
| `tiny` | ~75 MB | ~400 MB | Fast but lower accuracy |
| `base` | ~142 MB | ~500 MB | Good balance (default) |
| `small` | ~466 MB | ~1 GB | Better accuracy |
| `medium` | ~1.5 GB | ~2.5 GB | High accuracy |
| `large-v3` | ~3 GB | ~5 GB | Best accuracy, slow on CPU |

```bash
# Create the model cache directory
mkdir -p ~/.cache/whisper-cpp

# Download the base model (recommended starting point)
curl -L -o ~/.cache/whisper-cpp/ggml-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# Or download small for better accuracy
curl -L -o ~/.cache/whisper-cpp/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

## 4. Configure the bot

Add the following to your `.env`:

```bash
# Enable voice transcription with local provider
ENABLE_VOICE_MESSAGES=true
VOICE_PROVIDER=local

# Path to the whisper.cpp binary (omit if already on PATH as "whisper-cpp")
WHISPER_CPP_BINARY_PATH=/usr/local/bin/whisper-cpp

# Model: a name like "base", "small", "medium" or a full file path
# Named models resolve to ~/.cache/whisper-cpp/ggml-{name}.bin
WHISPER_CPP_MODEL_PATH=base
```

### Minimal configuration

If `whisper-cpp` is on your PATH and you downloaded the `base` model to the default location, you only need:

```bash
VOICE_PROVIDER=local
```

## 5. Verify the setup

```bash
# Test ffmpeg conversion
ffmpeg -f lavfi -i "sine=frequency=440:duration=2" -ar 16000 -ac 1 /tmp/test.wav -y

# Test whisper.cpp
whisper-cpp -m ~/.cache/whisper-cpp/ggml-base.bin -f /tmp/test.wav --no-timestamps
```

You should see a transcription attempt (it will be empty or nonsensical for a sine wave, but the binary should run without errors).

## Troubleshooting

### `whisper.cpp binary not found on PATH`

The bot could not locate the binary. Either:
- Install it system-wide: `sudo cp build/bin/whisper-cli /usr/local/bin/whisper-cpp`
- Or set the full path: `WHISPER_CPP_BINARY_PATH=/path/to/whisper-cli`

### `whisper.cpp model not found`

The model file does not exist at the expected path. Download it:

```bash
mkdir -p ~/.cache/whisper-cpp
curl -L -o ~/.cache/whisper-cpp/ggml-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
```

### `ffmpeg is required but was not found`

Install ffmpeg for your platform (see step 1 above).

### Poor transcription quality

- Try a larger model (`small` or `medium` instead of `base`)
- Ensure audio is not too short (< 1 second) or too noisy
- whisper.cpp uses `--language auto` by default; this works well for most languages

### High CPU usage / slow transcription

- Use a smaller model (`tiny` or `base`)
- Enable GPU acceleration when building whisper.cpp (CUDA / Metal)
- Consider using the `mistral` or `openai` cloud providers for faster results on low-powered machines
