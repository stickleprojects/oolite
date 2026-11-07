**Problem:** the UI-test framework's stages (start the desktop, launch the game, observe the window, tidy up) live inside Python (`session.py`, `scenarios.py`, the `start` lines in `environments.toml`). No stage can be run alone, so debugging one environment means writing throwaway scripts. That happened on #75.

**Goal:** every stage is a script that can be run and debugged by hand, inside one container, for one build. The test runner runs the same scripts in order.

**Stages**
1. **Image**: one Dockerfile per distro version, installing that distro's standard packages (e.g. `ubuntu-desktop` on Ubuntu 26.04, as a user would have).
2. **Start**: start the desktop and set the environment variables.
3. **Launch**: one launcher for Linux (chmod +x, `APPIMAGE_EXTRACT_AND_RUN`, game log location) and a separate one for Windows.
4. **Observe**: window info (title bar, focus, position) and screenshots.
5. **Tests**: `tests/ui`, calling observe.
6. **Collect**: copy out logs, screenshots and results.
7. **Tidy up**.

**Open design question (under discussion):** how to organise the scripts across distros, desktops and X11/Wayland, i.e. separate distro and desktop axes, or one folder per distro+desktop combination that inherits defaults and overrides them. To be settled before any code.

Related: #75 (where the need showed up), #45 (observing native Wayland windows).
