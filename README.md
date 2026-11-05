# Speedy Scandocs v2

## The app (start here)

Most people should install the packaged app, which needs no Python:

- **Windows:** unzip `Speedy-Scandocs-<version>-Windows.zip`, keep the whole folder together, and open
  **Speedy Scandocs.exe** inside it. It isn't signed, so the first time Windows may show "Windows
  protected your PC". Click **More info**, then **Run anyway**.
- **Mac (Apple Silicon only):** unzip `Speedy-Scandocs-<version>-Mac.zip` and drag **Speedy Scandocs**
  to Applications. It isn't signed by Apple, so macOS refuses it the first time. Click **Done**, go to
  **System Settings**, **Privacy & Security**, click **Open Anyway** at the bottom, and confirm.

To run it from this folder instead, double-click **Speedy Scandocs.vbs** on Windows or **Speedy
Scandocs.command** on a Mac. The first time, it offers to install what it needs.

In **Settings**, choose the scans folder and paste the Bedrock API key. The key is kept in Windows
Credential Manager or the Mac Keychain, not in a file. When a new folder is chosen, the app asks
first, then creates:

| Folder | What's in it |
|---|---|
| (the scans folder itself) | New PDFs from the scanner |
| `Named` | Matched a client on the list |
| `Review` | Named, but a new client or Claude wasn't sure |
| `Failed` | Claude couldn't name it, or the file wouldn't open |
| `Ready to File` | A person confirmed it. Staff file these by hand |
| `Settings` | Client list, naming rules, decisions, activity log, unless a shared settings folder is chosen |

In the app, the first tab is **Home** (the scans folder itself). A scans folder set up by an earlier
version has a `Completed` folder; it is renamed to `Ready to File` the next time the app opens it.
If something is open in it, whatever can move does, and the rest moves on a later start. Update every
computer at the same time, because an older copy of the app makes `Completed` again.

**Using it:** A guided tour opens the first time, and **Guide** at the top opens it again. It moves
around the window, spotlighting each button and area in turn, and it uses pretend files in a
temporary folder, so real scans are never touched (`tour.py`). Check
Scandocs Folder, then Auto Process. Then go through Named, Review and Failed. Space opens the file:
Up and Down change documents, Left and Right change pages, Enter confirms the name, and F2 opens a
popup with the suggested name filled in, so part of it can be changed. With the file closed, F2 or
the box at the bottom changes the name and Enter saves it. Ctrl+Z undoes the last one. Asking "Is
this name correct?" a second time is on by default and can be turned off in Settings.

**Model:** Claude Haiku 5.5 is the recommended model and the default for new installs. A computer
that already saved a choice keeps it until someone changes it in Settings.

**Shared settings:** in Settings, **Settings folder** can point anywhere, so the office can share one
client list, one set of rules, the decisions Claude learns from, and the activity log, even when each
computer has its own scans folder. Point every computer at the same folder. If the chosen folder has
`client_list.txt` and `naming_rules.txt`, it's used as it is. If not, the app offers to choose another
folder or create them there, copying what's in use now and never replacing anything. The old files stay
where they were. If a shared folder can't be reached or loses those files, the app stops and says so
instead of making blank ones. On Dropbox, keep the folder available offline, and if two people change the
same file at once Dropbox may keep a "conflicted copy", so check for those now and then.

**Naming rules:** in Settings, **Add a Naming Rule** first reminds staff that it uses AI tokens and
should only be used once they've tested and are confident a new rule is needed. It then lets them
describe a new rule or a change in their own words. Claude checks the request against the other rules, says what it found, and lays
out up to three options with one recommended, such as new wording for the new rule or for the old
one. Leaving the rules as they are is always offered. Staff pick one and can adjust the wording, and
nothing is saved until they do. Without a key or a connection, the rule can be saved as typed. The
box has its own model choice, separate from the scanning model. Claude Sonnet 5.5 is recommended and
is the default, and the choice is remembered. These requests are not in the usage totals. The
old file is first copied to `Rule Backups\naming_rules_obsolete_<date and time>.txt`, beside it, and
only the three newest copies are kept. Changes made by hand in Notepad are not backed up.

**Version:** the version number is `VERSION` in `engine.py`. It shows beside the app name and in
Settings.

**Usage:** the bottom of Settings shows tokens and estimated cost for the last 7 days and for the
life of this scans folder, added up from `Settings\scandocs_log.csv`. Costs use Anthropic's published
prices (`PRICES` in `engine.py`, update them if prices change), so the Bedrock bill can differ. Files
logged before the model was recorded are priced at the model chosen in Settings.

**Learning:** every confirmed or corrected name goes in `Settings\decisions.csv` and is shown to
Claude on later runs. A new client joins the client list only when a person confirms that file.
Unless a shared settings folder is chosen, each scans folder has its own client list and rules.

**On a Mac:** the app works the same, except that Cmd+Z undoes and laptops need fn+F2 to change a
name. The background script below is for Windows only.

**Tests:** `python test/test_app.py` (no AI, no key). Those tests stay on the development computer,
so a release is tested by `self_check.py` instead, which needs no client data.

The rest of this file describes the older background script, `scandocs.py`, which still works.

## The background script

Names scanned PDFs as `LAST, First - Short Description.pdf` using Claude on Amazon Bedrock
(zero data retention). Runs in the background through Windows Task Scheduler: every hour from
7 AM to 7 PM, plus once when the employee signs in each morning. The computer can sleep or be
shut down at night; a missed run happens once on waking. Need a scan sooner? Use **Name Scans Now**.

## How it works

1. A PDF lands in the **scan folder**.
2. The first 2 pages are turned into images and sent to Claude with the full client list,
   the office's naming rules, and past corrections.
3. Claude picks an exact name from the client list, or proposes a new client's name.
   If it finds no client name at all, it gets pages 3 and 4 (this catches fax cover sheets).
4. **Known client:** the file moves straight to the **named folder**.
   **New client:** the file goes to the **review folder**, already named. If it looks right,
   staff just drag it into the named folder, and the client is added to the list automatically.
   **No name found:** the file goes to the review folder with its original name.
5. Everything is logged in `scandocs_log.csv`.

## Files

| File | What it is | Who edits it |
|---|---|---|
| `scandocs.py` | The program | Developer |
| `config.toml` | Folders, region, model | Set once |
| `client_list.txt` | One client per line, `LAST, First` | Grows by itself as staff approve new clients. Can start empty, or paste in an export |
| `naming_rules.txt` | Plain-English naming rules | Office, any time |
| `corrections.csv` | Written by the program when staff rename its files | Program (can be pruned by hand) |
| `scandocs_log.csv` | Every file processed, with tokens used | Program |
| `requirements.txt` | Python libraries | Developer |
| `setup_task.ps1` | Saves the API key and creates the scheduled task | Run once |

## Teaching it (the review loop)

The person who checks the work has three ways to correct it:

- **Rename a file in the named folder.** On its next run the program notices (it recognizes the
  file by its contents, not its name) and adds a line to `corrections.csv`. Recent corrections
  are shown to Claude on every document from then on. Rename before filing the document
  elsewhere, or the correction is missed.
- **Approve a new client:** a file in the review folder that already has a proposed name is a
  new client. If the name is right, drag it into the named folder. That's all; the client
  joins the list and their next documents skip review.
- **Fix a file in the review folder:** rename it `LAST, First - Description.pdf` and move it into
  the named folder. That is recorded as a correction, and the client is added to the list.
- **Fix a client's spelling:** rename the file in the named folder (add a hyphen, a second
  surname, fix a typo). The client list is updated to the new spelling, not duplicated. If
  the new name is a different person (different first name), that person is added instead and
  the old entry is left alone. Files already named with the old spelling are not renamed.
- **Write a rule in `naming_rules.txt`**, for example:
  `MoveDocs bills: call them "MoveDocs Bill" plus the provider name.`
  Rules take effect on the next run.

Nobody has to maintain the client list. Each client's first document is checked by a person,
and from then on the spelling is fixed. To fix a misspelled client, edit `client_list.txt`
in Notepad.

## Test run without AI (`--fake`)

The `test` folder has everything needed to try the whole loop with no key and no AI.
Answers come from `test\fake_answers.csv` (today's dry-run names). Two files are left blank
on purpose so they land in Needs Review.

```
python test\reset_test.py                                   copy the 29 scans into test\Inbox
python scandocs.py --config test\config_test.toml --fake    name them
```

Then play reviewer in `test\Named` and `test\Needs Review`, add a rule to
`test\naming_rules.txt`, and run the second command again. It reports what it learned.
Run `reset_test.py` and the second command once more, then open `test\last_prompt.txt`
to see your rules and corrections in the instructions real Claude would get.
Five clients are left off the test list on purpose so they show up as new clients.
`reset_test.py --all` also forgets the corrections and the new clients.

## Setup (office computer)

1. **AWS.** In the Amazon Bedrock console, choose your region (for example us-west-2) and make
   sure Claude Sonnet 5.5 and Haiku 5.5 are available. Set the account's data retention to `none`.
   Set an AWS Budgets alert (for example $25 a month).
2. **API key.** In Bedrock, create an API key. Long-term keys have an expiry date you choose,
   so put a reminder on the calendar to replace it before it expires. Never email the key.
3. **Python.** Install Python 3.11 or newer from python.org (tick "Add to PATH"), then in this
   folder run: `pip install -r requirements.txt`
4. **Settings.** Edit `config.toml`: the folder names in Dropbox and the region.
   `client_list.txt` can start empty, or paste in an export of current clients to skip
   the first round of approvals.
5. **Try it.** Set the key for this window and do a dry run:
   ```
   set AWS_BEARER_TOKEN_BEDROCK=paste-key-here
   python scandocs.py --dry-run
   ```
   Open `scandocs_log.csv` to see the proposed names. Nothing is moved.
6. **Schedule it.** In PowerShell: `powershell -ExecutionPolicy Bypass -File .\setup_task.ps1`
   Run it while signed in as the employee who checks the scans. It asks for the key once, saves it
   to that Windows user only, creates the scheduled task, and puts these shortcuts on their desktop:
   **Scans - Named**, **Scans - Needs Review**, **Scan Naming Rules** and **Client List**
   (open in Notepad), and **Name Scans Now** (runs it immediately instead of waiting).
   Sign out and back in once so the scheduled task picks up the key.

   After this the employee never needs a terminal.

Optional: set `dry_run = true` in `config.toml` for the first week, check the log, then turn it off.

## Running on a shared Dropbox

- In `config.toml`, `{dropbox}` stands for the Dropbox folder on whichever computer runs the
  script (the team Dropbox if there is one), so the same settings work anywhere. Adjust the
  folder names after it to match the office Dropbox.
- The client list, rules, corrections and log live in Dropbox too (`Scans\Settings`), so they
  are backed up and can be opened from any computer. The setup script copies the starter files
  there on first install.
- Anyone in the office can approve or fix files from their own computer; the moves sync back.
- **Run the scheduled task on one computer only.** Two computers would process the same scans.
- On that computer, right-click the Scans folder in Dropbox and choose **Make available offline**,
  so scans are on the disk when the script runs.
- The script's run lock and file-check cache stay on that computer
  (`%LOCALAPPDATA%\SpeedyScandocs`), so nothing extra syncs to everyone.
- To skip a first round of new-client approvals, paste the old tool's `client_list.txt` (or an
  export) into `Scans\Settings\client_list.txt`.

## Notes

- Model IDs on Bedrock: `us.anthropic.claude-sonnet-5-5` and `us.anthropic.claude-haiku-5-5`
  (use the `us.` or `global.` prefix; plain IDs do not work on bedrock-runtime).
- Cost: each document is about 5,000 tokens of page images plus the cached client list.
  Roughly $0.01 a document on Sonnet, much less on Haiku. The log records tokens per file.
- A file that fails 3 runs in a row (damaged PDF, for example) is moved to the review folder.
- The scheduled task runs only while that Windows user is signed in. It never wakes the computer.
  Change the hours with `.\setup_task.ps1 -StartHour 8 -EndHour 18`.
- Packaging as an .exe: build with PyInstaller as before. `setup_task.ps1` uses
  `scandocs.exe` automatically if it is in the same folder.

## Releases on GitHub

Release repository: https://github.com/treyj1/speedy-scandocs-v2

The GitHub copy must reach the office blank. The client list, the scans folder and the API key are
all set up in the office after installing:

- **Client list:** `client_list.txt` and the starter list in `engine.py` hold comments only. Don't add
  names to either one.
- **Scans folder:** `scan_folder` in `DEFAULT_SETTINGS` stays empty. The real choice is saved in
  `%APPDATA%\SpeedyScandocs\settings.json` on each computer, outside this folder.
- **API key:** It's kept in Windows Credential Manager or the Mac Keychain on each computer, so it's
  never in a file here.
- **Test data:** `.gitignore` leaves out all of `test/`, including `test/fake_answers.csv`,
  `test/client_list_test*.txt`, `test/app_demo/` and `test/live_test/`, along with any `.pdf` or `.csv`
  file. These hold names from real-looking documents. `../files-test/` is outside the repository.

No demo ships. Staff practice on real files, with the guide in the app. `Speedy Scandocs Demo.vbs`
stays on the development computer, and `--demo` stays in `app.py` only because the tests use it.

Push from a Claude Code session on the development computer, not a cloud session, because the test
data isn't on GitHub. This folder (`speedy-scandocs-v2`) is the top of the repository, and the branch
is `main`.

Before each push:

1. Run `python test/test_app.py`. Every test must pass. `FreshInstallTests` checks the client list,
   scans folder and API key.
2. List the files git will add. Nothing from `test/`, no `.pdf` or `.csv` files, and no
   `Speedy Scandocs Demo.vbs`.
3. Search those files for every client name in `test/client_list_test_original.txt`,
   `test/live_test/Settings/client_list.txt` and `test/fake_answers.csv`, and in the file names under
   `test/app_demo/` and `test/live_test/`. Remove any real name found. "GARCIA LOPEZ, Maria" is a
   made-up example and can stay.

### Making a release

Windows and Mac apps are built by GitHub, in `.github/workflows/release.yml`, because a Mac app can
only be built on a Mac. Each one is built with `packaging/speedy_scandocs.spec`, then opened on its
own system with `--self-check` (`self_check.py`). If that fails, nothing is released.

1. Change `VERSION` in `engine.py`, and push.
2. To try a build first: on GitHub, **Actions**, **Build release**, **Run workflow**. The zips are on
   the run's page for 7 days.
3. To release, tag it. The tag must be `v` plus `VERSION`, or the build stops:
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
4. The zips land on a draft in **Releases**. Try each one, then click **Publish release**.

The repository is private, so only people with access to it can download from Releases. Share the
zips with the office some other way, such as Dropbox.

The self-check proves the packaged app opens and its libraries work, not that a person can use it.
Try a new Mac build on a real Mac. It can't reach Bedrock, a scanner or the Keychain's real keys.

To build for this computer only: `pip install pyinstaller`, then
`python -m PyInstaller packaging/speedy_scandocs.spec --noconfirm`. The app is in `dist`.
`GDJ Logo.png` is the logo in the app and `GDJ Logo.ico` is the Windows icon. If the logo changes,
replace both and run `packaging/make_icons.py` to remake the Mac icon.

Neither app is signed, which is why Windows and macOS warn on first opening (see the top of this
file). Removing those warnings takes a paid certificate: an Apple Developer account for the Mac.
