"""Tests of the game, run with the oolite-ui-test-framework (see ../../tools/oolite-ui-test-framework/README.md). Normally started by its `uitest` command, which runs
them in a Docker image per environment; they need an AppImage (--wmt-app) and an environment (--wmt-env)."""
pytest_plugins = ["oolite_ui_test_framework.plugin"]
