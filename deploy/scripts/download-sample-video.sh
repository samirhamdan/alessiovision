#!/usr/bin/env sh
# Baixa o vídeo de pedestres de exemplo do OpenCV para deploy/data/demo.avi.
set -eu
cd "$(dirname "$0")/.."
mkdir -p data
curl -fL -o data/demo.avi https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/vtest.avi
echo "vídeo salvo em deploy/data/demo.avi"
