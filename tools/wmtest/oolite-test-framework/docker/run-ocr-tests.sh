#!/bin/sh
# Run the OCR tests (real tesseract) inside a wmtest image. Usage: docker/run-ocr-tests.sh [image] [pytest args]
# The image is any image with python3, pytest and tesseract: wmtest-py-debian (default), wmtest-py-arch, wmtest-py-wayland, or your own.
# Also settable with OCR_TEST_IMAGE. Nothing is written to the host (the source is mounted read-only).
IMAGE="${1:-${OCR_TEST_IMAGE:-wmtest-py-debian}}"; [ $# -gt 0 ] && shift
HERE="$(cd "$(dirname "$0")/.." && pwd)"
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "image $IMAGE not found: build it first (docker build -f docker/Dockerfile.<name> -t $IMAGE .)"; exit 2; }
exec docker run --rm -v "$HERE":/wmtest:ro -w /wmtest --entrypoint python3 "$IMAGE" \
    -m pytest -p no:cacheprovider tests/test_ocr.py tests/test_ocr_tesseract.py tests/test_ocr_generated.py -v "$@"
