"""Strings the OCR must read correctly, drawn by test_ocr_generated.py on every colour pair below. ADD MORE HERE: one string per line,
no other change is needed. Use the real strings Oolite shows (menu items, headings, button labels). Keep each short and on one line."""
STRINGS = [
    "Start New Commander",
    "Load Commander",
    "View Ship Library",
    "Game Options",
    "Manage Expansion Packs",
    "Exit Game",
    "Press Space Commander",
    "Docked",
]

# (name, text colour, background colour). The game draws yellow on black for items and black on red for the selected item.
COLOUR_PAIRS = [
    ("yellow-on-black", (255, 255, 0), (0, 0, 0)),
    ("black-on-red", (0, 0, 0), (255, 0, 0)),
    ("white-on-blue", (255, 255, 255), (0, 0, 255)),
    ("yellow-on-blue", (255, 255, 0), (0, 0, 255)),
    ("white-on-red", (255, 255, 255), (255, 0, 0)),
    ("black-on-yellow", (0, 0, 0), (255, 255, 0)),
]

FONT_SIZES = [18, 24]       # pixel heights; Oolite's menu text at 720p is about 18-24 px
