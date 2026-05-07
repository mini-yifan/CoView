"""
样式定义模块

定义GUI界面的样式常量。
"""


class Styles:
    """样式定义类"""

    MAIN_WINDOW_STYLE = """
        QWidget {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #f0f4ff, stop:0.5 #f5f0ff, stop:1 #f0f8ff);
        }
    """

    TITLE_LABEL_STYLE = """
        QLabel {
            color: #4a5568;
            padding: 12px 20px;
            margin-bottom: 4px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(99,102,241,0.08), stop:1 rgba(168,85,247,0.08));
            border-radius: 14px;
            font-weight: bold;
            border: none;
        }
    """

    INPUT_STYLE = """
        QLineEdit {
            padding: 12px 16px;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            background-color: #ffffff;
            color: #2d3748;
            font-size: 11pt;
        }
        QLineEdit:focus {
            border-color: #818cf8;
            background-color: #ffffff;
            outline: none;
        }
        QLineEdit::placeholder {
            color: #a0aec0;
        }
    """

    TEXT_EDIT_STYLE = """
        QTextEdit {
            padding: 14px 16px;
            border: 2px solid #e2e8f0;
            border-radius: 14px;
            background-color: #ffffff;
            color: #2d3748;
            font-size: 11pt;
            line-height: 1.5;
        }
        QTextEdit:focus {
            border-color: #818cf8;
            background-color: #ffffff;
            outline: none;
        }
        QTextEdit::placeholder {
            color: #a0aec0;
            font-size: 11pt;
        }
    """

    PRIMARY_BUTTON_STYLE = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #6366f1, stop:1 #8b5cf6);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 12px;
            font-weight: bold;
            min-height: 42px;
            font-size: 12pt;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #818cf8, stop:1 #a78bfa);
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #4f46e5, stop:1 #7c3aed);
        }
        QPushButton:disabled {
            background: #e2e8f0;
            color: #a0aec0;
        }
    """

    SECONDARY_BUTTON_STYLE = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #f1f5f9, stop:1 #e2e8f0);
            color: #475569;
            border: 2px solid #e2e8f0;
            padding: 12px 24px;
            border-radius: 12px;
            font-weight: bold;
            min-height: 42px;
            font-size: 12pt;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #e2e8f0, stop:1 #cbd5e1);
            border-color: #cbd5e1;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #cbd5e1, stop:1 #94a3b8);
        }
        QPushButton:disabled {
            background: #f1f5f9;
            color: #cbd5e1;
            border-color: #f1f5f9;
        }
    """

    STATUS_READY_STYLE = """
        QLabel {
            color: #6366f1;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(99,102,241,0.08), stop:1 rgba(168,85,247,0.08));
            padding: 12px 16px;
            border-radius: 12px;
            margin-top: 4px;
            font-weight: bold;
            border: none;
            font-size: 11pt;
        }
    """

    STATUS_RUNNING_STYLE = """
        QLabel {
            color: #3b82f6;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(59,130,246,0.08), stop:1 rgba(99,102,241,0.08));
            padding: 12px 16px;
            border-radius: 12px;
            margin-top: 4px;
            font-weight: bold;
            border: none;
            font-size: 11pt;
        }
    """

    STATUS_STOPPING_STYLE = """
        QLabel {
            color: #f59e0b;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(245,158,11,0.08), stop:1 rgba(251,146,60,0.08));
            padding: 12px 16px;
            border-radius: 12px;
            margin-top: 4px;
            font-weight: bold;
            border: none;
            font-size: 11pt;
        }
    """

    STATUS_ERROR_STYLE = """
        QLabel {
            color: #ef4444;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(239,68,68,0.08), stop:1 rgba(248,113,113,0.08));
            padding: 12px 16px;
            border-radius: 12px;
            margin-top: 4px;
            font-weight: bold;
            border: none;
            font-size: 11pt;
        }
    """

    STATUS_SUCCESS_STYLE = """
        QLabel {
            color: #10b981;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(16,185,129,0.08), stop:1 rgba(52,211,153,0.08));
            padding: 12px 16px;
            border-radius: 12px;
            margin-top: 4px;
            font-weight: bold;
            border: none;
            font-size: 11pt;
        }
    """

    LOG_WINDOW_STYLE = """
        QWidget {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #f8fafc, stop:1 #f1f5f9);
        }
    """

    LOG_TEXT_STYLE = """
        QTextEdit {
            background-color: #1e293b;
            color: #e2e8f0;
            border: none;
            border-radius: 12px;
            padding: 12px;
            selection-background-color: #475569;
        }
    """

    MODEL_OUTPUT_STYLE = """
        QTextEdit {
            background-color: #ffffff;
            color: #334155;
            border: 2px solid #e2e8f0;
            border-radius: 14px;
            padding: 12px 16px;
            selection-background-color: #c7d2fe;
        }
    """

    CLEAR_BUTTON_STYLE = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ef4444, stop:1 #f87171);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #dc2626, stop:1 #ef4444);
        }
    """

    SAVE_BUTTON_STYLE = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #10b981, stop:1 #34d399);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #059669, stop:1 #10b981);
        }
    """

    SETTINGS_BUTTON_STYLE = """
        QPushButton {
            background-color: transparent;
            color: #6366f1;
            border: 2px solid #e2e8f0;
            padding: 8px 16px;
            border-radius: 10px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: rgba(99,102,241,0.06);
            border-color: #c7d2fe;
        }
        QPushButton:pressed {
            background-color: rgba(99,102,241,0.12);
        }
    """

    SETTINGS_LABEL_STYLE = """
        QLabel {
            color: #64748b;
            font-size: 9pt;
            font-weight: bold;
            padding: 0px;
            margin: 0px;
        }
    """

    SETTINGS_INPUT_STYLE = """
        QLineEdit {
            padding: 8px 12px;
            border: 2px solid #e2e8f0;
            border-radius: 10px;
            background-color: #ffffff;
            color: #334155;
            font-size: 9pt;
        }
        QLineEdit:focus {
            border-color: #818cf8;
            background-color: #ffffff;
            outline: none;
        }
        QLineEdit::placeholder {
            color: #a0aec0;
        }
    """
