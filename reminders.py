#!/usr/bin/env python3
"""Reminders for the WhatsApp inbox. State in state/reminders.json.

  reminders.py add "<ISO datetime, e.g. 2026-11-19T10:00>" "<text>" [source message id]
  reminders.py list            open (not yet fired) reminders, soonest first
  reminders.py due             reminders whose time has passed and were not fired yet (JSON)
  reminders.py fire <id>       mark as fired (after posting it in the group)
  reminders.py cancel <id>
The model turns Yair's words ("תזכיר לי מחר ב-10 ...") into the ISO time; this script never parses language.
poll_whatsapp.py calls `due_reminders()` every loop and exits with them under "reminders".
"""
import json, os, sys, uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "state", "reminders.json")


def load():
    if not os.path.exists(PATH):
        return []
    with open(PATH) as f:
        return json.load(f)


def save(items):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def now_local():
    return datetime.now().astimezone()


def parse_when(s):
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpret as local time
    return dt


def due_reminders(items=None):
    items = load() if items is None else items
    now = now_local()
    return [r for r in items if not r.get("fired_at") and not r.get("cancelled_at") and parse_when(r["when"]) <= now]


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    cmd = argv[1]
    items = load()
    if cmd == "add":
        when = parse_when(argv[2]); text = argv[3]; src = argv[4] if len(argv) > 4 else None
        r = {"id": uuid.uuid4().hex[:6], "when": when.isoformat(timespec="minutes"), "text": text,
             "source_id": src, "created_at": now_local().isoformat(timespec="seconds"), "fired_at": None, "cancelled_at": None}
        items.append(r); save(items); print(json.dumps(r, ensure_ascii=False)); return 0
    if cmd == "list":
        open_ = sorted([r for r in items if not r.get("fired_at") and not r.get("cancelled_at")], key=lambda r: r["when"])
        print(json.dumps(open_, ensure_ascii=False, indent=1)); return 0
    if cmd == "due":
        print(json.dumps(due_reminders(items), ensure_ascii=False, indent=1)); return 0
    if cmd in ("fire", "cancel"):
        rid = argv[2]
        for r in items:
            if r["id"] == rid:
                r["fired_at" if cmd == "fire" else "cancelled_at"] = now_local().isoformat(timespec="seconds")
                save(items); print(json.dumps(r, ensure_ascii=False)); return 0
        print(json.dumps({"error": "not_found", "id": rid})); return 1
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
