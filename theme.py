"""
The look of the app: colored file folders on a dark wood desk, with ruled paper inside.
One appearance on every computer, on purpose.
"""

# The folder for each screen. fill = folder color, on = text on it, soft = quieter text on it.
FOLDERS = {
    "new":       dict(fill="#DDBE83", on="#2A2013", soft="#5A4A31"),
    "named":     dict(fill="#3F7D58", on="#FFFFFF", soft="#DCEBDF"),
    "review":    dict(fill="#E3B23C", on="#2A2013", soft="#5A4415"),
    "failed":    dict(fill="#B8433A", on="#FFFFFF", soft="#F6DAD6"),
    "completed": dict(fill="#3A6A9E", on="#FFFFFF", soft="#DBE6F2"),
}

DESK_TOP = "#46372C"
DESK_BOTTOM = "#2C221C"
CREAM = "#EADFCB"
INK = "#20242A"
PAPER = "#FCFAF4"
PAPER_BACK = "#EDE6D6"
RULE = "#E6DFCF"
MUTED = "#6F675A"
FAINT = "#A79E8E"
HIGHLIGHT = "#FFE259"
STAMP_BLUE = "#1F5FA8"
STAMP_AMBER = "#A8690A"
STAMP_RED = "#B3261E"

DISPLAY = '"Bahnschrift", "DIN Alternate", "Segoe UI"'
BODY = '"Segoe UI", "Helvetica Neue", Arial'

QSS = f"""
* {{ font-family: {BODY}; font-size: 14px; color: {INK}; }}
QMainWindow {{ background: {DESK_BOTTOM}; }}
QDialog {{ background: transparent; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {PAPER}; border: 1px solid {RULE}; padding: 4px; }}

#brand {{ font-family: {DISPLAY}; font-size: 17px; font-weight: 600; color: {CREAM}; }}
#brandVersion {{ font-size: 11px; color: rgba(234, 223, 203, 55%); }}
#demoChip {{ font-size: 12px; color: {HIGHLIGHT}; }}
QPushButton#deskLink {{ background: transparent; border: none; padding: 6px 2px; color: {CREAM}; }}
QPushButton#deskLink:hover {{ color: #FFFFFF; }}

#title {{ font-family: {DISPLAY}; font-size: 28px; font-weight: 600; }}
#guide {{ font-size: 13px; }}
#status {{ font-size: 13px; }}
#hint {{ font-size: 12px; }}
#hint[problem="true"] {{ font-weight: 700; }}

#paper {{ background: {PAPER}; border: none; border-radius: 2px; }}
#empty {{ font-family: {DISPLAY}; color: {FAINT}; font-size: 18px; }}
#welcomeTitle {{ font-family: {DISPLAY}; font-size: 24px; font-weight: 600; }}
#welcomeBody {{ color: {MUTED}; }}

QPushButton {{ border-radius: 3px; padding: 8px 16px; font-weight: 600; color: #FFFFFF; border: 1px solid #000000;
               background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #343A42, stop:1 {INK}); }}
QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #454C56, stop:1 #2B3037); }}
QPushButton:pressed {{ background: {INK}; }}
QPushButton:disabled {{ color: rgba(255, 255, 255, 45%); background: rgba(32, 36, 42, 45%); border-color: transparent; }}
QPushButton#quiet {{ background: {PAPER}; color: {INK}; border: 1px solid {FAINT}; font-weight: 500; }}
QPushButton#quiet:hover {{ background: #FFFFFF; border-color: {INK}; }}
QPushButton#quiet:disabled {{ color: {FAINT}; background: rgba(252, 250, 244, 45%); border-color: transparent; }}
QPushButton#link {{ background: transparent; border: none; padding: 6px 12px 6px 0; color: {MUTED}; font-weight: 400; }}
QPushButton#link:hover {{ color: {INK}; }}
QPushButton#stop {{ background: transparent; border: none; padding: 2px 4px; font-weight: 600; }}

QListWidget {{ background: transparent; border: none; outline: none; }}

QLineEdit {{ background: #FFFFFF; border: 1px solid {FAINT}; border-radius: 2px; padding: 9px 11px;
             selection-background-color: {HIGHLIGHT}; selection-color: {INK}; }}
QLineEdit:focus {{ border: 1px solid {INK}; }}
QPlainTextEdit {{ background: #FFFFFF; border: 1px solid {FAINT}; border-radius: 2px; padding: 5px 7px;
                  selection-background-color: {HIGHLIGHT}; selection-color: {INK}; }}
QPlainTextEdit:focus {{ border: 1px solid {INK}; }}
QLineEdit:disabled {{ color: {FAINT}; background: {PAPER_BACK}; }}
QLineEdit[problem="true"] {{ border: 2px solid {STAMP_RED}; }}
#nameEdit {{ font-size: 15px; }}

QComboBox {{ background: #FFFFFF; border: 1px solid {FAINT}; border-radius: 2px; padding: 8px 28px 8px 11px; }}
QComboBox:focus {{ border: 1px solid {INK}; }}
QComboBox::drop-down {{ border: none; width: 0; }}
QComboBox QAbstractItemView {{ background: #FFFFFF; border: 1px solid {FAINT}; outline: none;
                               selection-background-color: {HIGHLIGHT}; selection-color: {INK}; }}

QProgressBar {{ background: rgba(0, 0, 0, 18%); border: none; max-height: 5px; min-height: 5px; }}
QProgressBar::chunk {{ background: {INK}; }}

#card {{ background: {PAPER}; border: none; border-radius: 3px; }}
#cardTitle {{ font-family: {DISPLAY}; font-size: 22px; font-weight: 600; }}
#cardBody {{ color: {MUTED}; }}
#cardName {{ font-size: 15px; font-weight: 600; }}
#fieldLabel {{ color: {MUTED}; font-size: 12px; font-weight: 600; }}
#path {{ font-size: 13px; }}
#formHint {{ color: {MUTED}; font-size: 12px; }}
#formHint[problem="true"] {{ color: {STAMP_RED}; font-weight: 600; }}
#usage {{ color: {MUTED}; font-size: 11px; }}
#ruleWarning {{ color: {STAMP_AMBER}; font-size: 12px; font-weight: 600; }}
#ruleOption {{ font-weight: 600; spacing: 8px; padding-top: 3px; }}
#ruleOption::indicator {{ width: 14px; height: 14px; border-radius: 8px; border: 1px solid {FAINT}; background: #FFFFFF; }}
#ruleOption::indicator:hover {{ border-color: {INK}; }}
#ruleOption::indicator:checked {{ width: 6px; height: 6px; border: 5px solid {INK}; }}
#ruleWhy {{ color: {MUTED}; font-size: 12px; margin-left: 24px; }}
#keycap {{ background: #FFFFFF; border: 1px solid {FAINT}; border-bottom-width: 2px; border-radius: 3px;
           padding: 3px 9px; font-size: 12px; font-weight: 600; }}
#folderChip {{ border-radius: 3px; padding: 4px 10px; font-size: 12px; font-weight: 600; }}
#guideRow {{ padding-top: 3px; }}

#toast {{ background: {INK}; border-radius: 3px; }}
#toast QLabel {{ color: #FFFFFF; font-size: 13px; }}
#toast QPushButton {{ color: {HIGHLIGHT}; border: none; padding: 2px 6px; background: transparent; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 3px; }}
QScrollBar::handle:vertical {{ background: {RULE}; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def folder_style(view):
    f = FOLDERS[view]
    return (f"#title {{ color: {f['on']}; }} #guide, #status {{ color: {f['soft']}; }} "
            f"#hint {{ color: {f['soft']}; }} #hint[problem=\"true\"] {{ color: {f['on']}; }} "
            f"QPushButton#stop {{ color: {f['on']}; }}")
