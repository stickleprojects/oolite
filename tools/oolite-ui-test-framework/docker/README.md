# Docker images

One Dockerfile per family of environments: `Dockerfile.arch`, `Dockerfile.debian`, `Dockerfile.wayland`. Each image has python3,
pytest, python-xlib, tesseract and Pillow, plus that family's window managers or compositors. Which environment uses which image is
set by `image =` in `../environments.toml`.

`uitest` builds an image the first time it is needed and tags it `oolite-uitest-<name>`. To build one by hand, from
`tools/oolite-ui-test-framework/`:

    docker build -f docker/Dockerfile.debian -t oolite-uitest-debian .

Also here: `fakeinput.c` (sends keys and the mouse through KWin's fake-input protocol; built into the Wayland image as `uitest-fakeinput`), `wlrinput.c` (the same for sway, through the standard virtual-keyboard and virtual-pointer protocols; built as `uitest-wlrinput`, with `virtual-keyboard-unstable-v1.xml` from wlroots 0.19.0, which no Arch package ships) and `run-ocr-tests.sh [image]`
(runs the OCR tests inside an image).
