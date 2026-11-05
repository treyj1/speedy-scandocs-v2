"""
Speedy Scandocs: the app window. Start it with "Speedy Scandocs.vbs" (Windows) or
"Speedy Scandocs.command" (Mac). A packaged release is just the app.

    python app.py          normal use
    python app.py --demo   practice with the sample scans. No AI, no key, nothing real is touched.
    python app.py --self-check=report.txt   prove a packaged copy works. See self_check.py.

All the file and Claude work is in engine.py. This file is only the window.
"""

import os
import shutil
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import (QEvent, QLockFile, QPoint, QPointF, QRectF, QSize, QStringListModel, Qt, QThread, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QImage, QKeySequence,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QCompleter,
                               QDialog,
                               QFileDialog, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QRadioButton, QStackedLayout, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

import engine
import self_check
import theme
import tour

HERE = Path(__file__).resolve().parent
VIEWS = ("new", "named", "review", "failed", "completed")
TITLES = {"new": "Home", "named": "Named", "review": "Review", "failed": "Failed", "completed": "Ready to File"}

GUIDE = {
    "new": "Check the folder to see what came in, then Auto Process to name everything.",
    "named": "These matched a client on your list. Press Space to read one, Enter if the name is right, "
             "or fix it below.",
    "review": "A new client, or Claude wasn't sure which client. The reason is under each file.",
    "failed": "Claude couldn't name these. Read the file, type the name below, and press Enter.",
    "completed": "These are ready. Open the folder and move each file to its client's folder.",
}
EMPTY = {
    "new": "No new scans.",
    "named": "This folder is empty.",
    "review": "Nothing to review.",
    "failed": "Nothing failed.",
    "completed": "Nothing ready to file yet.",
}
STAMP_COLORS = {"New client": theme.STAMP_BLUE, "Check": theme.STAMP_AMBER,
                "No name": theme.STAMP_RED, "Error": theme.STAMP_RED}


RULE_CAUTION = ("This uses AI tokens, so only continue if you've tested things and you're confident "
                "a new rule is needed.")


def usage_line(label, usage):
    cost = usage["cost"]
    money = "$0.00" if not cost else "under $0.01" if cost < 0.01 else f"about ${cost:,.2f}"
    return f"{label}: {usage['input']:,} input tokens, {usage['output']:,} output tokens, {money}"


def tinted(color, alpha):
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def display_font(size, weight=QFont.DemiBold):
    font = QFont("Bahnschrift")
    font.setFamilies(["Bahnschrift", "DIN Alternate", "Segoe UI"])
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


class Row(QStyledItemDelegate):
    """One line on the page: client, description, Claude's note, and a stamp if it needs one."""

    HEIGHT = 58

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, p, option, index):
        item = index.data(Qt.UserRole)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect)
        if option.state & QStyle.State_Selected:
            p.fillRect(r.adjusted(0, 1, 0, -1), tinted(theme.HIGHLIGHT, 185))     # a stroke of highlighter
        elif option.state & QStyle.State_MouseOver:
            p.fillRect(r.adjusted(0, 1, 0, -1), QColor("#F5EFE1"))
        p.setPen(QColor(theme.RULE))
        p.drawLine(r.bottomLeft() + QPointF(0, -0.5), r.bottomRight() + QPointF(0, -0.5))

        left, right = r.left() + 18, r.right() - 16
        if item.tag:
            right -= self.draw_stamp(p, item.tag, right, r.center().y()) + 16

        client, sep, description = item.stem.partition(" - ")
        strong = QFont(option.font)
        strong.setPixelSize(14)
        strong.setWeight(QFont.DemiBold)
        plain = QFont(option.font)
        plain.setPixelSize(14)
        small = QFont(option.font)
        small.setPixelSize(12)
        reason = item.reason if item.bucket != "completed" else ""
        top = r.top() + (9 if reason else 0)
        height = 22 if reason else r.height()
        if sep:
            column = min((right - left) * 0.36, 300)
            p.setFont(strong)
            p.setPen(QColor(theme.INK))
            p.drawText(QRectF(left, top, column - 14, height), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(strong).elidedText(client, Qt.ElideRight, int(column - 14)))
            text_left = left + column
        else:
            description, text_left = item.stem, left
        p.setFont(plain)
        p.setPen(QColor(theme.INK))
        p.drawText(QRectF(text_left, top, right - text_left, height), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(plain).elidedText(description, Qt.ElideMiddle, int(right - text_left)))
        if reason:
            p.setFont(small)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(text_left, top + 22, right - text_left, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(small).elidedText(reason, Qt.ElideRight, int(right - text_left)))
        p.restore()

    def draw_stamp(self, p, tag, right, y):
        """Red-ink style stamp, set slightly crooked the way a hand would. Returns its width."""
        font = display_font(12)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        text = tag.upper()
        width = QFontMetrics(font).horizontalAdvance(text) + 16
        color = tinted(STAMP_COLORS.get(tag, theme.STAMP_AMBER), 215)
        p.save()
        p.translate(right - width / 2, y)
        p.rotate(-2.5)
        box = QRectF(-width / 2, -11, width, 22)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, 1.5))
        p.drawRoundedRect(box, 2, 2)
        p.setFont(font)
        p.drawText(box, Qt.AlignCenter, text)
        p.restore()
        return width


class ClientCompleter(QCompleter):
    """
    Suggests clients while typing the part of the name before ' - '. Enter picks a suggestion
    only if one was highlighted with the arrow keys. Otherwise it means the name is done.
    """

    entered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(QStringListModel(self))
        self.setCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterMode(Qt.MatchContains)

    def set_clients(self, clients):
        self.model().setStringList(clients)

    def splitPath(self, path):
        client, sep, _ = path.partition(" - ")
        if sep and self.widget().cursorPosition() >= len(client) + len(sep):
            return ["\n"]                     # typing the description: nothing can match this
        return [client]

    def eventFilter(self, watched, event):
        # While the list is open it gets the keys, so the name box never sees this Enter.
        if (event.type() == QEvent.KeyPress and watched is self.popup()
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and not self.popup().selectionModel().hasSelection()):
            self.popup().hide()
            self.entered.emit()
            return True
        return super().eventFilter(watched, event)

    def pathFromIndex(self, index):
        client = index.data()
        _, sep, rest = self.widget().text().partition(" - ")
        return f"{client} - {rest}"


class Desk(QWidget):
    """The dark wood the folders sit on."""

    def paintEvent(self, event):
        p = QPainter(self)
        wood = QLinearGradient(0, 0, 0, self.height())
        wood.setColorAt(0, QColor(theme.DESK_TOP))
        wood.setColorAt(1, QColor(theme.DESK_BOTTOM))
        p.fillRect(self.rect(), wood)


class FolderTabs(QWidget):
    """The folder tabs. The chosen folder comes to the front; the others sit behind, see-through."""

    picked = Signal(str)
    TAB_WIDTH = 164
    STEP = 146
    HEIGHT = 42

    def __init__(self):
        super().__init__()
        self.current = "new"
        self.hover = None
        self.counts = {}
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def set_current(self, view):
        self.current = view
        self.update()

    def set_count(self, view, n):
        self.counts[view] = n
        self.update()

    def tab_at(self, pos):
        # The front tab wins where tabs overlap.
        order = sorted(range(len(VIEWS)), key=lambda i: VIEWS[i] != self.current)
        for i in order:
            if self.shape(i).contains(QPointF(pos)):
                return VIEWS[i]
        return None

    def shape(self, i):
        x, h = i * self.STEP, float(self.HEIGHT)
        w = self.TAB_WIDTH
        path = QPainterPath()
        path.moveTo(x, h)
        path.cubicTo(x + 9, h, x + 9, 3, x + 20, 1)
        path.lineTo(x + w - 20, 1)
        path.cubicTo(x + w - 9, 3, x + w - 9, h, x + w, h)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        behind = [v for v in reversed(VIEWS) if v != self.current]
        for view in behind + [self.current]:
            self.draw_tab(p, view)

    def draw_tab(self, p, view):
        i = VIEWS.index(view)
        folder = theme.FOLDERS[view]
        front = view == self.current
        fill = QLinearGradient(0, 0, 0, self.HEIGHT)
        base = QColor(folder["fill"])
        if front:
            fill.setColorAt(0, base.lighter(112))
            fill.setColorAt(1, base.lighter(106))
        else:
            alpha = 235 if view == self.hover else 175
            fill.setColorAt(0, tinted(base, alpha))
            fill.setColorAt(1, tinted(base.darker(135), alpha))
        path = self.shape(i)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)
        rect = QRectF(i * self.STEP + 26, 0, self.TAB_WIDTH - 52, self.HEIGHT)
        p.setFont(display_font(15, QFont.DemiBold if front else QFont.Medium))
        p.setPen(QColor(folder["on"]))
        p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, TITLES[view])
        n = self.counts.get(view)
        if n is not None:
            p.setFont(display_font(14, QFont.Normal))
            p.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, str(n))

    def mouseMoveEvent(self, event):
        hover = self.tab_at(event.position().toPoint())
        if hover != self.hover:
            self.hover = hover
            self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.update()

    def mousePressEvent(self, event):
        view = self.tab_at(event.position().toPoint())
        if view:
            self.picked.emit(view)


class Folder(QWidget):
    """The open folder: its color wraps around the sheet of paper inside."""

    def __init__(self):
        super().__init__()
        self.view = "new"
        self.paper = None

    def set_view(self, view):
        self.view = view
        self.setStyleSheet(theme.folder_style(view))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = QColor(theme.FOLDERS[self.view]["fill"])
        fill = QLinearGradient(0, 0, 0, self.height())
        fill.setColorAt(0, base.lighter(106))
        fill.setColorAt(1, base.darker(112))
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0, -6, 0, 0), 7, 7)
        p.fillPath(path, fill)
        if self.paper and self.paper.isVisible():
            sheet = QRectF(self.paper.geometry())
            p.fillRect(sheet.adjusted(4, 5, 7, 7), QColor(0, 0, 0, 46))
            p.fillRect(sheet.adjusted(3, 3, 4, 4), QColor(theme.PAPER_BACK))


class Scrim(QWidget):
    """Dims the window behind a dialog."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.hide()

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor(30, 22, 16, 150))


class CardDialog(QDialog):
    """A sheet of paper laid over the window, with a strip of the current folder's color."""

    def __init__(self, win, width):
        super().__init__(win)
        self.win = win
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 30, 30, 30)
        self.card = QFrame(objectName="card")
        self.card.setFixedWidth(width)
        self.card.setGraphicsEffect(QGraphicsDropShadowEffect(self.card, blurRadius=30, offset=QPoint(0, 8),
                                                              color=QColor(0, 0, 0, 120)))
        outer.addWidget(self.card)
        wrap = QVBoxLayout(self.card)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(0)
        self.strip = QFrame()
        self.strip.setFixedHeight(7)
        self.color_strip(win.view)
        wrap.addWidget(self.strip)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(26, 20, 26, 22)
        self.body.setSpacing(10)
        wrap.addLayout(self.body)

    def color_strip(self, view):
        self.strip.setStyleSheet("background: %s; border-top-left-radius: 3px; border-top-right-radius: 3px;"
                                 % theme.FOLDERS[view]["fill"])

    def showEvent(self, event):
        super().showEvent(event)
        self.fit()

    def fit(self):
        self.adjustSize()
        center = self.win.geometry().center()
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def run(self):
        already_dimmed = self.win.scrim.isVisible()    # one dialog opened from another
        self.win.scrim.setGeometry(self.win.rect())
        self.win.scrim.show()
        self.win.scrim.raise_()
        try:
            return self.exec() == QDialog.Accepted
        finally:
            if not already_dimmed:
                self.win.scrim.hide()


class AskDialog(CardDialog):
    """A yes-or-no question. Enter means yes, Esc means no, and the mouse works too."""

    def __init__(self, win, title, body, yes, no, name=""):
        super().__init__(win, 460)
        self.body.addWidget(QLabel(title, objectName="cardTitle"))
        if name:
            label = QLabel(name, objectName="cardName", wordWrap=True)
            label.setTextFormat(Qt.PlainText)
            self.body.addWidget(label)
        if body:
            label = QLabel(body, objectName="cardBody", wordWrap=True)
            label.setTextFormat(Qt.PlainText)
            self.body.addWidget(label)
        self.body.addSpacing(10)
        row = QHBoxLayout()
        row.addStretch()
        self.no_btn = QPushButton(no, objectName="quiet")
        self.no_btn.setAutoDefault(False)
        self.no_btn.clicked.connect(self.reject)
        row.addWidget(self.no_btn)
        self.yes_btn = QPushButton(yes)
        self.yes_btn.setDefault(True)
        self.yes_btn.clicked.connect(self.accept)
        row.addWidget(self.yes_btn)
        self.body.addLayout(row)
        self.yes_btn.setFocus()


class RenameDialog(CardDialog):
    """Change the name from inside the preview. Enter saves, Esc goes back to the document."""

    HINT = "Enter saves. Esc goes back to the document."

    def __init__(self, win, item, stem):
        super().__init__(win, 640)
        self.item = item
        self.body.addWidget(QLabel("Change the name", objectName="cardTitle"))
        self.name = QLineEdit(stem, objectName="nameEdit", placeholderText="LAST, First - Description")
        self.name.textEdited.connect(self.update_hint)
        completer = ClientCompleter(self.name)
        completer.set_clients(win.completer.model().stringList())
        completer.entered.connect(self.save)
        self.name.setCompleter(completer)
        self.body.addWidget(self.name)
        self.hint = QLabel("", objectName="formHint", wordWrap=True)
        self.hint.setTextFormat(Qt.PlainText)
        self.body.addWidget(self.hint)
        self.body.addSpacing(10)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel", objectName="quiet")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self.save)
        row.addWidget(save)
        self.body.addLayout(row)
        self.update_hint()
        self.name.setFocus()

    def setVisible(self, visible):
        super().setVisible(visible)
        # Qt selects the whole box as a dialog opens, so the first key would wipe the name.
        # That's only wanted for a scanner's file name, which is nothing worth keeping.
        if visible and not self.win.is_unnamed(self.item):
            self.name.deselect()

    def stem(self):
        return self.name.text().strip()

    def update_hint(self, *_):
        new_client = engine.is_new_client_change(self.win.ws, self.item, self.stem())
        self.show_hint(f"{new_client} joins the client list when you confirm this file."
                       if new_client else self.HINT)

    def show_hint(self, text, problem=False):
        self.hint.setText(text)
        self.hint.setProperty("problem", problem)
        repolish(self.hint)

    def save(self):
        problem = self.win.name_problem(self.item, self.stem())
        if problem:
            self.show_hint(problem, problem=True)
            return
        self.accept()


class RuleDialog(CardDialog):
    """
    Say what a rule should be. Claude says what it found and lays out a choice with one recommendation.
    Nothing is saved until a person picks an option, and leaving the rules alone is always one of them.
    """

    def __init__(self, win):
        super().__init__(win, 560)
        self.request = ""
        self.seen = ""
        self.proposal = None
        self.choice = None
        self.radios = []
        self.task = None
        self.busy = False
        self.pages = [self.make_ask_page(), self.make_review_page(), self.make_done_page()]
        for page in self.pages:
            self.body.addWidget(page)
        self.go(0)

    def label(self, text, name):
        label = QLabel(text, objectName=name, wordWrap=True)
        label.setTextFormat(Qt.PlainText)
        return label

    def text_box(self, placeholder="", height=92):
        box = QPlainTextEdit(placeholderText=placeholder)
        box.setFixedHeight(height)
        box.setTabChangesFocus(True)
        box.installEventFilter(self)
        return box

    def button_row(self, *buttons):
        row = QHBoxLayout()
        row.addStretch()
        for button in buttons:
            button.setAutoDefault(False)
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button)
        return row

    def make_ask_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Add a Naming Rule", objectName="cardTitle"))
        lay.addWidget(self.label("Describe the new rule, or what you'd like changed, in your own words. Claude "
                                 "will check it against your other rules and give you a choice. Nothing is saved until you pick.",
                                 "cardBody"))
        self.box = self.text_box("For example: include the claim number in the description when there is one")
        lay.addWidget(self.box)
        lay.addSpacing(4)
        lay.addWidget(self.label("Claude model for naming rules", "fieldLabel"))
        self.model = Dropdown()
        for model_id, label in engine.RULE_MODELS.items():
            self.model.addItem(label, model_id)
        chosen = self.win.settings["rule_model_id"]
        if self.model.findData(chosen) < 0:
            self.model.addItem(chosen, chosen)
        self.model.setCurrentIndex(self.model.findData(chosen))
        self.model.setEnabled(not self.win.demo)
        lay.addWidget(self.model)
        self.ask_hint = self.label("", "formHint")
        lay.addWidget(self.ask_hint)
        lay.addSpacing(6)
        self.cancel_btn = QPushButton("Cancel", objectName="quiet")
        self.cancel_btn.clicked.connect(self.reject)
        self.review_btn = QPushButton("Review")
        self.review_btn.clicked.connect(self.review)
        lay.addLayout(self.button_row(self.cancel_btn, self.review_btn))
        lay.addStretch()
        return page

    def make_review_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Choose what to do", objectName="cardTitle"))
        self.summary = self.label("", "cardBody")
        lay.addWidget(self.summary)
        self.conflict_label = self.label("This could clash with", "fieldLabel")
        lay.addWidget(self.conflict_label)
        self.conflict = self.label("", "ruleWarning")
        lay.addWidget(self.conflict)
        lay.addSpacing(4)
        self.options = QWidget()
        self.option_rows = QVBoxLayout(self.options)
        self.option_rows.setContentsMargins(0, 0, 0, 0)
        self.option_rows.setSpacing(3)
        lay.addWidget(self.options)
        lay.addSpacing(4)
        self.old_label = self.label("Current rule", "fieldLabel")
        self.old_rule = self.label("", "path")
        self.new_label = self.label("New wording", "fieldLabel")
        self.rule_box = self.text_box(height=72)
        self.review_hint = self.label("", "formHint")
        for widget in (self.old_label, self.old_rule, self.new_label, self.rule_box, self.review_hint):
            lay.addWidget(widget)
        lay.addSpacing(6)
        back = QPushButton("Back", objectName="quiet")
        back.clicked.connect(lambda: self.go(0))
        self.save_btn = QPushButton("Save Rule")
        self.save_btn.clicked.connect(self.save)
        lay.addLayout(self.button_row(back, self.save_btn))
        lay.addStretch()
        return page

    def make_done_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Rule saved", objectName="cardTitle"))
        lay.addWidget(self.label("It applies the next time you run Auto Process. The earlier rules were kept as a "
                                 "backup in the Rule Backups folder beside them, which holds the three most recent.",
                                 "cardBody"))
        lay.addSpacing(6)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        lay.addLayout(self.button_row(self.close_btn))
        lay.addStretch()
        return page

    def go(self, page):
        self.page = page
        for i, widget in enumerate(self.pages):
            widget.setVisible(i == page)      # only this step takes up room, so the card fits it
        button = (self.review_btn, self.save_btn, self.close_btn)[page]
        button.setDefault(True)
        focus = {0: self.box, 1: self.radios[self.choice] if self.radios else button, 2: button}[page]
        focus.setFocus()
        self.fit()

    def set_busy(self, busy):
        self.busy = busy
        self.review_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(not busy)
        self.box.setReadOnly(busy)
        self.model.setEnabled(not busy and not self.win.demo)
        self.ask_hint.setText("Asking Claude…" if busy else "")

    def reject(self):
        if not self.busy:                     # the request can't be called back once it's sent
            super().reject()

    def review(self):
        request = self.box.toPlainText().strip()
        if self.busy:
            return
        if not engine.clean_rule(request):
            self.ask_hint.setText("Type what you'd like first.")
            return
        self.request = request
        self.seen = engine.read_rules(self.win.ws)
        if self.model.currentData() != self.win.settings["rule_model_id"]:
            self.win.settings["rule_model_id"] = self.model.currentData()
            self.win.save_settings()
        if self.win.demo:
            self.show_proposal(engine.typed_proposal(request, "This is the demo, so no AI is used. Your "
                                                              "wording is kept as you typed it."))
        elif not self.win.api_key:
            self.show_proposal(engine.typed_proposal(request, "There's no Bedrock API key yet, so Claude can't "
                                                              "check this against your other rules."))
        else:
            self.set_busy(True)
            self.task = Task(self.ask_claude, self)
            self.task.done.connect(self.answered)
            self.task.start()

    def ask_claude(self):
        """Runs off the window's thread. Returns the proposal, or a problem in plain English."""
        s = self.win.settings
        try:
            client = engine.make_client(s["aws_region"], self.win.api_key, quick=True,
                                        read_timeout=engine.RULE_READ_TIMEOUT)
            return engine.propose_rule_change(client, s["rule_model_id"], self.request, self.seen)
        except Exception as e:
            return engine.friendly_stop(e) or f"{type(e).__name__}: {e}"[:200]

    def answered(self, result):
        self.set_busy(False)
        if isinstance(result, str):
            result = engine.typed_proposal(self.request, f"Claude couldn't check this against your other rules. "
                                                         f"({result})")
        self.show_proposal(result)

    def show_proposal(self, proposal):
        self.proposal = dict(proposal, options=[dict(option) for option in proposal["options"]])
        self.summary.setText(proposal["summary"])
        self.summary.setVisible(bool(proposal["summary"]))
        self.conflict.setText(proposal["conflict_rule"])
        self.conflict.setVisible(bool(proposal["conflict_rule"]))
        self.conflict_label.setVisible(bool(proposal["conflict_rule"]))
        while self.option_rows.count():
            self.option_rows.takeAt(0).widget().deleteLater()
        self.group = QButtonGroup(self)
        self.radios = []
        recommended = proposal["recommended"]
        for i, option in enumerate(self.proposal["options"]):
            title = option["title"].replace("&", "&&")
            radio = QRadioButton(f"{title}  (recommended)" if i == recommended else title,
                                 objectName="ruleOption")
            radio.setCursor(Qt.PointingHandCursor)
            self.group.addButton(radio, i)
            self.option_rows.addWidget(radio)
            self.radios.append(radio)
            if option["why"]:
                self.option_rows.addWidget(self.label(option["why"], "ruleWhy"))
        self.group.idClicked.connect(self.choose)
        self.choice = None
        self.radios[recommended].setChecked(True)
        self.choose(recommended)
        self.go(1)

    def chosen(self):
        return self.proposal["options"][self.choice]

    def choose(self, i):
        """Show what this option would do. Wording changed on another option is kept if they come back."""
        if self.choice is not None and self.chosen()["action"] in ("add", "edit"):
            self.chosen()["new_rule"] = self.rule_box.toPlainText()
        self.choice = i
        option = self.chosen()
        action = option["action"]
        self.old_label.setText("Rule to remove" if action == "delete" else "Current rule")
        self.old_rule.setText(option["old_rule"])
        for widget in (self.old_label, self.old_rule):
            widget.setVisible(bool(option["old_rule"]))
        self.rule_box.setPlainText(option["new_rule"])
        for widget in (self.new_label, self.rule_box):
            widget.setVisible(action in ("add", "edit"))
        self.review_hint.setText("")
        self.save_btn.setText({"delete": "Remove Rule", "none": "Leave Rules As They Are"}.get(
            action, "Save as Typed" if option["typed"] else "Save Rule"))
        self.fit()

    def save(self):
        option = self.chosen()
        if option["action"] == "none":
            self.accept()
            return
        rule = engine.clean_rule(self.rule_box.toPlainText())
        if option["action"] != "delete" and not rule:
            self.review_hint.setText("The rule can't be empty.")
            return
        try:
            engine.apply_rule_change(self.win.ws, dict(option, new_rule=rule), self.seen)
        except engine.RulesChanged:
            self.ask_hint.setText("The rules changed while this was open. Click Review to check it again.")
            self.go(0)
        except OSError as e:
            self.review_hint.setText(f"The rules couldn't be saved. They may be open somewhere else. "
                                     f"({type(e).__name__})")
        else:
            self.go(2)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if watched is self.box:
                self.review()
                return True
            if watched is self.rule_box:
                self.save()
                return True
        return super().eventFilter(watched, event)


class Task(QThread):
    """Runs one function off the window's thread."""

    done = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        self.done.emit(self.fn())


class BatchWorker(QThread):
    progress = Signal(int, int, str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, win):
        super().__init__(win)
        self.ws = win.ws
        self.settings = dict(win.settings)
        self.demo = win.demo
        self.key = win.api_key
        self.stop = False

    def run(self):
        try:
            if self.demo:
                bedrock = engine.FakeClaude(HERE / "test" / "fake_answers.csv")
            else:
                bedrock = engine.make_client(self.settings["aws_region"], self.key)
            summary = engine.run_batch(self.ws, bedrock, self.settings["model_id"],
                                       settle_seconds=0 if self.demo else engine.SETTLE_SECONDS,
                                       on_progress=self.progress.emit, should_stop=lambda: self.stop)
            self.finished_ok.emit(summary)
        except engine.StopRun as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Something went wrong: {type(e).__name__}: {e}"[:300])


class Preview(QWidget):
    """
    Press Space on a file. Up and Down change documents, Left and Right change pages, Enter accepts
    the name, F2 changes it, and Space or Esc closes.
    """

    def __init__(self, win):
        super().__init__(win.centralWidget())
        self.win = win
        self.page = 0
        self.total = 1
        self.setFocusPolicy(Qt.StrongFocus)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 24, 40, 16)
        lay.setSpacing(10)
        self.image = QLabel(alignment=Qt.AlignCenter)
        self.image.setGraphicsEffect(QGraphicsDropShadowEffect(self.image, blurRadius=34, offset=QPoint(0, 10),
                                                               color=QColor(0, 0, 0, 190)))
        lay.addWidget(self.image, 1)
        self.caption = QLabel(alignment=Qt.AlignCenter)
        self.caption.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 600;")
        self.caption.setTextFormat(Qt.PlainText)
        lay.addWidget(self.caption)
        self.keys = QLabel(alignment=Qt.AlignCenter)
        self.keys.setStyleSheet(f"color: {theme.CREAM}; font-size: 12px;")
        lay.addWidget(self.keys)
        self.hide()

    def open(self):
        self.setGeometry(self.parentWidget().rect())
        self.page = 0
        self.show()
        self.raise_()
        self.setFocus()
        self.draw()

    def close_preview(self):
        self.hide()
        self.win.list.setFocus()

    def draw(self):
        item = self.win.current()
        if not item:
            self.close_preview()
            return
        self.draw_keys(item)
        ratio = self.devicePixelRatioF()
        long_edge = int(max(self.height() - 110, 300) * ratio)
        try:
            pil, self.total = engine.render_preview(item.path, self.page, long_edge)
        except Exception as e:
            self.image.clear()
            self.image.setText("This file can't be previewed.")
            self.image.setStyleSheet("color: #FFFFFF;")
            self.caption.setText(f"{item.stem}  ({type(e).__name__})")
            self.total = 1
            return
        image = QImage(pil.tobytes(), pil.width, pil.height, pil.width * 3, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(ratio)
        self.image.setPixmap(pixmap)
        self.caption.setText(f"{item.stem}   (page {self.page + 1} of {self.total})")

    def draw_keys(self, item):
        keys = ["Up and Down arrows: change documents", "Left and Right arrows: change pages"]
        if self.can_name():
            if not self.win.is_unnamed(item):
                keys.append("Enter: name is right")
            keys.append(f"{engine.RENAME_KEY}: change name")
        keys.append("Space: close")
        self.keys.setText("   ·   ".join(keys))

    def can_name(self):
        item = self.win.current()
        return item is not None and item.bucket in engine.BUCKETS[:3]

    def after_confirm(self, moved):
        if moved and self.win.current():
            self.page = 0
            self.setFocus()
            self.draw()
        else:
            self.close_preview()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Space, Qt.Key_Escape):
            self.close_preview()
        elif key in (Qt.Key_Right, Qt.Key_PageDown) and self.page < self.total - 1:
            self.page += 1
            self.draw()
        elif key in (Qt.Key_Left, Qt.Key_PageUp) and self.page > 0:
            self.page -= 1
            self.draw()
        elif key in (Qt.Key_Down, Qt.Key_Up):
            step = 1 if key == Qt.Key_Down else -1
            row = self.win.list.currentRow() + step
            if 0 <= row < self.win.list.count():
                self.win.list.setCurrentRow(row)
                self.page = 0
                self.draw()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self.after_confirm(self.win.confirm_current())
        elif key == Qt.Key_F2 and self.can_name():
            if self.win.rename_current():
                self.after_confirm(True)
            else:
                self.setFocus()

    def mousePressEvent(self, event):
        self.close_preview()

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor(30, 23, 18, 236))


class Toast(QFrame):
    """A short message near the bottom of the window, with an optional Undo."""

    def __init__(self, parent):
        super().__init__(parent, objectName="toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 9, 10, 9)
        lay.setSpacing(14)
        self.label = QLabel()
        lay.addWidget(self.label)
        self.undo = QPushButton("Undo")
        self.undo.setFocusPolicy(Qt.NoFocus)
        self.undo.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.undo)
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)
        self.hide()

    def say(self, text, can_undo=False, ms=6000):
        self.label.setText(text)
        self.undo.setVisible(can_undo)
        self.adjustSize()
        self.place()
        self.show()
        self.raise_()
        self.timer.start(ms)

    def place(self):
        area = self.parentWidget().rect()
        self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 104)


class CheckBox(QCheckBox):
    """A plain square box with a real check mark."""

    def __init__(self, text, checked):
        super().__init__(text, checked=checked)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(QFontMetrics(self.font()).horizontalAdvance(self.text()) + 34, 28)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1, (self.height() - 18) / 2, 18, 18)
        p.setPen(QPen(QColor(theme.INK), 1.2))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(box, 2, 2)
        if self.isChecked():
            p.setPen(QPen(QColor(theme.INK), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            x, y = box.left(), box.top()
            p.drawPolyline([QPointF(x + 4, y + 9.5), QPointF(x + 7.5, y + 13), QPointF(x + 14, y + 5)])
        p.setPen(QColor(theme.INK))
        p.drawText(self.rect().adjusted(30, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Dropdown(QComboBox):
    """A combo box with a small drawn arrow."""

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.MUTED), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x, y = self.width() - 17, self.height() / 2
        p.drawPolyline([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])


class SettingsDialog(CardDialog):
    def __init__(self, win):
        super().__init__(win, 520)
        s = win.settings
        self.body.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(QLabel("Settings", objectName="cardTitle"))
        row.addStretch()
        self.version = QLabel(f"Version {engine.VERSION}", objectName="usage")
        row.addWidget(self.version, 0, Qt.AlignBottom)
        self.body.addLayout(row)
        self.body.addSpacing(8)

        self.field("Scans folder")
        row = QHBoxLayout()
        self.folder = QLabel(s["scan_folder"] or "Not chosen yet", objectName="path", wordWrap=True)
        self.folder.setTextFormat(Qt.PlainText)
        row.addWidget(self.folder, 1)
        change = QPushButton("Choose…", objectName="quiet")
        change.setAutoDefault(False)
        change.setEnabled(not win.demo)
        change.clicked.connect(self.choose_folder)
        row.addWidget(change)
        self.body.addLayout(row)
        self.body.addSpacing(10)

        self.field("Settings folder")
        row = QHBoxLayout()
        self.settings_folder = QLabel(win.settings_folder_text(), objectName="path", wordWrap=True)
        self.settings_folder.setTextFormat(Qt.PlainText)
        row.addWidget(self.settings_folder, 1)
        change = QPushButton("Choose…", objectName="quiet")
        change.setAutoDefault(False)
        change.setEnabled(not win.demo)
        change.clicked.connect(self.choose_settings_folder)
        row.addWidget(change)
        self.body.addLayout(row)
        self.settings_hint = QLabel("Choose a shared folder so the whole office uses the same client list and "
                                    "naming rules.", objectName="formHint", wordWrap=True)
        self.settings_hint.setTextFormat(Qt.PlainText)
        self.body.addWidget(self.settings_hint)
        self.body.addSpacing(10)

        self.field("Bedrock API key")
        row = QHBoxLayout()
        self.key = QLineEdit(win.api_key, echoMode=QLineEdit.Password, placeholderText="Paste the key here")
        self.key.setEnabled(not win.demo)
        row.addWidget(self.key, 1)
        self.test_btn = QPushButton("Test", objectName="quiet")
        self.test_btn.setAutoDefault(False)
        self.test_btn.setEnabled(not win.demo)
        self.test_btn.clicked.connect(self.test)
        row.addWidget(self.test_btn)
        self.body.addLayout(row)
        self.result = QLabel("", objectName="formHint", wordWrap=True)
        self.result.setTextFormat(Qt.PlainText)
        self.body.addWidget(self.result)
        self.body.addSpacing(4)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.addWidget(self.make_label("Claude model"), 0, 0)
        grid.addWidget(self.make_label("AWS region"), 0, 1)
        self.model = Dropdown()
        for model_id, label in engine.MODELS.items():
            self.model.addItem(label, model_id)
        if self.model.findData(s["model_id"]) < 0:
            self.model.addItem(s["model_id"], s["model_id"])
        self.model.setCurrentIndex(self.model.findData(s["model_id"]))
        grid.addWidget(self.model, 1, 0)
        self.region = QLineEdit(s["aws_region"])
        grid.addWidget(self.region, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        self.body.addLayout(grid)
        self.body.addSpacing(12)

        self.confirm_twice = CheckBox("Ask “Is this name correct?” before moving a file to Ready to File",
                                      s["confirm_twice"])
        self.body.addWidget(self.confirm_twice)
        self.guidance = CheckBox("Show instructions on each screen", s["show_guidance"])
        self.body.addWidget(self.guidance)
        self.body.addSpacing(6)
        self.add_rule_btn = QPushButton("Add a Naming Rule", objectName="quiet")
        self.add_rule_btn.setAutoDefault(False)
        self.add_rule_btn.setCursor(Qt.PointingHandCursor)
        self.add_rule_btn.setEnabled(win.ws is not None)
        self.add_rule_btn.clicked.connect(self.add_rule)
        self.needs_folder = [self.add_rule_btn]
        self.body.addWidget(self.add_rule_btn, 0, Qt.AlignLeft)
        self.body.addSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(2)
        for text, fn in (("Client list", lambda: win.open_settings_file("client_list")),
                         ("Naming rules", lambda: win.open_settings_file("rules_file")),
                         ("Activity log", lambda: win.open_settings_file("log_file"))):
            b = QPushButton(text, objectName="link")
            b.setAutoDefault(False)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            b.setEnabled(win.ws is not None)
            self.needs_folder.append(b)
            row.addWidget(b)
        row.addStretch()
        if win.demo:
            reset = QPushButton("Reset demo", objectName="quiet")
            reset.setAutoDefault(False)
            reset.clicked.connect(self.reset_demo)
            row.addWidget(reset)
        done = QPushButton("Done")
        done.setDefault(True)
        done.clicked.connect(self.save)
        row.addWidget(done)
        self.body.addLayout(row)

        self.body.addSpacing(6)
        self.usage = QLabel(objectName="usage")
        self.usage.setTextFormat(Qt.PlainText)
        self.usage.setToolTip("Estimated from Claude's published prices. Your Bedrock bill may differ.")
        self.body.addWidget(self.usage)
        self.update_usage()

    def update_usage(self):
        ws = self.win.ws
        if ws:
            usage = engine.usage_totals(ws, self.win.settings["model_id"])
            self.usage.setText(usage_line("Last 7 days", usage["week"]) + "\n"
                               + usage_line("Lifetime", usage["lifetime"]))
        self.usage.setVisible(ws is not None)

    def add_rule(self):
        # The demo uses no AI, so there are no tokens to warn about.
        if self.win.demo or self.win.ask("Before you add a rule", RULE_CAUTION, "Continue", "Cancel"):
            RuleDialog(self.win).run()

    def make_label(self, text):
        return QLabel(text, objectName="fieldLabel")

    def field(self, text):
        self.body.addWidget(self.make_label(text))

    def choose_folder(self):
        start = self.win.settings["scan_folder"] or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose the scans folder", start)
        if chosen and self.win.use_folder(chosen):
            self.folders_changed()

    def choose_settings_folder(self):
        start = self.win.settings["settings_folder"] or self.win.settings["scan_folder"] or str(Path.home())
        while True:
            chosen = QFileDialog.getExistingDirectory(self, "Choose the settings folder", start)
            if not chosen:
                return
            note = self.win.use_settings_folder(chosen)
            if note:
                self.settings_hint.setText(note)
                self.folders_changed()
                return
            start = chosen                    # they asked to choose a different folder

    def folders_changed(self):
        self.folder.setText(self.win.settings["scan_folder"] or "Not chosen yet")
        self.settings_folder.setText(self.win.settings_folder_text())
        for button in self.needs_folder:
            button.setEnabled(self.win.ws is not None)
        self.update_usage()
        self.fit()

    def test(self):
        self.test_btn.setEnabled(False)
        self.result.setProperty("problem", False)
        self.result.setText("Testing…")
        region, model, key = self.region.text().strip(), self.model.currentData(), self.key.text().strip()
        self.task = Task(lambda: engine.test_connection(region, model, key), self)
        self.task.done.connect(self.tested)
        self.task.start()

    def tested(self, problem):
        self.test_btn.setEnabled(True)
        self.result.setProperty("problem", bool(problem))
        self.result.setText(problem or "Connected. Claude answered.")
        repolish(self.result)
        self.adjustSize()

    def reset_demo(self):
        self.win.reset_demo()
        self.accept()

    def save(self):
        s = self.win.settings
        s.update(aws_region=self.region.text().strip() or engine.DEFAULT_SETTINGS["aws_region"],
                 model_id=self.model.currentData(),
                 confirm_twice=self.confirm_twice.isChecked(),
                 show_guidance=self.guidance.isChecked())
        if not self.win.demo:
            key = self.key.text().strip()
            if key != self.win.api_key:
                try:
                    engine.save_api_key(key)
                    self.win.api_key = key
                except Exception as e:
                    self.result.setProperty("problem", True)
                    self.result.setText(f"The key couldn't be saved: {e}")
                    repolish(self.result)
                    return
        self.win.save_settings()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.settings = dict(engine.DEFAULT_SETTINGS) if demo else engine.load_settings()
        self.api_key = "" if demo else engine.load_api_key()
        self.ws = None
        self.worker = None
        self.last_undo = None
        self.undo_view = "named"
        self.checked = False                    # has Check Scandocs Folder been clicked?
        self.view = "new"
        self.items = {v: [] for v in VIEWS}
        self.shown = None                       # the file names now in the list

        self.setWindowTitle("Speedy Scandocs" + (" (Demo)" if demo else ""))
        self.setWindowIcon(app_icon())
        self.resize(1120, 760)
        self.setMinimumSize(900, 600)
        self.build()
        self.scrim = Scrim(self)
        self.toast = Toast(self.centralWidget())
        self.toast.undo.clicked.connect(self.undo)
        self.preview = Preview(self)
        QShortcut(QKeySequence.Undo, self, activated=self.undo)
        if demo:
            self.settings["scan_folder"] = str(demo_root())
            self.setup_demo()
        self.load_workspace()

    # ------------------------------------------------------------ layout

    def build(self):
        root = Desk()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 12, 22, 20)
        outer.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(4, 0, 2, 10)
        top.setSpacing(16)
        top.addWidget(QLabel("Speedy Scandocs", objectName="brand"))
        self.version = QLabel(f"v{engine.VERSION}", objectName="brandVersion")
        top.addWidget(self.version)
        top.addStretch()
        if self.demo:
            top.addWidget(QLabel("Demo. No AI is used.", objectName="demoChip"))
        for text, action in (("Guide", self.open_guide), ("Settings", self.open_settings)):
            button = QPushButton(text, objectName="deskLink")
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(action)
            top.addWidget(button)
        outer.addLayout(top)

        self.tabs = FolderTabs()
        self.tabs.picked.connect(self.show_view)
        outer.addWidget(self.tabs)

        self.folder = Folder()
        outer.addWidget(self.folder, 1)
        col = QVBoxLayout(self.folder)
        col.setContentsMargins(20, 16, 24, 14)
        col.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.title = QLabel(objectName="title")
        self.title.setMinimumHeight(44)
        row.addWidget(self.title)
        row.addStretch()
        self.check_btn = QPushButton("Check Scandocs Folder", objectName="quiet")
        self.check_btn.clicked.connect(self.check_folder)
        self.process_btn = QPushButton("Auto Process")
        self.process_btn.clicked.connect(self.auto_process)
        self.open_btn = QPushButton("Open Ready to File Folder")
        self.open_btn.clicked.connect(self.open_folder)
        for b in (self.check_btn, self.process_btn, self.open_btn):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        col.addLayout(row)
        self.guide = QLabel(objectName="guide", wordWrap=True)
        col.addWidget(self.guide)

        self.progress_box = QWidget()
        lay = QVBoxLayout(self.progress_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        self.status = QLabel(objectName="status")
        self.status.setTextFormat(Qt.PlainText)
        row.addWidget(self.status, 1)
        self.stop_btn = QPushButton("Stop", objectName="stop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_batch)
        row.addWidget(self.stop_btn)
        lay.addLayout(row)
        self.bar = QProgressBar(textVisible=False)
        lay.addWidget(self.bar)
        self.progress_box.hide()
        col.addWidget(self.progress_box)

        paper = QFrame(objectName="paper")
        self.folder.paper = paper
        self.stack = QStackedLayout(paper)
        self.stack.setContentsMargins(0, 0, 0, 0)

        self.list = QListWidget()
        self.list.setItemDelegate(Row(self.list))
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMouseTracking(True)
        self.list.currentRowChanged.connect(self.selected)
        self.list.doubleClicked.connect(lambda: self.preview.open())
        self.list.installEventFilter(self)
        self.stack.addWidget(self.list)

        self.empty = QLabel(objectName="empty", alignment=Qt.AlignCenter, wordWrap=True)
        self.stack.addWidget(self.empty)

        welcome = QWidget()
        lay = QVBoxLayout(welcome)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Set up Speedy Scandocs", objectName="welcomeTitle", alignment=Qt.AlignCenter))
        self.welcome_text = QLabel("", objectName="welcomeBody", alignment=Qt.AlignCenter, wordWrap=True)
        self.welcome_text.setMaximumWidth(420)
        lay.addWidget(self.welcome_text, 0, Qt.AlignCenter)
        lay.addSpacing(8)
        start = QPushButton("Open Settings")
        start.setCursor(Qt.PointingHandCursor)
        start.clicked.connect(self.open_settings)
        lay.addWidget(start, 0, Qt.AlignCenter)
        self.stack.addWidget(welcome)
        col.addWidget(paper, 1)
        col.addSpacing(4)

        self.action_bar = QWidget()
        lay = QVBoxLayout(self.action_bar)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(5)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.name_edit = QLineEdit(objectName="nameEdit", placeholderText="File name")
        self.name_edit.textEdited.connect(self.name_changed)
        self.name_edit.installEventFilter(self)
        self.completer = ClientCompleter(self.name_edit)
        self.completer.entered.connect(self.confirm_current)
        self.name_edit.setCompleter(self.completer)
        row.addWidget(self.name_edit, 1)
        self.retry_btn = QPushButton("Try Again", objectName="quiet")
        self.retry_btn.clicked.connect(self.retry_current)
        row.addWidget(self.retry_btn)
        self.confirm_btn = QPushButton("Correct")
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setMinimumWidth(96)
        self.confirm_btn.clicked.connect(self.confirm_current)
        row.addWidget(self.confirm_btn)
        lay.addLayout(row)
        self.hint = QLabel(objectName="hint")
        self.hint.setTextFormat(Qt.PlainText)
        lay.addWidget(self.hint)
        col.addWidget(self.action_bar)

    # ------------------------------------------------------------ data

    def load_workspace(self):
        folder, shared = self.settings["scan_folder"], self.settings["settings_folder"]
        # Never carry on without a shared folder's files: a blank list could sync over the office's real one.
        usable = folder and Path(folder).is_dir() and not (shared and engine.missing_settings_files(shared))
        self.ws = engine.Workspace(folder, shared) if usable else None
        if self.ws and not self.ws.is_ready():
            self.ws.create()
        self.checked = False
        self.items["new"] = []
        self.shown = None
        self.refresh()
        self.show_view("new")

    def refresh(self):
        """Read the buckets from disk and update the counts."""
        if self.ws:
            rows = self.ws.latest_rows()
            for bucket in engine.BUCKETS:
                self.items[bucket] = engine.list_bucket(self.ws, bucket, rows)
            if self.checked:
                self.items["new"] = engine.list_new(self.ws)
            self.completer.set_clients(engine.load_clients(self.ws.client_list))
        self.tabs.set_count("new", len(self.items["new"]) if self.checked else None)
        for bucket in engine.BUCKETS:
            self.tabs.set_count(bucket, len(self.items[bucket]))
        self.draw_list()

    def current(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def draw_list(self, select_name=None):
        items = self.items[self.view]
        names = [i.name for i in items]
        if names != self.shown or select_name:
            keep = select_name or (self.current().name if self.current() else None)
            old_row = max(self.list.currentRow(), 0)
            self.list.blockSignals(True)
            self.list.clear()
            for it in items:
                row = QListWidgetItem()
                row.setData(Qt.UserRole, it)
                self.list.addItem(row)
            self.shown = names
            row = names.index(keep) if keep in names else min(old_row, len(names) - 1)
            if row >= 0:
                self.list.setCurrentRow(row)
            self.list.blockSignals(False)
            self.selected()
        else:
            # Same files: pick up any new reasons without disturbing what's being typed.
            for i, it in enumerate(items):
                self.list.item(i).setData(Qt.UserRole, it)
        self.update_chrome()

    def update_chrome(self):
        view, ready = self.view, self.ws is not None
        busy = self.worker is not None
        items = self.items[view]
        self.title.setText(TITLES[view])
        self.tabs.set_current(view)
        self.folder.set_view(view)
        self.guide.setText(GUIDE[view])
        self.guide.setVisible(self.settings["show_guidance"] and ready)
        self.check_btn.setVisible(view == "new" and ready)
        self.process_btn.setVisible(view == "new" and ready)
        self.check_btn.setEnabled(not busy)
        self.process_btn.setEnabled(not busy and self.checked and bool(items))
        self.open_btn.setVisible(view == "completed" and ready)
        self.retry_btn.setVisible(view == "failed")
        self.action_bar.setVisible(view in ("named", "review", "failed") and bool(items))
        if not ready:
            scans = self.settings["scan_folder"]
            if scans and Path(scans).is_dir():
                self.welcome_text.setText("The settings folder can't be reached, or its client list or naming "
                                          "rules are missing. It may be offline. Choose it again in Settings.")
            elif scans:
                self.welcome_text.setText("The scans folder can't be found. It may be offline, or it may have "
                                          "moved. Choose it again in Settings.")
            else:
                self.welcome_text.setText("Choose the folder your scanner saves to, then paste your Bedrock "
                                          "API key.")
            self.stack.setCurrentIndex(2)
        elif items:
            self.stack.setCurrentIndex(0)
        else:
            unchecked = view == "new" and not self.checked
            self.empty.setText("Click Check Scandocs Folder to begin." if unchecked else EMPTY[view])
            self.stack.setCurrentIndex(1)

    def show_view(self, view):
        self.view = view
        self.shown = None
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self.draw_list()
        if self.current():
            self.list.setCurrentRow(0)
        self.list.setFocus()

    def selected(self, *_):
        item = self.current()
        if not item or item.bucket not in engine.BUCKETS[:3]:
            return
        self.name_edit.setText(item.stem)
        self.set_problem(False)
        self.update_action()

    def is_unnamed(self, item):
        return item.row.get("result") in ("no name", "error") or (item.bucket == "failed" and not item.row)

    def update_action(self):
        item = self.current()
        if not item or item.bucket not in engine.BUCKETS[:3]:
            return
        changed = self.name_edit.text().strip() != item.stem
        self.confirm_btn.setText("Save" if changed else "Correct")
        self.confirm_btn.setEnabled(changed or not self.is_unnamed(item))
        new_client = engine.is_new_client_change(self.ws, item, self.name_edit.text())
        if new_client:
            self.set_hint(f"{new_client} joins the client list when you confirm this file.")
        elif self.is_unnamed(item):
            self.set_hint("Type it as LAST, First - Description.")
        elif self.settings["show_guidance"]:
            self.set_hint(f"Space to read the file. Enter if the name is right. {engine.RENAME_KEY} to change it.")
        else:
            self.set_hint("")

    def set_hint(self, text):
        self.hint.setText(text)
        self.set_style_flag(self.hint, False)

    def set_problem(self, problem):
        self.set_style_flag(self.name_edit, bool(problem))

    def set_style_flag(self, widget, value):
        widget.setProperty("problem", value)
        repolish(widget)

    def name_changed(self, *_):
        self.set_problem(False)
        self.update_action()

    def show_name_problem(self, text):
        self.hint.setText(text)
        self.set_style_flag(self.hint, True)
        self.set_problem(True)
        self.name_edit.setFocus()

    # ------------------------------------------------------------ keyboard

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if watched is self.list:
                if key == Qt.Key_Space and self.current():
                    self.preview.open()
                    return True
                if key in (Qt.Key_Return, Qt.Key_Enter):
                    self.confirm_current()
                    return True
                if key == Qt.Key_F2 and self.action_bar.isVisible():
                    self.name_edit.setFocus()
                    self.name_edit.selectAll()
                    return True
            elif watched is self.name_edit:
                popup_open = self.completer.popup().isVisible()
                if key in (Qt.Key_Return, Qt.Key_Enter) and not popup_open:
                    self.confirm_current()
                    return True
                if key == Qt.Key_Escape and not popup_open:
                    self.selected()
                    self.list.setFocus()
                    return True
                if key in (Qt.Key_Up, Qt.Key_Down) and not popup_open:
                    row = self.list.currentRow() + (1 if key == Qt.Key_Down else -1)
                    if 0 <= row < self.list.count():
                        self.list.setCurrentRow(row)
                    return True
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------ actions

    def ask(self, title, body, yes, no, name=""):
        return AskDialog(self, title, body, yes, no, name).run()

    def check_folder(self):
        self.checked = True
        self.refresh()
        count = len(self.items["new"])
        if count:
            self.list.setCurrentRow(0)
            self.list.setFocus()
        self.toast.say(f"{count} new {'scan' if count == 1 else 'scans'} found" if count else "No new scans found",
                       ms=3000)

    def auto_process(self):
        if not self.demo and not self.api_key:
            self.toast.say("Add your Bedrock API key in Settings first.", ms=5000)
            self.open_settings()
            return
        if self.worker:
            return
        self.worker = BatchWorker(self)
        self.worker.progress.connect(self.batch_progress)
        self.worker.finished_ok.connect(self.batch_done)
        self.worker.failed.connect(self.batch_failed)
        self.bar.setRange(0, 0)
        self.status.setText("Starting…")
        self.progress_box.show()
        self.update_chrome()
        self.worker.start()

    def batch_progress(self, done, total, name):
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.status.setText(f"Reading {done + 1} of {total}:  {name}")
        self.refresh()

    def stop_batch(self):
        if self.worker:
            self.worker.stop = True
            self.status.setText("Stopping after this file…")

    def end_batch(self):
        self.worker.wait()
        self.worker = None
        self.progress_box.hide()
        self.refresh()

    def batch_done(self, s):
        self.end_batch()
        handled = s["named"] + s["review"] + s["failed"]
        if s["total"] == 0 and s["busy"]:
            self.toast.say("The scanner may still be saving these. Try again in a few seconds.")
            return
        message = f"{handled} done: {s['named']} Named, {s['review']} Review, {s['failed']} Failed"
        if s["busy"]:
            message += f". {s['busy']} still saving, left in Home."
        self.toast.say(message, ms=8000)
        for view in ("named", "review", "failed"):
            if self.items[view]:
                self.show_view(view)
                break

    def batch_failed(self, message):
        self.end_batch()
        self.ask("Auto Process stopped", message + "\n\nFiles not yet processed are still in Home.", "OK", "Close")

    def name_problem(self, item, stem):
        if stem == item.stem and self.is_unnamed(item):
            return "Type the correct name first."
        return engine.name_problem(stem)

    def name_is_right(self, item, stem):
        """The second look, unless it's turned off in Settings."""
        if not self.settings["confirm_twice"]:
            return True
        new_client = engine.is_new_client_change(self.ws, item, stem)
        body = f"{new_client} will be added to the client list." if new_client else ""
        return self.ask("Is this name correct?", body, "Yes, correct", "Go back", name=stem)

    def rename_current(self):
        """F2 in the preview. Go back returns to the popup with the typing kept. True if the file moved."""
        item = self.current()
        stem = self.name_edit.text().strip()
        while True:
            dialog = RenameDialog(self, item, stem)
            if not dialog.run():
                return False
            stem = dialog.stem()
            if self.name_is_right(item, stem):
                self.name_edit.setText(stem)
                return self.confirm_current(asked=True)

    def confirm_current(self, *, asked=False):
        """Enter or the Correct button. Returns True if the file moved to Ready to File."""
        item = self.current()
        if not item or item.bucket not in engine.BUCKETS[:3]:
            return False
        stem = self.name_edit.text().strip()
        problem = self.name_problem(item, stem)
        if problem:
            self.show_name_problem(problem)
            return False
        if not asked and not self.name_is_right(item, stem):
            if self.preview.isHidden():
                self.list.setFocus()
            return False
        new_client = engine.is_new_client_change(self.ws, item, stem)
        try:
            self.last_undo = engine.confirm_file(self.ws, item, stem)
        except OSError as e:
            self.toast.say(f"That file couldn't be moved. It may be open somewhere else. ({type(e).__name__})")
            self.refresh()
            return False
        self.undo_view = item.bucket
        self.refresh()
        self.list.setFocus()
        added = f" {new_client} added to the client list." if self.last_undo.added else ""
        self.toast.say(f"Moved to Ready to File.{added}", can_undo=True)
        return True

    def undo(self):
        if not self.last_undo or self.scrim.isVisible():
            return
        undo, self.last_undo = self.last_undo, None
        try:
            engine.undo_decision(self.ws, undo)
        except OSError:
            self.toast.say("That file couldn't be put back. It may have been moved already.")
            self.refresh()
            return
        self.toast.hide()
        self.view = self.undo_view
        self.shown = None
        self.refresh()
        self.draw_list(select_name=undo.source.name)

    def retry_current(self):
        item = self.current()
        if not item:
            return
        engine.retry_file(self.ws, item)
        self.checked = True
        self.refresh()
        self.toast.say("Sent back to Home.", ms=3000)
        self.list.setFocus()

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ws.folder("completed"))))

    def open_settings_file(self, attr):
        path = getattr(self.ws, attr)
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.toast.say("Nothing has been written there yet.", ms=3000)

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.run()
        self.update_chrome()
        self.selected()

    def open_guide(self):
        if self.worker:
            self.toast.say("The guide can open when Auto Process is done.", ms=4000)
            return
        tour.Tour(self, self.tour_sheets(), TITLES).start()

    def tour_sheets(self):
        """The dialogs the tour lays open on the window, each made when the tour reaches it."""
        def rule_box(review=False):
            dialog = RuleDialog(self)
            dialog.box.setPlainText(tour.SAMPLE_REQUEST)
            if review:
                dialog.show_proposal(tour.SAMPLE_RULE_PROPOSAL)
            return dialog

        return dict(settings=lambda: SettingsDialog(self),
                    ask=lambda: AskDialog(self, "Is this name correct?", "", "Yes, correct", "Go back",
                                          name=self.current().stem),
                    rename=lambda: RenameDialog(self, self.current(), self.current().stem),
                    rule=rule_box,
                    rule_review=lambda: rule_box(review=True))

    def first_run_guide(self):
        if not self.settings["guide_seen"]:
            self.open_guide()
            self.settings["guide_seen"] = True
            self.save_settings()

    def save_settings(self):
        if not self.demo:
            engine.save_settings(self.settings)

    def settings_folder_text(self):
        shared, scans = self.settings["settings_folder"], self.settings["scan_folder"]
        return shared or (str(Path(scans) / engine.FOLDER_NAMES["settings"]) if scans else "Inside the scans folder")

    def use_settings_folder(self, chosen):
        """
        A settings folder was picked. Use it if the files are there, or ask. Returns a note saying what
        happened, or "" if another folder should be chosen.
        """
        path = Path(chosen)
        missing = engine.missing_settings_files(path)
        inside = path / engine.FOLDER_NAMES["settings"]
        if missing and not engine.missing_settings_files(inside):
            path, missing = inside, []        # they picked the folder around it
        if self.ws and path == self.ws.settings_dir:
            return "This is already the settings folder."
        note = "Found the client list and naming rules here."
        if missing:
            words = " or ".join(missing)
            copied = ("Your current client list, rules and learned names will be copied there."
                      if self.ws else "New starter files will be made.")
            if not self.ask("These files aren't here yet",
                            f"This folder doesn't have {words} yet. You can choose a different folder that "
                            f"already has them, or create them here. {copied}",
                            "Create Them Here", "Choose Another Folder", name=str(path)):
                return ""
            try:
                engine.set_up_settings_folder(path, self.ws)
            except OSError as e:
                self.ask("That folder can't be used", f"The files couldn't be created there. ({type(e).__name__})",
                         "Choose Another Folder", "Close", name=str(path))
                return ""
            note = "The client list and naming rules are set up here."
        self.settings["settings_folder"] = str(path)
        self.save_settings()
        self.load_workspace()
        return note

    def use_folder(self, chosen):
        """A new scans folder was picked: confirm, then create its subfolders."""
        root = Path(chosen)
        if str(root) == self.settings["scan_folder"]:
            return False
        ws = engine.Workspace(root, self.settings["settings_folder"])
        missing = ws.missing_folders()
        body = (f"These folders will be created inside it: {', '.join(missing)}. Nothing already there is changed."
                if missing else "This folder is already set up.")
        if not self.ask("Use this folder?", body, "Yes, use it", "Cancel", name=str(root)):
            return False
        ws.create()
        self.settings["scan_folder"] = str(root)
        self.save_settings()
        self.load_workspace()
        return True

    # ------------------------------------------------------------ demo

    def setup_demo(self, reset=False):
        root = demo_root()
        if reset and root.exists():
            shutil.rmtree(root)
        if root.exists():
            return
        ws = engine.Workspace(root)
        ws.create()
        for pdf in sorted((HERE.parent / "files-test").glob("*.pdf")):
            shutil.copy2(pdf, root / pdf.name)
        shutil.copy2(HERE / "test" / "client_list_test_original.txt", ws.client_list)

    def reset_demo(self):
        self.last_undo = None
        self.setup_demo(reset=True)
        self.load_workspace()

    # ------------------------------------------------------------ window events

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview"):
            self.scrim.setGeometry(self.rect())
            self.toast.place()
            if self.preview.isVisible():
                self.preview.setGeometry(self.centralWidget().rect())
                self.preview.draw()

    def changeEvent(self, event):
        super().changeEvent(event)
        # Back from File Explorer or Finder: files may have moved.
        if (event.type() == QEvent.ActivationChange and self.isActiveWindow() and hasattr(self, "preview")
                and not self.worker and not self.preview.isVisible()):
            self.refresh()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop = True
            self.worker.wait()
        super().closeEvent(event)


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def demo_root():
    return HERE / "test" / "app_demo"


def folder_pixmap(size):
    """A yellow file folder. packaging/make_icons.py saves this as the release icons."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    u = size / 16
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#B98F3E"))
    p.drawRoundedRect(QRectF(1 * u, 2.5 * u, 6.5 * u, 4 * u), u, u)
    p.drawRoundedRect(QRectF(1 * u, 4 * u, 14 * u, 10 * u), u, u)
    p.setBrush(QColor(theme.FOLDERS["review"]["fill"]))
    p.drawRoundedRect(QRectF(1 * u, 5.5 * u, 14 * u, 8.5 * u), u, u)
    p.end()
    return pixmap


def app_icon():
    icon = QIcon()
    for size in (16, 32, 64, 256):
        icon.addPixmap(folder_pixmap(size))
    return icon


def report_crash(kind, value, tb):
    text = "".join(traceback.format_exception(kind, value, tb))
    try:
        (engine.app_data_dir() / "crash.log").write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text, file=sys.stderr)
    if QApplication.instance():
        QMessageBox.critical(None, "Speedy Scandocs",
                             f"Something went wrong: {value}\n\nDetails were saved to crash.log.")


def main():
    check = [arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--self-check=")]
    if check:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # build computers have no screen
    else:
        sys.excepthook = report_crash      # its popup would wait forever with no one to click OK
    app = QApplication(sys.argv)
    app.setApplicationName("Speedy Scandocs")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.QSS)
    if check:
        sys.exit(self_check.run(MainWindow, check[0]))
    demo = "--demo" in sys.argv
    # Only one copy at a time, so the same scans can't be processed twice.
    lock = QLockFile(str(engine.app_data_dir() / ("demo.lock" if demo else "app.lock")))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Speedy Scandocs", "Speedy Scandocs is already open.")
        return
    window = MainWindow(demo=demo)
    window.show()
    QTimer.singleShot(0, window.first_run_guide)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
