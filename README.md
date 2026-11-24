# A WhatsApp inbox for Claude Code

Post a task in a one-person WhatsApp group, typed or as a voice note. Claude Code on your Mac sees it
within ten seconds, reacts with 👀, does the work with the tools you connected (web, Gmail, Calendar,
Drive, Sheets, your browser) and replies in the same group from your own account, starting with 🤖.
Anything that would reach another person (an email, a calendar invite) is prepared as a draft and waits
for your "yes" in the group.

No server, no API keys, no new app on the phone. Claude Code writes nothing by itself here: the scripts
are in this folder, and the whole product is the spec in `CLAUDE.md`.

## Setup: five steps, one sentence typed to Claude

1. Install what you don't already have: the [Claude desktop app](https://claude.ai/download), the
   [Claude in Chrome](https://claude.ai/chrome) extension, and the WhatsApp Mac app linked to your phone.
   Sign in to [web.whatsapp.com](https://web.whatsapp.com) in Chrome.
2. On your phone, create a WhatsApp group named exactly `Claude` with only you in it
   (new group → add one contact → create → remove them). Post one message in it.
3. Download this folder (the green **Code** button → **Download ZIP**, or `git clone`).
4. In the Claude desktop app open the **Code** tab, choose this folder, set the session to auto mode, and send:

   ```text
   Set up and start the WhatsApp inbox (see CLAUDE.md)
   ```

5. Claude runs the installer (Python environment, packages, the voice model, permissions, a self-test),
   tells you the two or three clicks that remain (allow the extension on web.whatsapp.com, turn on the
   Google connectors you want), and starts the loop. Send yourself a first task from the phone.

The Mac must stay awake with the lid open, and the WhatsApp Mac app must stay open, while the inbox runs.
Send the same sentence again whenever you open a new session.

## What's in here

- `CLAUDE.md` — the product. The spec in plain language, then the operating notes Claude keeps for itself
  (file formats, reply layout, approval flow, pitfalls it hit). Run `./setup.sh --name <your first name>`
  to personalise it, then read it once and delete the rules that are not yours.
- `setup.sh` — idempotent installer. `--check` only reports; `--no-voice` skips the 1.5 GB Hebrew-tuned
  Whisper model (voice notes are then answered with "please type it").
- `poll_whatsapp.py` — watches WhatsApp's local database, read-only, and exits when you post. No model time
  is spent while idle.
- `fetch_media.py`, `fetch_voice.py`, `transcribe.py` — attachments and local transcription.
- `reminders.py`, `pending.py` — reminders, and the approval queue for anything that reaches other people.
- `react_snippet.js` — the reaction mechanics (👀 ⏳ ✅) in WhatsApp Web.

## Privacy and safety

Everything runs on your Mac under your own accounts. The scripts open WhatsApp's database read-only and
only ever read or post in the one group. Replies go through WhatsApp Web in your own Chrome, so there is no
third-party WhatsApp client. Forwarded text, links and screenshots are treated as material for the task,
never as instructions. Emails, invites and anything else that reaches another person are sent only after
you answer yes in the group.

## Changing the language

The voice model is tuned for Hebrew and also handles English. For another language, change `MODEL_REPO`
in `setup.sh` to any CTranslate2 Whisper model on Hugging Face (`Systran/faster-whisper-large-v3` is the
general one) and the model folder name in `transcribe.py`. The reply-format rules in `CLAUDE.md` assume
Hebrew and English; rewrite them in your words.
