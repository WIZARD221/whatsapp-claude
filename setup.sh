#!/bin/bash
# One-shot setup for the Claude WhatsApp inbox. Idempotent: run it again any time.
# Does every step a machine can do and prints the short list of what still needs a person.
#
#   ./setup.sh                       install, download the model, write permissions, baseline, self-test
#   ./setup.sh --no-voice            same, but skip the 1.5 GB voice model (remembered; --voice turns it back on)
#   ./setup.sh --name Dana           also personalise CLAUDE.md (replaces "Yair")
#   ./setup.sh --check               only report status, change nothing
#
# Needs: macOS, the WhatsApp Mac app installed and linked (the one step that needs your phone).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

NAME="" CHECK=0 VOICE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --check) CHECK=1; shift;;
    --no-voice) VOICE=0; shift;;
    --voice) VOICE=1; shift;;
    *) echo "unknown option $1"; exit 1;;
  esac
done

MODEL_REPO="ivrit-ai/whisper-large-v3-turbo-ct2"
MODEL_DIR="models/ivrit-whisper-large-v3-turbo-ct2"
WA_DIR="$HOME/Library/Group Containers/group.net.whatsapp.WhatsApp.shared"
DB="$WA_DIR/ChatStorage.sqlite"
TODO=()           # things only a person can do
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m•\033[0m %s\n' "$*"; }
todo() { printf '  \033[31m✗\033[0m %s\n' "$1"; TODO+=("$1"); }
run()  { if [ "$CHECK" = 1 ]; then warn "would run: $*"; return 1; else "$@"; fi; }

echo "== 1. Machine"
[ "$(uname)" = Darwin ] || { echo "This only works on macOS (it reads the WhatsApp Mac app's database)."; exit 1; }
ok "macOS $(sw_vers -productVersion), $(uname -m)"

echo "== 2. Apps"
if [ -d /Applications/WhatsApp.app ]; then ok "WhatsApp Mac app installed"
else todo "Install WhatsApp from the Mac App Store, open it and link it to your phone (scan the QR code)."; fi
if [ -d "/Applications/Google Chrome.app" ]; then ok "Google Chrome installed"
else todo "Install Google Chrome (Claude replies through WhatsApp Web in Chrome)."; fi
if [ -d /Applications/Claude.app ]; then ok "Claude desktop app installed"
else todo "Install the Claude desktop app (claude.ai/download) and sign in."; fi

echo "== 3. WhatsApp database"
if [ ! -f "$DB" ]; then
  todo "WhatsApp's database is missing: open WhatsApp on this Mac and link it to your phone, then run ./setup.sh again."
elif ! sqlite3 "file:$DB?mode=ro" "select count(*) from ZWACHATSESSION" >/dev/null 2>&1; then
  todo "The WhatsApp database cannot be read. System Settings → Privacy & Security → Full Disk Access → add the Claude app (and Terminal), then run ./setup.sh again."
else
  ok "database readable (read-only)"
  N=$(sqlite3 "file:$DB?mode=ro" "select count(*) from ZWACHATSESSION where ZPARTNERNAME='Claude' and ZSESSIONTYPE=1" 2>/dev/null || echo 0)
  if [ "${N:-0}" -ge 1 ]; then
    ok "group \"Claude\" exists"
    MEMBERS=$(sqlite3 "file:$DB?mode=ro" "select count(*) from ZWAGROUPMEMBER m join ZWACHATSESSION s on m.ZCHATSESSION=s.Z_PK where s.ZPARTNERNAME='Claude' and s.ZSESSIONTYPE=1 and m.ZISACTIVE=1" 2>/dev/null || echo "?")
    warn "active members in the group (yourself included): ${MEMBERS}. It must be only you."
  else
    todo "Create a WhatsApp group named exactly \"Claude\" with only you in it (on the phone: new group, add one contact, create, then remove them). Post one message in it."
  fi
  if pgrep -f "WhatsApp.app/Contents/MacOS/WhatsApp" >/dev/null; then ok "WhatsApp app is running"
  else warn "WhatsApp app is not running; starting it in the background"; run open -g -a WhatsApp; fi
fi

echo "== 4. Python environment"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  if command -v brew >/dev/null 2>&1; then run brew install uv
  else warn "installing uv (astral.sh)"; run sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'; fi
fi
export PATH="$HOME/.local/bin:$PATH"
if [ -x .venv/bin/python ]; then ok "virtualenv exists ($(.venv/bin/python --version 2>&1))"
else run uv venv --python 3.12 .venv >/dev/null && ok "virtualenv created"; fi
if .venv/bin/python -c "import faster_whisper, av, cryptography, huggingface_hub" 2>/dev/null; then
  ok "python packages present"
else
  warn "installing faster-whisper, av, cryptography, huggingface_hub"
  run uv pip install --python .venv/bin/python -q faster-whisper "av<16" cryptography huggingface_hub && ok "packages installed"
fi

echo "== 5. Whisper model (Hebrew-tuned, ~1.5 GB)"
mkdir -p state
[ "$VOICE" = 0 ] && run touch state/.no_voice
[ "$VOICE" = 1 ] && run rm -f state/.no_voice
if [ -f state/.no_voice ]; then
  warn "voice notes are off (--no-voice); Claude will ask for voice-note tasks as text. ./setup.sh --voice turns them on"
elif [ -f "$MODEL_DIR/model.bin" ]; then ok "model present"
else
  warn "downloading $MODEL_REPO (a few minutes)"
  run .venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL_REPO', local_dir='$MODEL_DIR')" \
    && ok "model downloaded"
fi

echo "== 6. Project state and permissions"
run mkdir -p state/audio state/media .claude
if [ -f .claude/settings.json ]; then
  if grep -q "poll_whatsapp" .claude/settings.json; then ok ".claude/settings.json already allows the inbox commands"
  else warn ".claude/settings.json exists but has no inbox allowlist; add the entries listed in CLAUDE.md (Permissions) to its permissions.allow"; fi
else
  run sh -c 'cat > .claude/settings.json <<EOF
{"permissions": {"allow": [
  "Bash(python3 poll_whatsapp.py*)",
  "Bash(.venv/bin/python fetch_voice.py*)",
  "Bash(.venv/bin/python fetch_media.py*)",
  "Bash(.venv/bin/python transcribe.py*)",
  "Bash(python3 pending.py*)",
  "Bash(python3 reminders.py*)",
  "Bash(./setup.sh*)",
  "Bash(sqlite3 *)",
  "mcp__claude-in-chrome__*"
]}}
EOF'
  [ "$CHECK" = 0 ] && ok "wrote .claude/settings.json (no permission prompts for the inbox commands)"
fi
if [ -n "$NAME" ]; then
  if [ "$CHECK" = 1 ]; then warn "would personalise CLAUDE.md"
  else
    cp CLAUDE.md CLAUDE.md.orig 2>/dev/null
    sed -i '' "s/Yair/$NAME/g" CLAUDE.md
    ok "CLAUDE.md personalised (original kept as CLAUDE.md.orig); read it once and delete rules that are not yours"
  fi
fi
if [ -f "$DB" ] && [ ! -f state/poll_state.json ]; then
  run python3 poll_whatsapp.py --init >/dev/null 2>&1 && ok "poller baselined: old messages in the group will not be re-answered"
elif [ -f state/poll_state.json ]; then ok "poller state exists (kept)"; fi

echo "== 7. Self-test"
if [ "$CHECK" = 1 ]; then warn "skipped (--check)"; fi
if [ "$CHECK" = 0 ] && [ -f "$MODEL_DIR/model.bin" ]; then
  .venv/bin/python - <<'EOF' >state/selftest.wav.log 2>&1 && ok "transcriber loads the model and runs" || warn "transcriber self-test failed, see state/selftest.wav.log"
import wave, struct, subprocess, json, sys, os
p = "state/selftest.wav"
with wave.open(p, "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
out = subprocess.run([".venv/bin/python", "transcribe.py", p], capture_output=True, text=True)
os.remove(p)
json.loads(out.stdout.strip().splitlines()[-1])
EOF
fi
if [ "$CHECK" = 0 ] && [ -f "$DB" ]; then
  python3 poll_whatsapp.py --once >/dev/null 2>&1; rc=$?
  case $rc in 0|3) ok "poller reads the group";; *) warn "poller exit code $rc";; esac
fi

echo
echo "== Still needs a person (cannot be done from a script)"
TODO+=("Sign in to web.whatsapp.com in Chrome (scan the QR code with your phone) and install the \"Claude in Chrome\" extension; the first time Claude opens web.whatsapp.com choose \"Always allow\" for the site. Keep the WhatsApp Mac app running.")
TODO+=("In the Claude app: open this folder in the Code tab, set the session to auto mode, and turn on the connectors you want (Gmail, Calendar, Drive) — each is one OAuth sign-in.")
TODO+=("Keep the Mac awake with the lid open (Claude asks for keep-awake itself when the inbox starts).")
TODO+=("If Claude is not already running the inbox, send this line in the Code tab:   Set up and start the WhatsApp inbox (see CLAUDE.md)")
i=1; for t in "${TODO[@]}"; do echo "  $i. $t"; i=$((i+1)); done
echo
