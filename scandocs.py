"""
Speedy Scandocs v2: name scanned PDFs by client using Claude on Amazon Bedrock.

Each run:
  1. Looks for PDFs in the scan folder that have finished writing.
  2. Renders the first pages as images (no OCR).
  3. Sends the images and the client list to Claude, which answers with an exact
     entry from the list, or proposes a new client's name, plus a short description.
  4. Known client: the file moves to the named folder as "LAST, First - Description.pdf".
     New client: the file goes to the review folder already named. When staff move it
     to the named folder, the client is added to the list automatically.
     No client name found: the file goes to the review folder with its original name.

Usage:
  python scandocs.py              process the scan folder once
  python scandocs.py --dry-run    show what would happen, move nothing
  python scandocs.py --config path\\to\\config.toml

The Bedrock API key is read from the AWS_BEARER_TOKEN_BEDROCK environment
variable. It never goes in config.toml.
"""

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import pypdfium2 as pdfium

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))  # works when frozen by PyInstaller
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

NONE = "NONE"
BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

INSTRUCTIONS = """You name scanned documents for a personal injury and workers' compensation law firm.

You will see the first pages of one scanned PDF. Decide which firm client the document is about,
and write a short description of the document.

Who the client is:
- The client is the firm's own client: the injured worker, claimant, plaintiff, patient,
  employee, or petitioner the firm represents.
- Never pick an insurer, adjuster, employer, doctor, opposing party, the other driver,
  or anyone at the law firm.
- The name may appear as "Claimant", "Employee", "Injured", "Patient", "Your Client",
  "RE:", "Member", or "In the Matter of".

Picking the client:
- The client MUST be copied exactly, character for character, from the CLIENT LIST below.
- Spelling, hyphens, accents, and the order of double surnames may differ between the
  document and the list. Match on the person, then copy the list's spelling.
- If the document names several people, pick the one who is on the client list. If more
  than one is on the list, pick the one the document is mainly about.
- If the firm's client is clearly named but is NOT on the list (a new client), set client
  to NONE and put their name in new_client, written "LAST, First": surname(s) in capitals
  exactly as the document spells them (keep both surnames and any hyphen), first name in
  normal case, no middle names or initials. Example: "Maria J. Garcia Lopez" becomes
  "GARCIA LOPEZ, Maria".
- If the pages shown have no client name (for example a fax cover sheet), or you cannot
  tell which person is the firm's client, set client to NONE and new_client to "".
  Do not guess.

The description:
- 3 to 8 words, Title Case, plain English.
- Say who it is from (when useful) and what it is, for example:
  "Notice of Hearing 11-24-2025", "Travelers Denial of Transfer of Care and D-12a",
  "MRO Invoice for UMC Records", "Letter of Representation to USAA",
  "Balance Verification Request Las Vegas Pharmacy".
- Include a date only when it is the key date of the document (a hearing date, an
  appointment date). Write dates as MM-DD-YYYY.
- Do not include the client's name. Do not use the characters < > : " / \\ | ? *

The office's own NAMING RULES and PAST CORRECTIONS follow. They come from the people who
check your work, so they override the general guidance above.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "client": {
            "type": "string",
            "description": "An exact line from the CLIENT LIST, or NONE",
        },
        "new_client": {
            "type": "string",
            "description": "Only when client is NONE: the firm client's name as LAST, First if clearly shown, else empty",
        },
        "description": {
            "type": "string",
            "description": "3 to 8 word description of the document",
        },
        "reason": {
            "type": "string",
            "description": "One short sentence: where on the page the client name was found, or why NONE",
        },
    },
    "required": ["client", "new_client", "description", "reason"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- setup

def load_config(path):
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    base = Path(path).resolve().parent
    cfg.setdefault("rules_file", "naming_rules.txt")
    cfg.setdefault("corrections_file", "corrections.csv")
    for key in ("scan_folder", "named_folder", "review_folder", "client_list", "log_file",
                "rules_file", "corrections_file"):
        p = Path(os.path.expandvars(cfg[key]))
        cfg[key] = p if p.is_absolute() else base / p
    cfg.setdefault("pages_first_pass", 2)
    cfg.setdefault("pages_max", 4)
    cfg.setdefault("image_long_edge", 1568)
    cfg.setdefault("settle_seconds", 60)
    cfg.setdefault("cache_ttl", "")
    cfg.setdefault("max_corrections_in_prompt", 150)
    return cfg


def load_clients(path):
    """The list may start empty. It grows as staff approve new clients."""
    if not Path(path).exists():
        Path(path).write_text('# One client per line, "LAST, First". Added to automatically.\n', encoding="utf-8")
    clients = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            clients.append(line)
    return clients


def add_clients(path, names):
    """Append approved new clients to the list (skips ones already there). Returns those added."""
    existing = {c.casefold() for c in load_clients(path)}
    added = []
    for n in names:
        n = re.sub(r"\s+", " ", n).strip()
        if n and "," in n and n.casefold() not in existing:
            existing.add(n.casefold())
            added.append(n)
    if added:
        text = Path(path).read_text(encoding="utf-8-sig")
        with open(path, "a", encoding="utf-8") as f:
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write("\n".join(added) + "\n")
    return added


def _letters(x):
    import unicodedata
    x = unicodedata.normalize("NFKD", x)
    return re.sub(r"[^a-z]", "", "".join(ch for ch in x if not unicodedata.combining(ch)).casefold())


def _name_parts(n):
    last, _, first = n.partition(",")
    return _letters(last), _letters(first.split()[0] if first.split() else "")


def identical_letters(a, b):
    """Same letters, ignoring case, spaces, hyphens and accents: 'GARCIA LOPEZ' = 'Garcia-López'."""
    return _name_parts(a) == _name_parts(b) and all(_name_parts(a))


def same_person(a, b):
    """
    True when two list names are spelling variants of one person, e.g.
    'GARCIA LOPEZ, Maria' / 'GARCIA-LOPEZ, Maria' or 'NGUYEN, Linh' /
    'NGUYEN TRAN, Linh'. Different first names mean different people.
    """
    (la, fa), (lb, fb) = _name_parts(a), _name_parts(b)
    if not fa or fa != fb:
        return False
    from difflib import SequenceMatcher
    return la in lb or lb in la or SequenceMatcher(None, la, lb).ratio() >= 0.8


def replace_client(path, old, new):
    """Swap one client's spelling in the list, keeping everything else as it is."""
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    have_new = any(l.strip().casefold() == new.casefold() for l in lines)
    out, changed = [], False
    for l in lines:
        if l.strip() == old:
            changed = True
            if not have_new:
                out.append(new)
            continue
        out.append(l)
    if changed:
        Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


def client_from_filename(name):
    """'GARCIA LOPEZ, Maria - Notice of Hearing.pdf' -> 'GARCIA LOPEZ, Maria'"""
    m = re.match(r"^(.+?,\s*.+?)\s+-\s+.+\.pdf$", name, re.IGNORECASE)
    return re.sub(r"\s*\(\d+\)$", "", m.group(1)).strip() if m else None


def make_client(cfg):
    import boto3
    from botocore.config import Config
    if not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        sys.exit("AWS_BEARER_TOKEN_BEDROCK is not set. See README, step 4.")
    return boto3.client(
        "bedrock-runtime",
        region_name=cfg["aws_region"],
        config=Config(retries={"max_attempts": 6, "mode": "adaptive"}, read_timeout=120),
    )


# ---------------------------------------------------------------- learning from staff

def file_hash(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def learn_from_renames(cfg):
    """
    Learns from what staff do in the named folder. Files are recognized by their content
    hash, so renaming does not lose track of them.
      - A proposed new-client file moved to Named unchanged: the client is approved and
        added to the client list.
      - A file renamed by staff (in Named, or fixed in Review and moved to Named): recorded
        in corrections.csv, and the client in the new name is added to the list if missing.
      - If staff only changed the spelling of a listed client's name (added a hyphen, a
        second surname, fixed a typo), that entry in the list is updated, not duplicated.
        If they changed it to a different person, the new person is added and the old
        entry is left alone.
    Returns (corrections_found, clients_added, spellings_updated).
    """
    log = [r for r in read_csv(cfg["log_file"])
           if r.get("sha256") and r.get("result") in ("named", "review", "new client")]
    if not log:
        return 0, [], []
    named_dir = Path(cfg["named_folder"])
    latest = {r["sha256"]: r for r in log}            # last time the script handled each file
    logged_names = {r["new_name"] for r in log}
    new_clients = []
    respelled = []                                     # (old, new)

    # 1. Approvals: proposed new-client files moved to Named as they were.
    for r in log:
        if r["result"] == "new client" and (named_dir / r["new_name"]).exists():
            new_clients.append(r["client"])

    # 2. Renames.
    corrections = {r["sha256"]: r for r in read_csv(cfg["corrections_file"])}
    corrected_names = {c["corrected_name"] for c in corrections.values()}
    seen_path = named_dir / ".scandocs_checked.json"   # so a big folder isn't re-hashed every run
    try:
        seen = json.loads(seen_path.read_text())
    except (OSError, ValueError):
        seen = {}
    found = 0
    for p in named_dir.glob("*.pdf"):
        if p.name in logged_names or p.name in corrected_names:
            continue                                   # untouched, or already learned
        st = p.stat()
        stamp = f"{st.st_size}:{st.st_mtime_ns}"
        if seen.get(p.name) == stamp:
            continue
        seen[p.name] = stamp
        sha = file_hash(p)
        if sha not in latest:
            continue                                   # a file the script never saw
        r = latest[sha]
        if re.sub(r" \(\d+\)(\.pdf)$", r"\1", p.name) == r["new_name"]:
            if r["result"] == "new client":
                new_clients.append(r["client"])            # approved; Windows just added "(2)"
            continue
        claude_named = {"named": r["new_name"], "review": "(sent to review)",
                        "new client": "(new client) " + r["new_name"]}[r["result"]]
        corrections[sha] = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "sha256": sha,
            "original_scan": r["original"],
            "claude_named": claude_named,
            "corrected_name": p.name,
            "what_claude_saw": r.get("reason", ""),
        }
        fixed = client_from_filename(p.name)
        if fixed:
            old = r["client"] if r["result"] == "named" else ""
            if old and fixed != old and same_person(old, fixed):
                respelled.append((old, fixed))
            else:
                new_clients.append(fixed)
        found += 1
    try:
        seen_path.write_text(json.dumps(seen))
    except OSError:
        pass
    if found:
        fields = ["time", "sha256", "original_scan", "claude_named", "corrected_name", "what_claude_saw"]
        with open(cfg["corrections_file"], "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(sorted(corrections.values(), key=lambda c: c["time"]))
    updated = [(o, n) for o, n in respelled if replace_client(cfg["client_list"], o, n)]
    return found, add_clients(cfg["client_list"], new_clients), updated


def build_system_text(cfg, clients):
    parts = [INSTRUCTIONS]
    rules = Path(cfg["rules_file"])
    if rules.exists():
        text = "\n".join(l for l in rules.read_text(encoding="utf-8-sig").splitlines()
                         if l.strip() and not l.lstrip().startswith("#"))
        if text:
            parts.append("NAMING RULES (written by office staff):\n" + text)
    corr = read_csv(cfg["corrections_file"])[-cfg["max_corrections_in_prompt"]:]
    if corr:
        def line(c):
            was, now = c["claude_named"], c["corrected_name"]
            if was == "(sent to review)":
                text = f'- You found no client and sent it to review. Staff named it "{now}".'
            elif was.startswith("(new client) "):
                text = f'- You proposed the new-client name "{was[13:]}". Staff changed it to "{now}".'
            else:
                text = f'- You named it "{was}". Staff renamed it to "{now}".'
            return text + (f' (You had noted: {c["what_claude_saw"]})' if c["what_claude_saw"] else "")
        lines = [line(c) for c in corr]
        parts.append("PAST CORRECTIONS (learn the pattern, both client choice and description wording):\n"
                     + "\n".join(lines))
    parts.append('CLIENT LIST (one client per line, format "LAST, First"):\n'
                 + ("\n".join(clients) if clients else "(empty so far: every client is new)"))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- files

def ready_pdfs(folder, settle_seconds):
    """PDFs that have not changed for settle_seconds (the scanner is done writing)."""
    now = time.time()
    out = []
    for p in sorted(Path(folder).glob("*.pdf")) + sorted(Path(folder).glob("*.PDF")):
        try:
            st = p.stat()
        except OSError:
            continue
        if now - st.st_mtime >= settle_seconds and st.st_size > 0:
            out.append(p)
    return list(dict.fromkeys(out))


def render_pages(pdf_path, first, last, long_edge):
    """Render pages [first, last) as JPEG bytes, scaled so the long edge is long_edge px."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        images = []
        for i in range(first, min(last, len(pdf))):
            page = pdf[i]
            w, h = page.get_size()  # points
            scale = long_edge / max(w, h)
            img = page.render(scale=scale).to_pil().convert("L")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            images.append(buf.getvalue())
        return images, len(pdf)
    finally:
        pdf.close()


def safe_filename(client, description):
    desc = BAD_CHARS.sub(" ", description).strip().rstrip(".")
    desc = re.sub(r"\s+", " ", desc)[:80].strip() or "Document"
    name = re.sub(r"\s+", " ", BAD_CHARS.sub(" ", client)).strip()
    return f"{name} - {desc}.pdf"


def unique_path(folder, filename):
    target = Path(folder) / filename
    n = 2
    while target.exists():
        target = Path(folder) / f"{Path(filename).stem} ({n}).pdf"
        n += 1
    return target


# ---------------------------------------------------------------- Claude

def ask_claude(bedrock, cfg, system_blocks, images, page_note):
    content = [{"image": {"format": "jpeg", "source": {"bytes": b}}} for b in images]
    content.append({"text": f"{page_note} Name this document."})
    resp = bedrock.converse(
        modelId=cfg["model_id"],
        system=system_blocks,
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": 400},
        outputConfig={
            "textFormat": {
                "type": "json_schema",
                "structure": {"jsonSchema": {"schema": json.dumps(SCHEMA), "name": "document_name"}},
            }
        },
    )
    text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
    return json.loads(text), resp.get("usage", {})


class FakeClaude:
    """
    Stand-in for Bedrock, for testing without AI or a key (--fake).
    Answers come from a CSV with columns: file, client, description.
    Like real Claude: a client on the list is matched, a client not on the list is
    proposed as a new client, and a blank client means no name found.
    """
    def __init__(self, csv_path, clients):
        self.answers = {r["file"]: r for r in read_csv(csv_path)}
        self.clients = clients
        self.current = None

    def converse(self, **request):
        a = self.answers.get(self.current, {})
        name = (a.get("client") or "").strip()
        known = match_client(name, self.clients) if name else NONE
        ans = {"client": known, "new_client": name if name and known == NONE else "",
               "description": a.get("description", ""),
               "reason": "Fake answer from the test CSV." if name else "No client name in the fake answers CSV."}
        return {"output": {"message": {"content": [{"text": json.dumps(ans)}]}},
                "usage": {"inputTokens": 0, "outputTokens": 0}}


def match_client(answer, clients):
    """Exact match first, then a forgiving match on case and spacing. Anything else is NONE."""
    if answer in clients:
        return answer
    key = re.sub(r"\s+", " ", answer).strip().casefold()
    for c in clients:
        if re.sub(r"\s+", " ", c).strip().casefold() == key:
            return c
    return NONE


def name_one(bedrock, cfg, system_blocks, clients, pdf_path):
    """Returns (client, new_client, description, reason, pages_read, usage_totals)."""
    usage = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0, "cacheWriteInputTokens": 0}
    step = cfg["pages_first_pass"]
    start = 0
    total_pages = None
    result = {"client": NONE, "new_client": "", "description": "", "reason": ""}
    if isinstance(bedrock, FakeClaude):
        bedrock.current = Path(pdf_path).name
    while True:
        images, total_pages = render_pages(pdf_path, start, start + step, cfg["image_long_edge"])
        if not images:
            break
        note = f"These are pages {start + 1} to {start + len(images)} of {total_pages}."
        result, u = ask_claude(bedrock, cfg, system_blocks, images, note)
        for k in usage:
            usage[k] += u.get(k, 0) or 0
        result["client"] = match_client(result.get("client", NONE), clients)
        new = re.sub(r"\s+", " ", result.get("new_client") or "").strip()
        if result["client"] == NONE and new:
            exact = [c for c in clients if identical_letters(new, c)]
            close = [c for c in clients if same_person(new, c)]
            if len(exact) == 1:
                # On the list after all, just punctuated differently: file it as that client.
                result["client"], new = exact[0], ""
            elif len(close) == 1:
                # Probably an existing client (e.g. one surname instead of two). Propose the
                # list's spelling, but let staff confirm by moving it.
                new = close[0]
                result["reason"] = (result.get("reason", "") + f" Looks like existing client {new}.").strip()
            elif "," not in new:
                new = ""                                 # not in LAST, First form; let staff decide
        result["new_client"] = new
        start += step
        if result["client"] != NONE or new or start >= min(total_pages, cfg["pages_max"]):
            break
    return (result["client"], result["new_client"], result.get("description", ""),
            result.get("reason", ""), min(start, total_pages or 0), usage)


# ---------------------------------------------------------------- main

def write_log(log_file, row):
    new = not Path(log_file).exists()
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def acquire_lock(path, stale_after=1800):
    """Stops two runs from overlapping if Task Scheduler fires while a run is still going."""
    try:
        if path.exists() and time.time() - path.stat().st_mtime > stale_after:
            path.unlink()
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def main():
    ap = argparse.ArgumentParser(description="Name scanned PDFs by client with Claude on Bedrock.")
    ap.add_argument("--config", default=str(APP_DIR / "config.toml"))
    ap.add_argument("--dry-run", action="store_true", help="show proposed names, move nothing")
    ap.add_argument("--fake", action="store_true",
                    help="test without AI: answers come from the fake_answers CSV in the config")
    args = ap.parse_args()

    cfg = load_config(args.config)
    dry = args.dry_run or cfg.get("dry_run", False)
    for key in ("named_folder", "review_folder"):
        cfg[key].mkdir(parents=True, exist_ok=True)

    lock = cfg["scan_folder"] / ".scandocs.lock"
    if not acquire_lock(lock):
        print("Another run is in progress. Exiting.")
        return
    try:
        learned, added, updated = learn_from_renames(cfg)
        if learned:
            print(f"Learned {learned} new correction(s) from staff renames.")
        for name in added:
            print(f"Added new client to the list: {name}")
        for old, new in updated:
            print(f"Updated client spelling on the list: {old}  ->  {new}")
        clients = load_clients(cfg["client_list"])
        pdfs = ready_pdfs(cfg["scan_folder"], 0 if dry else cfg["settle_seconds"])
        if not pdfs:
            print("Nothing to do.")
            return
        cache_point = {"type": "default"}
        if cfg["cache_ttl"]:
            cache_point["ttl"] = cfg["cache_ttl"]
        system_text = build_system_text(cfg, clients)
        system_blocks = [{"text": system_text}, {"cachePoint": cache_point}]
        if args.fake:
            fake_csv = Path(args.config).resolve().parent / cfg.get("fake_answers", "fake_answers.csv")
            bedrock = FakeClaude(fake_csv, clients)
            # Show exactly what real Claude would be told, rules and corrections included.
            prompt_file = Path(args.config).resolve().parent / "last_prompt.txt"
            prompt_file.write_text(system_text, encoding="utf-8")
            rules = Path(cfg["rules_file"])
            n_rules = sum(1 for l in rules.read_text(encoding="utf-8-sig").splitlines()
                          if l.strip() and not l.lstrip().startswith("#")) if rules.exists() else 0
            n_corr = len(read_csv(cfg["corrections_file"])[-cfg["max_corrections_in_prompt"]:])
            print(f"FAKE MODE: no AI is called. Claude's instructions would include {n_rules} rule(s) "
                  f"and {n_corr} correction(s). See {prompt_file.name}.\n")
        else:
            bedrock = make_client(cfg)

        for pdf in pdfs:
            row = {"time": datetime.now().isoformat(timespec="seconds"), "original": pdf.name,
                   "result": "", "new_name": "", "client": "", "description": "", "reason": "",
                   "pages_read": 0, "input": 0, "cache_read": 0, "cache_write": 0, "output": 0,
                   "sha256": ""}
            try:
                row["sha256"] = file_hash(pdf)
                client, new_client, desc, reason, pages, u = name_one(bedrock, cfg, system_blocks, clients, pdf)
                row.update(client=client, description=desc, reason=reason, pages_read=pages,
                           input=u["inputTokens"], cache_read=u["cacheReadInputTokens"],
                           cache_write=u["cacheWriteInputTokens"], output=u["outputTokens"])
                if client == NONE and new_client:
                    # Named already, so staff only have to move it if it looks right.
                    dest = unique_path(cfg["review_folder"], safe_filename(new_client, desc))
                    row["result"], row["client"] = "new client", new_client
                elif client == NONE:
                    dest, row["result"] = unique_path(cfg["review_folder"], pdf.name), "review"
                else:
                    dest, row["result"] = unique_path(cfg["named_folder"], safe_filename(client, desc)), "named"
                row["new_name"] = dest.name
                if dry:
                    row["result"] = "dry-run " + row["result"]   # never learned from
                else:
                    shutil.move(str(pdf), str(dest))
            except Exception as e:  # one bad file must not stop the batch
                row["result"], row["reason"] = "error", f"{type(e).__name__}: {e}"[:300]
                # Network hiccups get retried next run; a file that keeps failing goes to review.
                past = sum(1 for r in read_csv(cfg["log_file"])
                           if r.get("result") == "error" and r.get("sha256") == row["sha256"])
                if past + 1 >= cfg.get("max_errors", 3) and not dry and pdf.exists():
                    dest = unique_path(cfg["review_folder"], pdf.name)
                    shutil.move(str(pdf), str(dest))
                    row["result"], row["new_name"] = "error, sent to review", dest.name
            write_log(cfg["log_file"], row)
            print(f'{row["result"]:7} {pdf.name}  ->  {row["new_name"]}')
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
