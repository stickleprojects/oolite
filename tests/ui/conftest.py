"""Tests of the game, run with the oolite-ui-test-framework (see ../../tools/oolite-ui-test-framework/README.md). Normally started by its `uitest` command, which runs
them in a Docker image per environment; they need an AppImage (--ui-app) and an environment (--ui-env)."""
pytest_plugins = ["oolite_ui_test_framework.plugin"]
