#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
ZIP_PATH="$ROOT_DIR/lambda.zip"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

python3 -m pip install -r "$ROOT_DIR/requirements.txt" -t "$BUILD_DIR"
cp -R "$ROOT_DIR/weather_bot" "$BUILD_DIR/"

(
  cd "$BUILD_DIR"
  zip -qr "$ZIP_PATH" .
)

echo "Created $ZIP_PATH"
