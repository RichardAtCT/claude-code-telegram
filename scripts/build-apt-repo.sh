#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <repo_dir> <deb_file> <gpg_key_id>" >&2
  exit 1
fi

REPO_DIR="$1"
DEB_FILE="$2"
GPG_KEY_ID="$3"

if ! command -v apt-ftparchive >/dev/null 2>&1; then
  echo "apt-ftparchive is required (install apt-utils)" >&2
  exit 1
fi

if [[ ! -f "$DEB_FILE" ]]; then
  echo "Debian package not found: $DEB_FILE" >&2
  exit 1
fi

mkdir -p "$REPO_DIR/pool/main/c/claude-code-telegram"
mkdir -p "$REPO_DIR/dists/stable/main/binary-all"
mkdir -p "$REPO_DIR/dists/stable/main/binary-amd64"

cp -f "$DEB_FILE" "$REPO_DIR/pool/main/c/claude-code-telegram/"

pushd "$REPO_DIR" >/dev/null

apt-ftparchive packages pool/main > dists/stable/main/binary-all/Packages
gzip -kf dists/stable/main/binary-all/Packages
cp dists/stable/main/binary-all/Packages dists/stable/main/binary-amd64/Packages
gzip -kf dists/stable/main/binary-amd64/Packages

cat > apt-ftparchive.conf <<CONF
APT::FTPArchive::Release {
  Origin "claude-code-telegram";
  Label "claude-code-telegram";
  Suite "stable";
  Codename "stable";
  Architectures "amd64 all";
  Components "main";
  Description "APT repository for claude-code-telegram";
};
CONF

apt-ftparchive -c apt-ftparchive.conf release dists/stable > dists/stable/Release

GPG_ARGS=(--batch --yes --pinentry-mode loopback -u "$GPG_KEY_ID")
if [[ -n "${GPG_PASSPHRASE:-}" ]]; then
  GPG_ARGS+=(--passphrase "$GPG_PASSPHRASE")
fi

gpg "${GPG_ARGS[@]}" --armor --detach-sign -o dists/stable/Release.gpg dists/stable/Release
gpg "${GPG_ARGS[@]}" --clearsign -o dists/stable/InRelease dists/stable/Release

gpg --armor --export "$GPG_KEY_ID" > claude-code-telegram-archive-keyring.asc
gpg --export "$GPG_KEY_ID" > claude-code-telegram-archive-keyring.gpg

rm -f apt-ftparchive.conf

cat > index.html <<HTML
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>claude-code-telegram APT repository</title>
  </head>
  <body>
    <h1>claude-code-telegram APT repository</h1>
    <p>This GitHub Pages site serves an APT repository.</p>
  </body>
</html>
HTML

popd >/dev/null
