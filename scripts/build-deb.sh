#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v poetry >/dev/null 2>&1; then
  echo "poetry is required to build the Debian package" >&2
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb is required to build the Debian package" >&2
  exit 1
fi

VERSION="$(poetry version -s)"

DEB_REVISION="${DEB_REVISION:-1}"
PKG_NAME="claude-code-telegram"
PKG_VERSION="${VERSION}-${DEB_REVISION}"
PKG_ARCH="all"

DIST_DIR="$ROOT_DIR/dist"
DEB_DIST_DIR="$DIST_DIR/deb"
BUILD_DIR="$ROOT_DIR/build/deb"
PACKAGE_ROOT="$BUILD_DIR/${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}"

rm -rf "$PACKAGE_ROOT"
mkdir -p "$PACKAGE_ROOT/DEBIAN"

poetry build -f wheel

WHEEL_PATH="$DIST_DIR/claude_code_telegram-${VERSION}-py3-none-any.whl"
if [[ ! -f "$WHEEL_PATH" ]]; then
  echo "Expected wheel not found: $WHEEL_PATH" >&2
  exit 1
fi

install -d "$PACKAGE_ROOT/usr/share/${PKG_NAME}/wheels"
install -m 0644 "$WHEEL_PATH" "$PACKAGE_ROOT/usr/share/${PKG_NAME}/wheels/"

install -d "$PACKAGE_ROOT/usr/bin"
install -m 0755 packaging/deb/claude-code-telegram "$PACKAGE_ROOT/usr/bin/claude-code-telegram"

install -d "$PACKAGE_ROOT/lib/systemd/system"
install -m 0644 packaging/deb/claude-code-telegram.service "$PACKAGE_ROOT/lib/systemd/system/claude-code-telegram.service"

install -d "$PACKAGE_ROOT/usr/share/doc/${PKG_NAME}"
install -m 0644 packaging/deb/claude-code-telegram.env.example "$PACKAGE_ROOT/usr/share/doc/${PKG_NAME}/claude-code-telegram.env.example"
install -m 0644 README.md "$PACKAGE_ROOT/usr/share/doc/${PKG_NAME}/README.md"

install -m 0755 packaging/deb/postinst "$PACKAGE_ROOT/DEBIAN/postinst"
install -m 0755 packaging/deb/prerm "$PACKAGE_ROOT/DEBIAN/prerm"
install -m 0755 packaging/deb/postrm "$PACKAGE_ROOT/DEBIAN/postrm"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<CONTROL
Package: ${PKG_NAME}
Version: ${PKG_VERSION}
Section: utils
Priority: optional
Architecture: ${PKG_ARCH}
Maintainer: Richard Atkinson <richardatk01@gmail.com>
Depends: adduser, bash, ca-certificates, python3 (>= 3.10), python3-venv
Homepage: https://github.com/RichardAtCT/claude-code-telegram
Description: Telegram bot for remote Claude Code access
 This package installs Claude Code Telegram Bot and a systemd service.
 During installation it creates a virtual environment in
 /opt/claude-code-telegram/venv and installs Python dependencies.
 Configure /etc/claude-code-telegram/claude-code-telegram.env
 before enabling the service.
CONTROL

mkdir -p "$DEB_DIST_DIR"
OUTPUT_DEB="$DEB_DIST_DIR/${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}.deb"

dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" "$OUTPUT_DEB" >/dev/null

echo "Built Debian package: $OUTPUT_DEB"
