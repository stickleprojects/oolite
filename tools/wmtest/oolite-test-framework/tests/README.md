# Tests of the framework itself

Fast offline tests (no display, no game, no Docker needed except the OCR ones inside an image). The tests of the game are in `/tests` at the repo root.

    python3 -m pytest tests -q                 # from oolite-test-framework/ ; pythonpath comes from pytest.ini
    docker/run-ocr-tests.sh [image]            # the OCR tests with real tesseract, in any image

Files are flat, one per module of `src/oolite_test_framework/` (`test_ocr.py` -> `ocr.py`, `test_verdict.py` -> `verdict.py`, ...). `test_plugin.py` runs the real
game tests against fake launch fixtures with pytester. `ui/components/` has one test file per component. `fixtures/` holds the sample screenshots.
`ocr_strings.py` is the list of strings used to generate text images; add more strings there. Naming of these files is tracked in issue #2.
