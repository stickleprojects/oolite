# Framework tests

The framework's own tests: fast and offline (no display, no game, no Docker). They check the framework, not the game; the tests of
the game are in [`tests/ui/`](../../../tests/ui/) at the repo root.

Run from `tools/oolite-ui-test-framework/`:

    docker/run-framework-tests.sh [image] # the whole suite inside a Docker image with tesseract: nothing skips (about 4 min)
    python3 -m pytest tests -q            # on the host: about 1 min, but the OCR tests skip without tesseract
    docker/run-ocr-tests.sh [image]       # only the OCR tests, inside a Docker image

Use `run-framework-tests.sh` for a full result: a skipped OCR test is a gap, not a pass. It mounts the whole repository, because
`test_plugin.py` reads the game's tests in `tests/ui/` at the repo root; mounting only this folder makes those tests fail with
`FileNotFoundError: '/tests/ui/...'`.

| Path | What it holds |
|---|---|
| `test_<module>.py` | one file per module of `src/oolite_ui_test_framework/` (`test_report.py` tests `report.py`, and so on) |
| `test_plugin.py` | runs the real game tests against fake launches (pytester) |
| `ui/components/` | one test file per screen component |
| `fixtures/` | sample screenshots and raw result files |
| `ocr_strings.py` | strings used to generate text images for the OCR tests; add more here |
