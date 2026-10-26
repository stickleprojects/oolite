# Docker images

One Dockerfile per environment family: `Dockerfile.debian`, `Dockerfile.arch`, `Dockerfile.wayland`. Each has python3, pytest, python-xlib, tesseract and Pillow, plus the
window managers / compositors of that family. Images are tagged `wmtest-py-<name>` and built on first use by `wmtest` (or by hand:
`docker build -f docker/Dockerfile.debian -t wmtest-py-debian .`). The framework is mounted at `/wmtest` and the game tests at `/gametests`; `PYTHONPATH=/wmtest/src`.
`run-ocr-tests.sh [image]` runs the OCR tests in any image.
