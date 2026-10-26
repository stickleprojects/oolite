"""Tests of the game, run with the oolite-test-framework (see ../oolite-test-framework/README.md). Normally started by its `wmtest` command, which runs
them in a Docker image per environment; they need an AppImage (--wmt-app) and an environment (--wmt-env)."""
pytest_plugins = ["oolite_test_framework.plugin"]
