"""
The guided tour. The window dims, a spotlight lands on one button or area at a time, and a note
glides over beside it to say what that thing does.

The tour never touches the real scans. While it runs, the window points at a throwaway scans
folder of pretend files, so it looks the same on a new computer as on a busy one, and it can show
screens that a person would normally have to go and find, such as Settings or an open document.
"""

import shutil
import tempfile
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QEvent, QMarginsF, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

import engine
import theme

NOTE_WIDTH = 372
EDGE = 14                     # the note stays this far inside the window
GAP = 28                      # between the note and what it points at, with room for its tail
GLIDE_MS = 420
PULSE_MS = 1500

# The pretend files: folder, file name, what Claude did, client, description, Claude's note.
SAMPLE_SCANS = ("scan_0041.pdf", "scan_0042.pdf", "scan_0043.pdf", "scan_0044.pdf")
SAMPLE_FILES = (
    ("named", "BAKER, Elena - Notice of Hearing 12-03-2026.pdf", "named", "BAKER, Elena",
     "Notice of Hearing 12-03-2026", "Client's name is in the address block on page 1."),
    ("named", "MORRIS, Thomas - Medical Records Dr Patel Claim 2025-0418.pdf", "named", "MORRIS, Thomas",
     "Medical Records Dr Patel Claim 2025-0418", "Client's name and claim number are at the top of page 1."),
    ("named", "NGUYEN, Linh - Letter from Insurance Adjuster.pdf", "named", "NGUYEN, Linh",
     "Letter from Insurance Adjuster", "The letter is addressed to the client."),
    ("review", "FOSTER, Karen - Medical Bill.pdf", "check", "FOSTER, Karen", "Medical Bill",
     "Two clients named Foster could fit, and the first name is hard to read."),
    ("review", "ORTEGA, Daniel - Signed Retainer Agreement.pdf", "new client", "ORTEGA, Daniel",
     "Signed Retainer Agreement", "This person signed on page 2, but isn't on your client list yet."),
    ("failed", "scan_0037.pdf", "no name", "", "", "No client name on any of the pages Claude read."),
    ("failed", "scan_0038.pdf", "error", "", "", "This file wouldn't open."),
    ("completed", "BAKER, Elena - Temporary Light Duty Offer.pdf", "named", "BAKER, Elena",
     "Temporary Light Duty Offer", ""),
    ("completed", "NGUYEN, Linh - Wage Statement.pdf", "named", "NGUYEN, Linh", "Wage Statement", ""),
)
SAMPLE_CLIENTS = "BAKER, Elena\nFOSTER, Karen\nFOSTER, Kevin\nMORRIS, Thomas\nNGUYEN, Linh\n"
SAMPLE_REQUEST = "Medical bills should say who the provider is"
SAMPLE_RULE_PROPOSAL = dict(
    summary="Your MoveDocs rule already covers some medical bills, so the two could clash.",
    conflict_rule='MoveDocs bills: call them "MoveDocs Bill" plus the provider name.',
    recommended=0,
    options=[
        dict(action="add", line=None, old_rule="", typed=False, title="Add the new rule, worded so both can stay",
             why="Bills from MoveDocs keep following your MoveDocs rule.",
             new_rule='Medical bills: unless they came through MoveDocs, name them "Medical Bill" plus the '
                      'provider, for example "Medical Bill Lakeside Clinic".'),
        dict(action="edit", line=0, typed=False, title="Reword the MoveDocs rule instead",
             old_rule='MoveDocs bills: call them "MoveDocs Bill" plus the provider name.',
             why="One rule would cover every medical bill.",
             new_rule='Medical bills: name them "Medical Bill" plus the provider, including bills from MoveDocs.'),
        dict(action="none", line=None, old_rule="", new_rule="", typed=False, title="Leave the rules as they are",
             why="Nothing changes."),
    ])


# ---------------------------------------------------------------- where the spotlight lands
# Each returns a widget, a rectangle in window coordinates, or a list of those to wrap together.

def tab(view):
    return lambda t: on_window(t.win.tabs, t.win.tabs.shape(list(t.win.items).index(view)).boundingRect().toRect())


def all_tabs(t):
    return [tab(view)(t) for view in t.win.items]


def rows(first, last=None):
    """The rows of the file list, counting from 0."""
    def target(t):
        found = [t.win.list.visualItemRect(t.win.list.item(i)) for i in range(first, (last or first) + 1)
                 if i < t.win.list.count()]
        return [on_window(t.win.list.viewport(), r) for r in found] or t.win.list
    return target


def page(t):
    """The page itself in the open document, not the empty space around it."""
    image = t.win.preview.image
    size = image.pixmap().deviceIndependentSize().toSize()
    box = QRect(QPoint(0, 0), size)
    box.moveCenter(image.rect().center())
    return on_window(image, box)


def desk_link(text):
    return lambda t: next(b for b in t.win.findChildren(QPushButton) if b.objectName() == "deskLink"
                          and b.text() == text)


def sheet_link(text):
    return lambda t: next(b for b in t.sheet.findChildren(QPushButton) if b.text() == text)


def on_window(widget, rect):
    return QRect(widget.mapTo(widget.window(), rect.topLeft()), rect.size())


# ---------------------------------------------------------------- the stops
#
# view     the folder to show
# sheet    a dialog to lay open on the window
# stage    "preview", "working" or "undo": something that only appears while the app is in use
# unchecked  show Home before Check Scandocs Folder has been clicked
# row      which file to select
# target   where the spotlight lands. Leave it out for a note in the middle of the window
# side     where the note should sit, if that matters
# keys / folders / note   extra lines in the note

FOLDER_TOUR = (("new", "New scans from the scanner."),
               ("named", "Matched a client on your list."),
               ("review", "A new client, or Claude wasn't sure."),
               ("failed", "Claude couldn't come up with a name."),
               ("completed", "Checked by you and ready to put away."))

SETTINGS = dict(view="completed", sheet="settings")

STEPS = (
    dict(view="new", unchecked=True, title="Welcome to Speedy Scandocs",
         text="Speedy Scandocs reads each scan and suggests a file name, so all you have to do is check "
              "its work.\n\nThis tour shows you around using pretend files. Your real files are safe "
              "while it runs.",
         note="Click Next or press the Right arrow to move on. Press Esc to leave at any time."),
    dict(view="new", unchecked=True, target=all_tabs, title="Your five folders",
         text="Every scan sits in one of these folders. Click a tab to open that folder. The number on "
              "the tab tells you how many files are inside.",
         folders=FOLDER_TOUR),
    dict(view="new", unchecked=True, target=lambda t: t.win.check_btn, title="Check for new scans",
         text="Start here. Click this to see what the scanner has saved. Home stays empty until you do, "
              "even if scans are waiting."),
    dict(view="new", target=rows(0, 3), title="See what came in",
         text="New scans are listed here with the plain names the scanner gave them. The Home tab now "
              "shows how many there are."),
    dict(view="new", target=lambda t: t.win.process_btn, title="Let Claude name them",
         text="Click Auto Process and Claude reads each scan and suggests a name. Each file then moves "
              "on its own to Named, Review or Failed.",
         note="This button only wakes up after Check Scandocs Folder finds something."),
    dict(view="new", stage="working", target=lambda t: t.win.progress_box, title="While Claude works",
         text="The bar shows how far along it is, and the line above it shows which file it's reading.\n\n"
              "Need to stop early? Click Stop. Claude finishes the file it's on, and the rest stay in "
              "Home for next time."),
    dict(view="named", target=tab("named"), title="Start with Named",
         text="When Claude is done, work through the folders from left to right. These files matched a "
              "client on your list, so most only need a quick look."),
    dict(view="named", target=rows(0), title="Reading a row",
         text="The client is on the left and the description is beside it. The small line underneath "
              "says how Claude worked it out.\n\nClick a row to select it, or use the Up and Down arrows."),
    dict(view="named", stage="preview", target=page, side="right", title="Open the document",
         text="With a file selected, press Space or double-click it to see the actual document.\n\n"
              "Claude's name is only a suggestion, so this is where you check it."),
    dict(view="named", stage="preview", target=lambda t: t.win.preview.keys, title="Getting around",
         text="The keys are listed along the bottom in case you forget.",
         keys=(("Up / Down", "Go to the next or previous document."),
               ("Left / Right", "Turn the pages."),
               ("Enter", "The name is right."),
               (engine.RENAME_KEY, "Change the name."),
               ("Space", "Close the document."))),
    dict(view="named", target=lambda t: t.win.name_edit, title="The suggested name",
         text="Names go like this: LAST, First, then a dash, then a short description.\n\n"
              f"To change one, press {engine.RENAME_KEY} or click in the box. As you type a client, matching names from "
              "your list pop up to choose from."),
    dict(view="named", target=lambda t: t.win.confirm_btn, title="Accept the name",
         text="If the name is right, press Enter or click Correct. The file moves to Ready to File with "
              "that name.",
         note="After you change a name, this button says Save instead."),
    dict(view="named", sheet="ask", target=lambda t: t.sheet.card, title="One more look",
         text="You'll see this quick check before a file moves. Press Enter for yes, or Esc to go back.",
         note="Don't need it? You can turn it off in Settings."),
    dict(view="named", stage="preview", sheet="rename", target=lambda t: t.sheet.name, side="below",
         title="Fix a name while reading",
         text=f"Press {engine.RENAME_KEY} with a document open and this box pops up with the name already filled in, so "
              "you can change just the part that's wrong. Press Enter to save."),
    dict(view="named", stage="undo", target=lambda t: t.win.toast, title="Changed your mind?",
         text=f"This message shows up after each move. Click Undo or press {engine.UNDO_KEY} and the file goes back "
              "where it was.",
         note="Undo only reaches the last file you moved."),
    dict(view="review", target=rows(0, 1), title="Next, Review",
         text="Claude puts a file here when it wants a person to look closely. The stamp on the right "
              "says why, and the small line says what Claude noticed.",
         keys=(("Check", "Claude has an idea, but isn't sure it's right."),
               ("New client", "This person isn't on your client list yet."))),
    dict(view="review", row=1, target=lambda t: t.win.hint, title="Adding a new client",
         text="A new client joins your list the first time you accept one of their files, and not "
              "before. This line tells you when that's about to happen.\n\nIf Claude picked the wrong "
              "person, just fix the name."),
    dict(view="failed", target=rows(0, 1), title="Then, Failed",
         text="Claude couldn't come up with a name for these, or the file wouldn't open. Open the "
              "document, type the name in the box at the bottom, and press Enter."),
    dict(view="failed", target=lambda t: t.win.retry_btn, title="Try again",
         text="Think Claude could do better a second time? This sends the file back to Home. It goes "
              "through Auto Process again with your next batch."),
    dict(view="completed", target=rows(0, 1), title="Ready to File",
         text="Every file you've accepted ends up here with its new name.",
         note="Claude learns from each name you accept or fix, so it should need less fixing over time."),
    dict(view="completed", target=lambda t: t.win.open_btn, title="Put them away",
         text="Click this to open the folder on your computer, then move each file into its client's "
              "folder. That last step is done by hand."),
    dict(view="completed", target=desk_link("Settings"), title="Settings",
         text="You won't need Settings every day, but it's worth knowing what's in there. Here's a "
              "quick look."),
    dict(SETTINGS, target=lambda t: t.sheet.folder, title="Scans folder",
         text="This is the folder your scanner saves to. When you choose one, the app sets up the "
              "folders it needs inside it, and it asks you first."),
    dict(SETTINGS, target=lambda t: t.sheet.settings_folder, title="Settings folder",
         text="This holds your client list, naming rules and what Claude has learned. If every computer "
              "points to the same shared folder, the whole office stays in step."),
    dict(SETTINGS, target=lambda t: [t.sheet.key, t.sheet.test_btn], title="Bedrock API key",
         text="The key is what lets the app reach Claude. Paste it here, then click Test to make sure "
              f"it works. It's kept safely {engine.KEY_STORE}, not in a file."),
    dict(SETTINGS, target=lambda t: [t.sheet.model, t.sheet.region], title="Model and region",
         text="You can leave these alone unless someone asks you to change them. The recommended model "
              "is marked in the list."),
    dict(SETTINGS, target=lambda t: [t.sheet.confirm_twice, t.sheet.guidance], title="Two choices",
         text="The first box turns the “Is this name correct?” check on or off. The second shows or "
              "hides the short instructions on each screen."),
    dict(SETTINGS, target=sheet_link("Add a Naming Rule"), title="Add a Naming Rule",
         text="Want files named a certain way from now on? Click here to add a rule or change one you "
              "already have. Claude helps with the wording, and you get the last word."),
    dict(view="completed", sheet="rule", target=lambda t: t.sheet.box, title="Say it in your own words",
         text="Type what you'd like the way you'd say it to a coworker, then click Review. Claude will "
              "work out the wording for you.",
         note="The list below this box picks which Claude writes the rule. The recommended one is fine."),
    dict(view="completed", sheet="rule_review", target=lambda t: t.sheet.conflict, title="Claude checks your other rules",
         text="Claude compares your request with the rules you already have. If they could clash, it "
              "shows you the rule here. This won't always show up."),
    dict(view="completed", sheet="rule_review", target=lambda t: t.sheet.options, title="Pick what to do",
         text="You'll always get a clear choice, with Claude's recommendation marked. It might be new "
              "wording for the new rule, new wording for the old one, or leaving things as they are."),
    dict(view="completed", sheet="rule_review", target=lambda t: t.sheet.rule_box, title="Check the wording",
         text="This is the rule exactly as it would be saved. If you'd like it worded differently, you "
              "can change it right here.",
         note="If the option changes a rule you already have, the current rule is shown above so you "
              "can compare them."),
    dict(view="completed", sheet="rule_review", target=lambda t: t.sheet.save_btn, title="Nothing changes until you say so",
         text="This button follows your choice, and a saved rule applies from your next Auto Process. "
              "Click Back if you'd rather start over.",
         note="Your old rules are saved as a backup first. The app keeps the three most recent."),
    dict(SETTINGS, target=lambda t: [sheet_link("Client list")(t), sheet_link("Activity log")(t)],
         title="Your lists and records",
         text="These open the files behind the app.",
         keys=(("Client list", "Everyone Claude can match a scan to."),
               ("Naming rules", "All of your rules. Add a Naming Rule is the easiest way to change them."),
               ("Activity log", "A record of every file Claude has read."))),
    dict(SETTINGS, target=lambda t: t.sheet.usage, title="What it costs",
         text="This shows how much Claude has been used, and a rough cost for the last 7 days and for "
              "overall. Your actual bill may be a little different."),
    dict(view="completed", target=desk_link("Guide"), title="That's everything",
         text="You're ready to go. Click Guide whenever you want to take this tour again."),
)


# ---------------------------------------------------------------- the pretend scans folder

def write_sample_pdf(path):
    """A two-page letter for the open-document stops. Every pretend file is a copy of it."""
    pdf = QPdfWriter(str(path))
    pdf.setPageSize(QPageSize(QPageSize.Letter))
    pdf.setResolution(150)
    p = QPainter(pdf)
    width = pdf.width()
    head, body = QFont("Georgia"), QFont("Georgia")
    head.setPixelSize(38)
    head.setBold(True)
    body.setPixelSize(23)
    pages = (("HEARINGS OFFICE", ("December 3, 2026", "", "Elena Baker", "412 Maple Street", "", "",
                                  "NOTICE OF HEARING", "", "Dear Ms. Baker:", "",
                                  "This is a sample document for the Speedy Scandocs tour.",
                                  "No real person or case is described here.", "",
                                  "A hearing has been set for the date shown above.",
                                  "Please bring any papers you would like reviewed.")),
             ("HEARINGS OFFICE", ("Page 2", "", "If you need a different date, please call this office.", "",
                                  "Sincerely,", "", "The Hearings Clerk")))
    for number, (title, lines) in enumerate(pages):
        if number:
            pdf.newPage()
        p.setFont(head)
        p.setPen(QColor(theme.INK))
        p.drawText(QRect(0, 110, width, 60), Qt.AlignCenter, title)
        p.setPen(QPen(QColor(theme.INK), 3))
        p.drawLine(140, 190, width - 140, 190)
        p.setFont(body)
        for i, line in enumerate(lines):
            p.drawText(140, 270 + i * 40, line)
    p.end()


def make_sample_folder(root):
    ws = engine.Workspace(root)
    ws.create()
    ws.client_list.write_text(SAMPLE_CLIENTS, encoding="utf-8")
    letter = ws.root / SAMPLE_SCANS[0]
    write_sample_pdf(letter)
    for name in SAMPLE_SCANS[1:]:
        shutil.copy2(letter, ws.root / name)
    for bucket, name, result, client, description, reason in SAMPLE_FILES:
        shutil.copy2(letter, ws.folder(bucket) / name)
        row = dict.fromkeys(engine.LOG_FIELDS, "")
        row.update(time=datetime.now().isoformat(timespec="seconds"), original="scan.pdf", result=result,
                   new_name=name, client=client, description=description, reason=reason, pages_read=2,
                   input=2600, cache_read=48000, cache_write=0, output=140,
                   model=engine.DEFAULT_SETTINGS["model_id"])
        engine.append_csv(ws.log_file, engine.LOG_FIELDS, row)
    return ws


# ---------------------------------------------------------------- the note

class Note(QFrame):
    """The sheet of paper that glides from stop to stop."""

    def __init__(self, tour):
        super().__init__(tour, objectName="card")
        self.setFixedWidth(NOTE_WIDTH)
        self.setGraphicsEffect(QGraphicsDropShadowEffect(self, blurRadius=30, offset=QPoint(0, 8),
                                                         color=QColor(0, 0, 0, 130)))
        wrap = QVBoxLayout(self)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(0)
        self.strip = QFrame()
        self.strip.setFixedHeight(7)
        wrap.addWidget(self.strip)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(22, 16, 22, 16)
        self.body.setSpacing(14)
        wrap.addLayout(self.body)
        self.content = None

        row = QHBoxLayout()
        row.setSpacing(6)
        self.counter = QLabel(objectName="formHint")
        row.addWidget(self.counter)
        row.addStretch()
        self.skip_btn = QPushButton("Skip", objectName="link")
        self.skip_btn.clicked.connect(tour.finish)
        self.back_btn = QPushButton("Back", objectName="quiet")
        self.back_btn.clicked.connect(tour.back)
        self.next_btn = QPushButton()
        self.next_btn.clicked.connect(tour.forward)
        for button in (self.skip_btn, self.back_btn, self.next_btn):
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)          # so the arrow keys and Enter always reach the tour
            row.addWidget(button)
        self.body.addLayout(row)

    def fill(self, step, i, total):
        if self.content:
            self.body.removeWidget(self.content)
            self.content.hide()
            self.content.deleteLater()
        self.content = self.make_content(step)
        self.body.insertWidget(0, self.content)
        self.content.show()
        last = i == total - 1
        self.strip.setStyleSheet("background: %s; border-top-left-radius: 3px; border-top-right-radius: 3px;"
                                 % theme.FOLDERS[step["view"]]["fill"])
        self.counter.setText(f"{i + 1} of {total}")
        self.skip_btn.setVisible(not last)
        self.back_btn.setVisible(i > 0)
        self.next_btn.setText("Get Started" if last else "Next")
        self.resize(NOTE_WIDTH, self.layout().totalHeightForWidth(NOTE_WIDTH))

    def make_content(self, step):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        title = QLabel(step["title"], objectName="cardTitle", wordWrap=True)
        lay.addWidget(title)
        lay.addWidget(self.text(step["text"]))
        rows = [(QLabel(key, objectName="keycap"), text) for key, text in step.get("keys", ())]
        rows += [(self.folder_chip(view), text) for view, text in step.get("folders", ())]
        if rows:
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            grid.setColumnStretch(1, 1)
            for i, (label, text) in enumerate(rows):
                grid.addWidget(label, i, 0, Qt.AlignLeft | Qt.AlignTop)
                grid.addWidget(self.text(text, "guideRow"), i, 1)
            lay.addLayout(grid)
        if "note" in step:
            lay.addWidget(self.text(step["note"], "formHint"))
        return page

    def text(self, text, name="cardBody"):
        label = QLabel(text, objectName=name, wordWrap=True)
        label.setTextFormat(Qt.PlainText)
        return label

    def folder_chip(self, view):
        chip = QLabel(self.titles[view], objectName="folderChip")
        folder = theme.FOLDERS[view]
        chip.setStyleSheet(f"background: {folder['fill']}; color: {folder['on']};")
        return chip


# ---------------------------------------------------------------- the tour

class Tour(QWidget):
    """
    Lies over the whole window. It takes every click and key, so nothing behind it can be used.

    sheets maps a stop's "sheet" to a function that makes that dialog. They are laid onto the
    window as plain widgets, so the spotlight can sit on the controls inside them.
    """

    def __init__(self, win, sheets, titles, steps=STEPS):
        super().__init__(win)
        self.win = win
        self.sheets = sheets
        self.steps = steps
        self.i = 0
        self.sheet = None
        self.sheet_name = None
        self.hole = self.hole_from = self.hole_to = QRectF()
        self.pos_from = self.pos_to = QPoint()
        self.pulse = 0.0
        self.setFocusPolicy(Qt.StrongFocus)
        Note.titles = titles
        self.note = Note(self)

        self.glide = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=GLIDE_MS)
        self.glide.setEasingCurve(QEasingCurve.OutCubic)
        self.glide.valueChanged.connect(self.frame)
        self.beat = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=PULSE_MS, loopCount=-1)
        self.beat.valueChanged.connect(self.pulsed)
        self.resized = QTimer(self, singleShot=True, interval=30, timeout=self.snap)

    # ------------------------------------------------------------ start and finish

    def start(self):
        win = self.win
        self.kept = dict(ws=win.ws, view=win.view, checked=win.checked, undo=win.last_undo,
                         typed=win.name_edit.text(), file=win.current().name if win.current() else None)
        self.folder = tempfile.TemporaryDirectory(prefix="scandocs_tour_", ignore_cleanup_errors=True)
        win.ws = make_sample_folder(self.folder.name)
        win.last_undo = None                           # so Ctrl+Z can't reach for a real file
        win.toast.hide()
        win.installEventFilter(self)
        self.setGeometry(win.rect())
        self.show()
        self.raise_()
        self.go(0, glide=False)
        self.beat.start()

    def finish(self):
        win, kept = self.win, self.kept
        self.glide.stop()
        self.beat.stop()
        self.resized.stop()
        win.removeEventFilter(self)
        self.hide()
        self.clear_stage()
        self.close_sheet()
        win.ws, win.checked, win.last_undo = kept["ws"], kept["checked"], kept["undo"]
        win.items = {view: [] for view in win.items}
        win.refresh()
        win.show_view(kept["view"])
        if kept["file"]:
            win.draw_list(select_name=kept["file"])
            win.name_edit.setText(kept["typed"])
            win.update_action()
        self.folder.cleanup()
        self.deleteLater()

    # ------------------------------------------------------------ moving between stops

    def forward(self):
        if self.i == len(self.steps) - 1:
            self.finish()
        else:
            self.go(self.i + 1)

    def back(self):
        if self.i > 0:
            self.go(self.i - 1)

    def go(self, i, glide=True):
        self.i = i
        step = self.steps[i]
        self.set_stage(step)
        self.note.fill(step, i, len(self.steps))
        self.settle_layouts()
        self.hole_to = self.spotlight(step)
        self.pos_to = self.place_note(self.hole_to, step.get("side"))
        self.hole_from, self.pos_from = self.hole, self.note.pos()
        self.setFocus()
        self.glide.stop()
        if glide and self.isVisible():
            self.glide.start()
        else:
            self.frame(1.0)

    def frame(self, t):
        """One moment of the glide, with t going from 0 to 1."""
        a, b = self.hole_from, self.hole_to
        mix = lambda x, y: x + (y - x) * t
        self.hole = QRectF(mix(a.left(), b.left()), mix(a.top(), b.top()),
                           mix(a.width(), b.width()), mix(a.height(), b.height()))
        self.note.move(int(mix(self.pos_from.x(), self.pos_to.x())), int(mix(self.pos_from.y(), self.pos_to.y())))
        self.update()

    def pulsed(self, value):
        self.pulse = value
        self.update(self.hole.adjusted(-24, -24, 24, 24).toAlignedRect())

    def snap(self):
        """The window changed size: put everything straight back in place."""
        self.setGeometry(self.win.rect())
        self.settle_layouts()
        self.place_sheet()
        self.go(self.i, glide=False)

    # ------------------------------------------------------------ what's on show behind the tour

    def set_stage(self, step):
        win = self.win
        self.clear_stage()
        win.checked = not step.get("unchecked")
        win.refresh()
        win.show_view(step["view"])
        if win.list.count():
            win.list.setCurrentRow(step.get("row", 0))
        stage = step.get("stage")
        if stage == "preview":
            win.preview.open()
        elif stage == "working":
            win.status.setText(f"Reading 2 of {len(SAMPLE_SCANS)}:  {SAMPLE_SCANS[1]}")
            win.bar.setRange(0, len(SAMPLE_SCANS))
            win.bar.setValue(1)
            win.progress_box.show()
            win.check_btn.setEnabled(False)
            win.process_btn.setEnabled(False)
        elif stage == "undo":
            win.toast.say("Moved to Ready to File.", can_undo=True, ms=3_600_000)
        if step.get("sheet") != self.sheet_name:
            self.close_sheet()
        if step.get("sheet") and not self.sheet:
            self.open_sheet(step["sheet"])
        self.raise_()

    def clear_stage(self):
        self.win.preview.hide()
        self.win.toast.hide()
        self.win.toast.timer.stop()
        self.win.progress_box.hide()

    def open_sheet(self, name):
        self.sheet = self.sheets[name]()
        self.sheet_name = name
        self.sheet.setParent(self.win, Qt.Widget)
        self.sheet.show()
        self.place_sheet()

    def place_sheet(self):
        if self.sheet:
            self.sheet.adjustSize()
            self.sheet.move((self.width() - self.sheet.width()) // 2, max((self.height() - self.sheet.height()) // 2, 0))

    def close_sheet(self):
        if self.sheet:
            self.sheet.hide()
            self.sheet.deleteLater()
        self.sheet = self.sheet_name = None

    def settle_layouts(self):
        """Things were just shown and hidden. Let them land before measuring where they are."""
        for _ in range(3):
            QApplication.sendPostedEvents(None, QEvent.LayoutRequest)

    # ------------------------------------------------------------ measuring

    def box(self, thing):
        if isinstance(thing, QRect):
            return thing
        if isinstance(thing, (list, tuple)):
            area = QRect()
            for part in thing:
                area = area.united(self.box(part))
            return area
        return on_window(thing, thing.rect())

    def spotlight(self, step):
        """Where the spotlight goes. No target gives an empty spot in the middle of the window."""
        if "target" not in step:
            return QRectF(QPointF(self.rect().center()), QPointF(self.rect().center()))
        area = QRectF(self.box(step["target"](self)))
        if self.sheet and area.bottom() > self.height() - EDGE:      # a tall dialog on a short window
            self.sheet.move(self.sheet.x(), self.sheet.y() - int(area.bottom() - self.height() + EDGE * 2))
            area = QRectF(self.box(step["target"](self)))
        return area.marginsAdded(QMarginsF(6, 6, 6, 6)).intersected(QRectF(self.rect()).adjusted(2, 2, -2, -2))

    def place_note(self, hole, prefer=None):
        """Beside the spotlight, covering as little of it as the window allows. Never off the window."""
        w, h = self.note.width(), self.note.height()
        room = self.rect().adjusted(EDGE, EDGE, -EDGE - w, -EDGE - h)
        keep_x = lambda x: max(room.left(), min(int(x), room.right()))
        keep_y = lambda y: max(room.top(), min(int(y), room.bottom()))
        if hole.isEmpty():
            return QPoint(keep_x((self.width() - w) / 2), keep_y((self.height() - h) / 2))
        middle = hole.center()
        spots = dict(below=QPoint(keep_x(middle.x() - w / 2), keep_y(hole.bottom() + GAP)),
                     above=QPoint(keep_x(middle.x() - w / 2), keep_y(hole.top() - GAP - h)),
                     right=QPoint(keep_x(hole.right() + GAP), keep_y(middle.y() - h / 2)),
                     left=QPoint(keep_x(hole.left() - GAP - w), keep_y(middle.y() - h / 2)))

        def covered(side):
            overlap = QRectF(QRect(spots[side], self.note.size())).intersected(hole)
            return overlap.width() * overlap.height()

        return spots[min(([prefer] if prefer else []) + ["below", "above", "right", "left"], key=covered)]

    # ------------------------------------------------------------ drawing

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = QPainterPath()
        dark.addRect(QRectF(self.rect()))
        if not self.hole.isEmpty():
            light = QPainterPath()
            light.addRoundedRect(self.hole, 5, 5)
            dark = dark.subtracted(light)
        p.fillPath(dark, QColor(24, 18, 13, 172))
        if self.hole.isEmpty():
            return
        p.setBrush(Qt.NoBrush)
        spread = self.pulse * 14
        ring = QColor(theme.HIGHLIGHT)
        ring.setAlphaF(0.55 * (1 - self.pulse))
        p.setPen(QPen(ring, 2))
        p.drawRoundedRect(self.hole.adjusted(-spread, -spread, spread, spread), 5 + spread, 5 + spread)
        p.setPen(QPen(QColor(theme.HIGHLIGHT), 3))
        p.drawRoundedRect(self.hole, 5, 5)
        tail = self.note_tail()
        if tail:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.PAPER))
            p.drawPolygon(tail)

    def note_tail(self):
        """The little point on the note that shows what it's talking about. None if it sits on top."""
        note, hole = QRectF(self.note.geometry()), self.hole
        reach, half = 19, 11
        mid_x = max(note.left() + 24, min(hole.center().x(), note.right() - 24))
        mid_y = max(note.top() + 24, min(hole.center().y(), note.bottom() - 24))
        if note.top() >= hole.bottom():
            return QPolygonF([QPointF(mid_x - half, note.top() + 1), QPointF(mid_x + half, note.top() + 1),
                              QPointF(mid_x, note.top() - reach)])
        if note.bottom() <= hole.top():
            return QPolygonF([QPointF(mid_x - half, note.bottom() - 1), QPointF(mid_x + half, note.bottom() - 1),
                              QPointF(mid_x, note.bottom() + reach)])
        if note.left() >= hole.right():
            return QPolygonF([QPointF(note.left() + 1, mid_y - half), QPointF(note.left() + 1, mid_y + half),
                              QPointF(note.left() - reach, mid_y)])
        if note.right() <= hole.left():
            return QPolygonF([QPointF(note.right() - 1, mid_y - half), QPointF(note.right() - 1, mid_y + half),
                              QPointF(note.right() + reach, mid_y)])
        return None

    # ------------------------------------------------------------ input

    def eventFilter(self, watched, event):
        if watched is self.win and event.type() in (QEvent.Resize, QEvent.Show):
            self.resized.start()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter):
            self.forward()
        elif key == Qt.Key_Left:
            self.back()
        elif key == Qt.Key_Escape:
            self.finish()

    def focusNextPrevChild(self, forward):
        return False

    def mousePressEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()
