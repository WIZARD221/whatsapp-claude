#!/usr/bin/env python3
"""Fetch a media attachment (voice note, image, video, document, sticker) of a message in the
WhatsApp Mac app's ChatStorage.sqlite. Uses the local copy when the app kept one, otherwise
downloads the encrypted blob from WhatsApp's CDN and decrypts it with the key in the database.
Usage: .venv/bin/python fetch_media.py <message stanza id> [out_dir]
Prints JSON: {"path", "type", "mime", "title", "caption", "bytes"}.
"""
import hashlib, hmac, json, mimetypes, os, re, sqlite3, sys, urllib.request
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DB = os.path.expanduser("~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite")
INFO = {1: b"WhatsApp Image Keys", 2: b"WhatsApp Video Keys", 3: b"WhatsApp Audio Keys",
        8: b"WhatsApp Document Keys", 11: b"WhatsApp Video Keys", 15: b"WhatsApp Image Keys"}
TYPE = {1: "image", 2: "video", 3: "audio", 8: "document", 11: "gif", 15: "sticker"}
DEFAULT_EXT = {1: "jpg", 2: "mp4", 3: "opus", 8: "bin", 11: "mp4", 15: "webp"}
HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_INBOX = os.path.join(HERE, "state", "bridge", "inbox.db")


def from_bridge(stanza):
    """Optional second backend: if a local mirror inbox exists at state/bridge/inbox.db (written by a
    separate, private component that is not part of this repo), the file is already on disk in
    state/audio or state/media. Same JSON as the Mac-app path below. Absent on a normal install."""
    if not os.path.exists(BRIDGE_INBOX):
        return None
    try:
        con = sqlite3.connect(f"file:{BRIDGE_INBOX}?mode=ro", uri=True)
        row = con.execute("SELECT type, text, media_path, media_mime, media_title FROM messages WHERE id=?",
                          (stanza,)).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not row or not row[2] or not os.path.exists(row[2]):
        return None
    kind, text, path, mime, title = row
    return {"path": path, "type": kind, "mime": mime, "title": title, "caption": text or "",
            "bytes": os.path.getsize(path)}


def hkdf_expand(key, length, info):
    prk = hmac.new(b"\0" * 32, key, hashlib.sha256).digest()
    okm, t, i = b"", b"", 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t; i += 1
    return okm[:length]


def pick_ext(mtype, mime, title, local):
    for cand in (local, title):
        if cand and "." in os.path.basename(cand):
            ext = os.path.basename(cand).rsplit(".", 1)[1].lower()
            if re.fullmatch(r"[a-z0-9]{1,5}", ext):
                return ext
    if mime:
        g = mimetypes.guess_extension(mime.split(";")[0].strip())
        if g:
            return g.lstrip(".")
    return DEFAULT_EXT.get(mtype, "bin")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    stanza = sys.argv[1]
    hit = from_bridge(stanza)
    if hit:
        print(json.dumps(hit, ensure_ascii=False)); return
    if not os.path.exists(DB):
        sys.exit("the WhatsApp Mac app's database is missing")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute("""SELECT m.ZMESSAGETYPE, m.ZTEXT, mi.ZMEDIAURL, mi.ZMEDIAKEY, mi.ZMEDIALOCALPATH,
                                mi.ZTITLE, mi.ZVCARDSTRING, mi.ZFILESIZE
                         FROM ZWAMESSAGE m JOIN ZWAMEDIAITEM mi ON mi.Z_PK=m.ZMEDIAITEM
                         WHERE m.ZSTANZAID=?""", (stanza,)).fetchone()
    con.close()
    if not row:
        sys.exit(f"no media for message {stanza}")
    mtype, text, url, key, local, title, mime, size = row
    kind = TYPE.get(mtype, f"type{mtype}")
    default_dir = os.path.join(HERE, "state", "audio" if mtype == 3 else "media")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else default_dir
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{stanza}.{pick_ext(mtype, mime, title, local)}")

    done = False
    if local:
        src = os.path.join(os.path.dirname(DB), local)
        if os.path.exists(src) and os.path.getsize(src) > 0:
            with open(src, "rb") as f, open(out, "wb") as g:
                g.write(f.read())
            done = True
    if not done:
        if not url or not key:
            sys.exit("media not stored locally and url/key missing in database")
        req = urllib.request.Request(url, headers={"User-Agent": "WhatsApp/2 Mac"})
        enc = urllib.request.urlopen(req, timeout=120).read()
        key = bytes(key)
        if len(key) != 32 and key[:2] == b"\x0a\x20":   # protobuf envelope: field 1 = 32-byte key
            key = key[2:34]
        keys = hkdf_expand(key, 112, INFO.get(mtype, b"WhatsApp Document Keys"))
        iv, cipher_key, mac_key = keys[:16], keys[16:48], keys[48:80]
        body, mac = enc[:-10], enc[-10:]
        if hmac.new(mac_key, iv + body, hashlib.sha256).digest()[:10] != mac:
            sys.exit("MAC check failed: wrong key or corrupt download")
        dec = Cipher(algorithms.AES(cipher_key), modes.CBC(iv)).decryptor()
        plain = dec.update(body) + dec.finalize()
        plain = plain[:-plain[-1]]  # strip PKCS7 padding
        with open(out, "wb") as f:
            f.write(plain)

    print(json.dumps({"path": out, "type": kind, "mime": mime, "title": title,
                      "caption": text or "", "bytes": os.path.getsize(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
