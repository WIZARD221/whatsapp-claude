// WhatsApp Web reaction flow for Claude in Chrome (tab must show the Claude group).
// Round trip 1: javascript_tool with STEP A (returns hover coords for the row).
// Round trip 2: browser_batch: hover [900,300] → hover [x,y] → wait 1 → javascript_tool with STEP B.
// Replace ROW_TEXT (a unique substring of the message), EMOJI ('👀' | '⏳' | '✅') and SEARCH
// ('eyes' | 'hourglass' | 'check mark'). Setting a reaction on a message that already has one replaces it.
// The frame scale 1568/window.innerWidth matches the screenshot coordinate frame reported by any screenshot.

// ---- STEP A ----
// const rows=[...document.querySelectorAll('#main [role=row]')];
// const row=rows.find(x=>x.innerText.includes(ROW_TEXT)); if(!row) throw new Error('row not found');
// const b=row.getBoundingClientRect(); const s=1568/window.innerWidth;
// ({x: Math.round((b.x+b.width*0.8)*s), y: Math.round((b.y+b.height/2)*s), visible: b.y>0 && b.y<window.innerHeight})
// (if visible is false, scroll_to the row first)

// ---- STEP B ----
// const sleep=ms=>new Promise(r=>setTimeout(r,ms));
// const h=document.querySelector('#main header')?.innerText.split('\n')[0]; if(h!=='Claude') throw new Error('wrong chat: '+h);
// const rows=[...document.querySelectorAll('#main [role=row]')];
// const row=rows.find(x=>x.innerText.includes(ROW_TEXT));
// const react=row.querySelector('[aria-label="React"]');            // a DIV with role=button, only while hovered
// if(!react) throw new Error('no react control in row');
// react.click(); await sleep(500);
// document.querySelector('[aria-label="React to message"]').click(); await sleep(600);   // the "+" in the quick bar
// const search=document.querySelector('[aria-label="Search reaction"]'); search.focus();
// Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(search, SEARCH);
// search.dispatchEvent(new Event('input',{bubbles:true})); await sleep(800);
// const target=[...document.querySelectorAll('[role=button]')].find(x=>x.getAttribute('aria-label')===EMOJI && x.getBoundingClientRect().width>0);
// if(!target) throw new Error('emoji not found'); target.click(); await sleep(800);
// ({reaction: row.querySelector('button[aria-label*="reaction"]')?.getAttribute('aria-label')||null,   // expect "reaction ✅. View reactions"
//   pickerOpen: !!document.querySelector('[aria-label="Search reaction"]')})                             // expect false

// GUARD (18 Nov 16:50): emoji are <img> in WhatsApp Web, so row.innerText does NOT start with 🤖 for our
// own messages. Detect our own rows with  row.querySelector('img[alt="🤖"]')  and never react on them.
// When the poller re-reports already-handled ids (it was not running when they arrived), the last row is
// ours: skip the fast path and match Yair's rows by their text instead.

// GUARD 2 (19 Nov 2026): scope the own-row check to the message body, `row.querySelector('[data-pre-plain-text] img[alt="🤖"]')`.
// A row of Yair's that quotes one of our messages contains a 🤖 <img> inside the quote block, so the unscoped check
// wrongly treats it as ours. Match voice rows by duration AND time (innerText includes '0:14' and '17:14').
