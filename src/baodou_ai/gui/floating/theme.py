"""Black, white, and gray theme constants for the floating overlay."""

from __future__ import annotations

PALETTE = {
    "black": "#111111",
    "white": "#FFFFFF",
    "panel_bg": "#FFFFFF",
    "input_bg": "#EEEEEE",
    "text": "#111111",
    "muted": "#707070",
    "placeholder": "#777777",
    "border": "#DDDDDD",
    "border_dark": "#999999",
    "scrollbar": "#A0A0A0",
    "status": "#555555",
    "status_muted": "rgba(120, 120, 120, 180)",
    "timestamp": "rgba(120, 120, 120, 160)",
}

def input_style() -> str:
    return f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {PALETTE["text"]};
                font-size: 15px;
                padding: 0px;
            }}
            QLineEdit::placeholder {{
                color: {PALETTE["placeholder"]};
            }}
            """


def scroll_area_style() -> str:
    return f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {PALETTE["scrollbar"]};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            """


def user_bubble_style() -> str:
    return f"""
            QLabel {{
                background-color: {PALETTE["black"]};
                border: 1px solid {PALETTE["black"]};
                border-radius: 14px;
                color: {PALETTE["white"]};
                font-size: 15px;
                padding: 10px 14px;
            }}
            """


def result_card_style() -> str:
    return f"""
            QLabel {{
                background-color: {PALETTE["white"]};
                border: 1px solid {PALETTE["border"]};
                border-radius: 14px;
                color: {PALETTE["text"]};
                font-size: 15px;
                padding: 10px 14px;
            }}
            """


def status_bubble_style() -> str:
    return f"""
            QLabel {{
                background-color: transparent;
                border: none;
                color: {PALETTE["status"]};
                font-size: 15px;
                padding: 0px 14px;
            }}
            """


def intermediate_report_style() -> str:
    return f"""
            QLabel {{
                background-color: transparent;
                border: none;
                color: {PALETTE["status_muted"]};
                font-size: 13px;
                padding: 2px 14px;
            }}
            """


def timestamp_style() -> str:
    return f"""
            QLabel {{
                background-color: transparent;
                border: none;
                color: {PALETTE["timestamp"]};
                font-size: 11px;
                padding: 0px 14px;
            }}
            """


def menu_style() -> str:
    return f"""
            QMenu {{
                background-color: {PALETTE["white"]};
                border: 1px solid {PALETTE["border"]};
                border-radius: 12px;
                padding: 8px;
            }}
            QMenu::item {{
                padding: 8px 22px;
                border-radius: 8px;
                color: {PALETTE["text"]};
            }}
            QMenu::item:selected {{
                background-color: #EEEEEE;
                color: {PALETTE["black"]};
            }}
            """
