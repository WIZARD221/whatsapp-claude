#!/usr/bin/env python3
"""Poll the WhatsApp Mac app's local ChatStorage.sqlite for new messages in the
"Claude" group. Exits (code 0) and prints JSON when a new message that does not
start with the bot marker exists. No network, no model usage.

Usage:
  poll_whatsapp.py --init            mark everything currently in the group as seen
  poll_whatsapp.py                   poll every 10s until new messages appear, print them
  poll_whatsapp.py --once            check once and exit (code 0 new msgs, 3 none)
  poll_whatsapp.py --ack             mark all current messages as seen (after handling)
  poll_whatsapp.py --recent N        print the last N messages (debug)
Exit codes: 0 new messages printed, 2 database unreadable, 3 nothing new (--once).
"""
import argparse, json, os, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reminders import due_reminders

GROUP_NAME = "Claude"
BOT_MARK = "🤖"
HOME = os.path.expanduser("~")
DB = os.path.join(HOME, "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite")
APP_PROC = "WhatsApp.app/Contents/MacOS/WhatsApp"


def app_running():
    """True if the WhatsApp Mac app's main process is alive (the ServiceExtension alone does not sync)."""
    r = subprocess.run(["pgrep", "-f", APP_PROC], capture_output=True, text=True)
    return r.returncode == 0


def ensure_app_running(st, misses):
    """The database only receives messages while the app runs. If the main process is gone on two
    consecutive polls, relaunch it in the background (no focus) and record it in the state."""
    if app_running():
        return 0
    misses += 1
    if misses >= 2:
        subprocess.run(["open", "-g", "-a", "WhatsApp"], capture_output=True)
        st.setdefault("relaunched", []).append(datetime.now().astimezone().isoformat(timespec="seconds"))
        st["relaunched"] = st["relaunched"][-20:]
        save_state(st)
        print(json.dumps({"warn": "whatsapp_relaunched", "at": st["relaunched"][-1]}), file=sys.stderr, flush=True)
        return 0
    return misses
LID_DB = os.path.join(HOME, "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/LID.sqlite")
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "poll_state.json")
CORE_DATA_EPOCH = 978307200  # 2001-01-01 in unix seconds
SYSTEM_TYPES = {6, 10, 12}   # group events / system notices
MEDIA_TYPES = {1, 2, 3, 8, 11, 15}  # fetch with fetch_media.py
CAPTION_TYPES = {1, 2, 11}         # ZWAMEDIAITEM.ZTITLE holds the caption (for documents it is the file name)
TYPE_NAMES = {0: "text", 1: "image", 2: "video", 3: "audio", 4: "contact", 5: "location",
              7: "url", 8: "document", 11: "gif", 14: "deleted", 15: "sticker"}


def connect(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"seen": [], "last_date": 0}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def own_identity(con, spk, st):
    """Every jid that is *me*: the account row in LID.sqlite (Z_PK=1; it has no username, so never
    select it by ZUSERNAME: on 20 Nov 2026 that matched a contact and flagged my own LID as another
    member), the creator of the group, and whatever --init recorded in the state file."""
    me = set(st.get("me", []))
    try:
        lid = connect(LID_DB)
        row = lid.execute("SELECT ZPHONENUMBER, ZIDENTIFIER FROM ZWAZACCOUNT ORDER BY Z_PK LIMIT 1").fetchone()
        lid.close()
        if row:
            if row[0]:
                me.add(f"{row[0]}@s.whatsapp.net")
            if row[1]:
                me.add(row[1])
    except sqlite3.Error:
        pass
    try:
        row = con.execute("SELECT ZCREATORJID FROM ZWAGROUPINFO WHERE ZCHATSESSION=?", (spk,)).fetchone()
        if row and row[0]:
            me.add(row[0])
    except sqlite3.Error:
        pass
    return me


def fetch(con, st):
    sess = con.execute(
        "SELECT Z_PK, ZCONTACTJID FROM ZWACHATSESSION WHERE ZPARTNERNAME=? AND ZSESSIONTYPE=1 AND ZREMOVED=0",
        (GROUP_NAME,)).fetchall()
    if len(sess) != 1:
        raise RuntimeError(f"expected exactly one group named {GROUP_NAME!r}, found {len(sess)}")
    spk, gjid = sess[0]
    me = own_identity(con, spk, st)
    members = con.execute(
        "SELECT ZMEMBERJID FROM ZWAGROUPMEMBER WHERE ZCHATSESSION=? AND ZISACTIVE=1", (spk,)).fetchall()
    global members_active
    members_active = [m[0] for m in members]
    others = [m[0] for m in members if m[0] not in me]
    rows = con.execute("""
        SELECT m.Z_PK, m.ZSTANZAID, m.ZISFROMME, m.ZMESSAGETYPE, m.ZMESSAGEDATE, m.ZFROMJID, m.ZTEXT,
               mi.ZMEDIALOCALPATH, mi.ZMOVIEDURATION, mi.ZFILESIZE, mi.ZTITLE, mi.ZVCARDSTRING
        FROM ZWAMESSAGE m LEFT JOIN ZWAMEDIAITEM mi ON mi.Z_PK = m.ZMEDIAITEM
        WHERE m.ZCHATSESSION=? ORDER BY m.ZMESSAGEDATE ASC""", (spk,)).fetchall()
    msgs = []
    for pk, stanza, fromme, mtype, mdate, fromjid, text, mpath, mdur, msize, mtitle, mmime in rows:
        if mtype in SYSTEM_TYPES or not stanza:
            continue
        ts = (mdate or 0) + CORE_DATA_EPOCH
        msgs.append({
            "pk": pk, "id": stanza, "from_me": bool(fromme), "from_jid": fromjid,
            "type": TYPE_NAMES.get(mtype, f"type{mtype}"), "type_code": mtype,
            "ts": ts, "time": datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds"),
            "text": text or (mtitle if mtype in CAPTION_TYPES else "") or "", "media_path": mpath, "media_seconds": mdur, "media_bytes": msize,
            "media_title": mtitle if mtype in MEDIA_TYPES else None, "media_mime": mmime if mtype in MEDIA_TYPES else None,
        })
    return gjid, others, msgs


def is_task(m):
    return not m["text"].startswith(BOT_MARK)


def has_later_bot_reply(m, msgs):
    """True if a later message starting with '🤖 Re:' quotes this task's first words."""
    head = " ".join(m["text"].split()[:3])
    for o in msgs:
        if o["ts"] > m["ts"] and o["text"].startswith(BOT_MARK + " Re:") and head and head in o["text"]:
            return True
    return False


def new_messages(st, msgs):
    seen = set(st["seen"])
    return [m for m in msgs if m["id"] not in seen and m["ts"] > st.get("last_date", 0) - 86400 and is_task(m)]


def mark_all_seen(st, msgs):
    st["seen"] = [m["id"] for m in msgs][-2000:]
    st["last_date"] = max([m["ts"] for m in msgs] + [st.get("last_date", 0)])
    save_state(st)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--ack", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--recent", type=int, default=0)
    ap.add_argument("--interval", type=float, default=10)
    a = ap.parse_args()

    if not os.path.exists(DB):
        print(json.dumps({"error": "db_missing", "path": DB})); sys.exit(2)
    try:
        con = connect(DB); con.execute("SELECT 1 FROM ZWAMESSAGE LIMIT 1"); con.close()
    except sqlite3.Error as e:
        print(json.dumps({"error": "db_unreadable", "detail": str(e), "path": DB})); sys.exit(2)

    st = load_state()
    misses = 0
    while True:
        if not (a.recent or a.init or a.ack or a.once):
            misses = ensure_app_running(st, misses)
        try:
            con = connect(DB)
            gjid, others, msgs = fetch(con, st)
            con.close()
        except (sqlite3.Error, RuntimeError) as e:
            print(json.dumps({"error": "query_failed", "detail": str(e)})); sys.exit(2)

        if a.recent:
            print(json.dumps(msgs[-a.recent:], ensure_ascii=False, indent=1)); return
        if a.init or a.ack:
            mark_all_seen(st, msgs)
            if a.init and len(members_active) == 1:
                st["me"] = sorted(set(st.get("me", [])) | set(members_active)); save_state(st)
            print(json.dumps({"ok": "ack" if a.ack else "init", "seen": len(st["seen"]), "group": gjid, "other_members": others}))
            return

        new = new_messages(st, msgs)
        due = [] if a.once else due_reminders()
        if due and not new and not others:
            # a reminder is due: hand it to the model (it posts it, then runs `reminders.py fire <id>`)
            print(json.dumps({"group": gjid, "other_members": others, "new": [], "reminders": due}, ensure_ascii=False, indent=1))
            sys.exit(0)
        if new or others:
            for m in new:
                m["already_answered"] = has_later_bot_reply(m, msgs)
            out = {"group": gjid, "other_members": others, "new": new}
            if st.get("relaunched"):
                out["relaunched"] = st["relaunched"][-3:]
            if due:
                out["reminders"] = due
            print(json.dumps(out, ensure_ascii=False, indent=1))
            # remember them so a restart without --ack does not re-deliver the same messages
            st["seen"] = (st["seen"] + [m["id"] for m in new])[-2000:]
            st["last_date"] = max([m["ts"] for m in new] + [st.get("last_date", 0)])
            save_state(st)
            sys.exit(0)
        if a.once:
            sys.exit(3)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
