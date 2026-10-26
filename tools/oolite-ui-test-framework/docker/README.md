# Docker images

One Dockerfile per family of environments: `Dockerfile.arch`, `Dockerfile.debian`, `Dockerfile.wayland`. Each image has python3,
pytest, python-xlib, tesseract and Pillow, plus that family's window managers or compositors. Which environment uses which image is
set by `image =` in `../environments.toml`.

`uitest` builds an image the first time it is needed and tags it `oolite-uitest-<name>`. To build one by hand, from
`tools/oolite-ui-test-framework/`:

    docker build -f docker/Dockerfile.debian -t oolite-uitest-debian .

Also here: `fakekey.c` (sends keys through KWin's fake-input protocol; built into the Wayland image) and `run-ocr-tests.sh [image]`
(runs the OCR tests inside an image).
