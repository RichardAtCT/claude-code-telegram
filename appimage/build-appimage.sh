#!/usr/bin/env bash
#
# Build AppImage for MultiCode AI Bot
#
# Requirements:
#   - appimagetool (https://github.com/AppImage/AppImageKit/releases)
#   - Python 3.10+
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/build"
APPDIR="$BUILD_DIR/MultiCodeBot.AppDir"

echo "==> Building MultiCode AI Bot AppImage"

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR"

# Create AppDir structure
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Install Python and dependencies
echo "==> Installing Python environment..."
cd "$PROJECT_ROOT"

# Use system Python or bundled Python
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)

if command -v poetry &> /dev/null; then
    poetry install --no-dev
    POETRY_VENV=$(poetry env info --path)

    # Copy Python environment
    cp -r "$POETRY_VENV"/* "$APPDIR/usr/"
else
    # Fallback to pip
    pip3 install --target="$APPDIR/usr/lib/python$PYTHON_VERSION/site-packages" -r requirements.txt
fi

# Copy application
echo "==> Copying application..."
cp -r "$PROJECT_ROOT/src" "$APPDIR/usr/lib/"
cp "$PROJECT_ROOT/pyproject.toml" "$APPDIR/usr/lib/"

# Create launcher script
cat > "$APPDIR/usr/bin/multicode-bot" << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
export PYTHONPATH="$APPDIR/usr/lib:$PYTHONPATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$LD_LIBRARY_PATH"
cd "$APPDIR/usr/lib"
exec python3 -m src.main "$@"
EOF
chmod +x "$APPDIR/usr/bin/multicode-bot"

# Create AppRun
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
export PYTHONPATH="${HERE}/usr/lib:${PYTHONPATH}"
exec "${HERE}/usr/bin/multicode-bot" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Create desktop entry
cat > "$APPDIR/multicode-bot.desktop" << 'EOF'
[Desktop Entry]
Name=MultiCode AI Bot
Exec=multicode-bot
Icon=multicode-bot
Type=Application
Categories=Development;Utility;
Terminal=true
EOF

cp "$APPDIR/multicode-bot.desktop" "$APPDIR/usr/share/applications/"

# Create/copy icon (you'll need to provide an actual icon)
# For now, create a placeholder
cat > "$APPDIR/multicode-bot.svg" << 'EOF'
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
  <rect width="256" height="256" fill="#007ACC"/>
  <text x="128" y="140" font-size="80" text-anchor="middle" fill="white" font-family="Arial">MC</text>
</svg>
EOF

cp "$APPDIR/multicode-bot.svg" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
cp "$APPDIR/multicode-bot.svg" "$APPDIR/.DirIcon"

# Download appimagetool if not present
if ! command -v appimagetool &> /dev/null; then
    echo "==> Downloading appimagetool..."
    wget -c https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage \
        -O "$BUILD_DIR/appimagetool"
    chmod +x "$BUILD_DIR/appimagetool"
    APPIMAGETOOL="$BUILD_DIR/appimagetool"
else
    APPIMAGETOOL=appimagetool
fi

# Build AppImage
echo "==> Building AppImage..."
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$BUILD_DIR/MultiCode-AI-Bot-1.0.0-x86_64.AppImage"

echo "==> Done! AppImage created at:"
echo "    $BUILD_DIR/MultiCode-AI-Bot-1.0.0-x86_64.AppImage"
echo ""
echo "Run with:"
echo "    $BUILD_DIR/MultiCode-AI-Bot-1.0.0-x86_64.AppImage"
