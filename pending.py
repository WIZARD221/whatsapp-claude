#!/usr/bin/env python3
"""Pending-approval bookkeeping for actions that need Yair's "yes" in the group
(emails to other people, calendar changes that notify attendees, payments, deletions).
State: state/pending.json. Usage:
  pending.py add <kind> <summary> [json-payload]   -> prints the new id (short)
  pending.py list                                   -> open items, oldest first
  pending.py get <id>
  pending.py done <id> [note]                       -> mark executed
  pending.py cancel <id> [note]                     -> mark cancelled
Items older than 48 h are reported as "stale" by list and should be re-confirmed, not executed.
"""
import json, os, secrets, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "state", "pending.json")
STALE = 48 * 3600


def load():
    try:
        return json.load(open(PATH))
    except FileNotFoundError:
        return []


def save(items):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    json.dump(items, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    items = load()
    now = int(time.time())
    if cmd == "add":
        kind, summary = args[0], args[1]
        payload = json.loads(args[2]) if len(args) > 2 else {}
        it = {"id": secrets.token_hex(2), "kind": kind, "summary": summary, "payload": payload,
              "status": "open", "created": now, "created_iso": time.strftime("%Y-%m-%d %H:%M", time.localtime(now))}
        items.append(it); save(items); print(it["id"])
    elif cmd == "list":
        out = [dict(i, stale=(now - i["created"] > STALE)) for i in items if i["status"] == "open"]
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif cmd == "get":
        print(json.dumps(next(i for i in items if i["id"] == args[0]), ensure_ascii=False, indent=1))
    elif cmd in ("done", "cancel"):
        for i in items:
            if i["id"] == args[0]:
                i["status"] = "executed" if cmd == "done" else "cancelled"
                i["closed"] = now
                if len(args) > 1: i["note"] = args[1]
        save(items); print("ok")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
