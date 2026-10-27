# Framework tests

The framework's own tests: fast and offline (no display, no game, no Docker). They check the framework, not the game; the tests of
the game are in [`tests/ui/`](../../../tests/ui/) at the repo root.

Run from `tools/oolite-ui-test-framework/`:

    python3 -m pytest tests -q            # about 40 s; the OCR tests skip without tesseract
    docker/run-ocr-tests.sh [image]       # the OCR tests with real tesseract, inside one of the Docker images

| Path | What it holds |
|---|---|
| `test_<module>.py` | one file per module of `src/oolite_ui_test_framework/` (`test_report.py` tests `report.py`, and so on) |
| `test_plugin.py` | runs the real game tests against fake launches (pytester) |
| `ui/components/` | one test file per screen component |
| `fixtures/` | sample screenshots and raw result files |
| `ocr_strings.py` | strings used to generate text images for the OCR tests; add more here |
