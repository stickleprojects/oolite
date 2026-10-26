"""Page objects, one module per game screen (title_menu.py, ...). Import from here: from oolite_ui_test_framework.ui.pages import TitleMenuPage."""
from .page import Page
from .title_menu import TitleMenuPage

__all__ = ["Page", "TitleMenuPage"]
