# Owner controls: the lamp and notes

The live wallpaper helper puts a small table lamp in the menu bar with two controls:

- **Light the lamp.** One bit per local day. Once lit, the item reads *The lamp is lit tonight ✓*.
  The renderer lights a window on the boat moored at the end of the pier from dusk on lit days,
  reading the lamp-state file below. The lamp shows on this Mac at once, even when offline.
- **Leave a note…** A short note to one or all of the recipients named in your local config: at most
  500 characters, 12 lines and 3 notes a local day. Notes are informational: they are read as news,
  not as requests. They go with the evening post (22:17 and 23:17 UTC) and are read the next morning;
  one left after 23:17 UTC arrives a morning later, and the panel says so.

Below them, status lines show the last send, how many items are waiting, and the key's expiry or any
trouble with it. Nothing about this changes the wallpaper window, which stays click-through.

## How it works

`tools/listener.py` (standard library only) does all of it; the helper only runs it.

- The helper runs `listener.py --json COMMAND` off its main thread with a 15 s timeout, refreshes the
  menu when it opens, every 15 minutes and at midnight, and sends anything queued 20 s after a wake.
- `tools/nightly.py` runs `listener.py drain` at the start of every run (every 15 minutes while the
  Mac is awake), so anything queued while offline goes out soon after the Mac is back online.
- Each control first writes an item to the outbox (and, for the lamp, the local lamp state), then
  tries to send at once.
- Each item becomes one new file in the private repo (default `edd426/shore`, branch `main`), created
  with the GitHub contents API: `PUT /repos/<repo>/contents/<path>` with
  `{"message", "content": base64, "branch"}` and no `sha`, so it can only create, never overwrite.
  Every request sends `Authorization: Bearer` and `X-GitHub-Api-Version: 2022-11-28`.
  - The lamp: `listener/lamp/<local date>.json`, holding `{"date":"2026-11-02","lit":true}`.
  - A note: `listener/notes/<local date>-<uuid>.json`, holding
    `{"id":"<uuid>","opened":"2026-11-02","text":"…","to":["world-a"]}`. `to` lists recipient keys in
    the config's order.
  - Files are canonical JSON: sorted keys, no spaces, UTF-8, one trailing newline. The outbox keeps
    the exact bytes, so a retry sends the same file.
- **Answers.**
  - 201: sent.
  - 422 means the file already exists. A GET of its raw bytes decides: identical bytes mean an
    earlier attempt landed and its answer was lost (sent); any file at a lamp path means that day is
    lit; different bytes at a note path mean the note can never be sent, so it is moved to
    `listener/rejected/` and reported. Nothing is ever overwritten.
  - Offline, a timeout, 5xx, 409, 429 or a rate-limit 403: the item stays queued for the next drain.
  - 401, 403 or 404, or no key in the Keychain: the item stays queued, the menu shows the error, and
    one notification is sent per episode. The next successful send clears it.
  - Redirects are refused, and plain `http://` is allowed only to this machine (the tests).

## Files

All under `~/Library/Application Support/The Listening Point/`. `tools/install.sh` replaces only
`src/` there, so these survive a reinstall.

| Path | What |
|---|---|
| `listener.json` | Your config (below). Never committed: this repo is public. |
| `listener/lamp.json` | The lamp state, for the renderer (schema below). |
| `listener/outbox/<uuid>.json` | Items waiting to be sent. |
| `listener/rejected/<uuid>.json` | Items the server will never take. Look, then delete by hand. |
| `listener/state.json` | The last send, the last error, the key's expiry, today's note ids (for the cap). |

Folders are mode 0700 and files 0600; every write goes to a temporary file in the same folder and is
renamed into place. The note's text is never logged; the key is never written anywhere.

### Lamp state (read by the renderer)

Path: `~/Library/Application Support/The Listening Point/listener/lamp.json`. From the installed
`tools/nightly.py` that is `os.path.join(HERE, "..", "..", "listener", "lamp.json")`, the same way it
finds `make_h24`.

```json
{"version": 1, "lit": {"2026-11-02": "2026-11-02T19:04:11+01:00"}}
```

- `lit` maps a local date (`YYYY-MM-DD`) to the local time the lamp was lit (ISO 8601 with offset).
  A date is lit if and only if it is a key. Dates older than 60 days are dropped.
- Whether the lamp has been sent is not recorded here: the window shows from the moment it is lit.
- A missing or unreadable file means nothing is lit. Readers should ignore keys they don't know;
  `version` changes only if this shape does.

## Setup (by hand, once)

1. **Make the key.** On github.com: Settings > Developer settings > Personal access tokens >
   Fine-grained tokens > Generate new token.
   - Name: `listening-point-listener`. Expiration: one year.
   - Resource owner: `edd426`. Repository access: *Only select repositories* > `edd426/shore`.
   - Repository permissions: **Contents: Read and write**. Metadata: Read-only is added by itself.
     Nothing else, in particular no Workflows.
   - Generate it and copy it. (Don't use the `gh` CLI's token: its scopes are far broader.)
2. **Store it in the login Keychain.** In Terminal:

   ```sh
   security add-generic-password -U -s listening-point-github -a listener -T /usr/bin/security -w
   ```

   With `-w` last, `security` prompts for the value (twice), so it never reaches shell history. Paste
   the key. `-T /usr/bin/security` lets the helper and the render job read it without a prompt, and
   that survives `tools/install.sh` rebuilding the helper.
3. **Write the config.**

   ```sh
   cp tools/listener.example.json ~/Library/Application\ Support/The\ Listening\ Point/listener.json
   ```

   Then replace the placeholders. Each recipient is `{"key": …, "label": …}`: the key (1-32 of
   `a-z`, `0-9` and `-`, not `all`) is what goes in a note's `to` and must be the name the carrier
   routes on; the label is what the menu shows. With two recipients the picker adds *Both*, with more
   *All*. Optional keys: `repo` (default `edd426/shore`), `branch` (`main`), `api`
   (`https://api.github.com`) and `keychain` (`{"service": …, "account": …}`). Keys starting with `_`
   are comments. Without this file the lamp still works and *Leave a note…* is disabled with a hint.
4. **Install** with `tools/install.sh`, which copies `listener.py` beside the helper and restarts it.
5. **Check** with `tools/listener.py check` (it should say the key can see the repo and when it
   expires), then `tools/listener.py status`.

**Rotating the key.** Make a new one and run the same `security` command (`-U` updates in place). The
menu shows *Key expires in N days* during the last 30 days.

**Revoking it.** Delete the token on GitHub, then
`security delete-generic-password -s listening-point-github -a listener`. A stolen key can only create
files in the private repo, which the carrier checks.

## Commands

```sh
tools/listener.py status                    # the lamp, the queue, the last send, the key, the recipients
tools/listener.py check                     # does the key work? (one GET of the repo)
tools/listener.py light                     # what the menu's Light the lamp does
echo "text" | tools/listener.py note --to all     # or --to <key>, repeatable
tools/listener.py drain                     # send whatever is queued (nightly.py does this)
```

`--json` prints one JSON object (the helper uses it); `--home DIR` and `--api URL` point it elsewhere
(the tests). Exit status: 0 done or queued, 1 refused (nothing stored), 2 stored but not sent,
3 failed.

## The shore on this Mac

The same key also lets this Mac read the shore that the carrier keeps in the private repo's `ledger/`
folder. `tools/shore_sync.py` (standard library and `shorekit/` only) keeps a checked copy, and the
renderer draws from that copy, never from the network.

- **When.** `tools/nightly.py` runs it on every pass once the key is in the Keychain, after the drain and
  under the render lock; it does nothing if it reached the repo less than an hour ago, and after a failed
  try it waits ten minutes. On wake the helper starts the render job when the last try was more than an
  hour ago. `tools/shore_sync.py --force` syncs now.
- **Fetch.** `GET …/contents/ledger/ledger.json` (raw, `If-None-Match`: usually a 304), then each object
  the copy lacks, `ledger/objects/<id>.json`, whose bytes must hash to the sha256 the ledger names.
- **Verify.** The new ledger must extend the copy event for event, and the kit must replay all of it
  against this Mac's own reference set. A ledger that drops or changes a known event, an object that does
  not match, or anything the kit refuses is turned away: the copy is kept, the reason is logged and stored
  in `shore/sync.json`, and one notification is sent for each ledger refused. What the sea takes arrives
  as a new `sea` event, an append like any other.
- **Offline**, or a key or server error: the last good copy stays in use.
- **The lamp.** Any `listener/lamp/<date>.json` in the repo means that day is lit, however it got there
  (the menu, or a file made on GitHub). A lit day missing from `listener/lamp.json` is added, from the
  moment sync saw it (or from noon, for an earlier day), so the window shows from dusk. None is removed.
- **Rendering again.** Sync never renders. Each day folder holds `shore.json`, the ledger (its length and
  sha256) and the lamp time its frames were made with; when they differ, `nightly.py` deletes the frames
  from the first moment the change shows (an object's `lands`, the moment the sea took one) and, for the
  lamp, the minutes from the moment it was lit when the scene's lamps can be on; then it renders them.

| Path (under `~/Library/Application Support/The Listening Point/`) | What |
|---|---|
| `shore/ledger.json`, `shore/objects/<id>.json` | the last good shore, in the kit's layout (`--shore`) |
| `shore/reference/r1/` | this Mac's own reference set: `nightly.py` builds it once with `tools/shore_reference.py` (about a minute) |
| `shore/sync.json` | the last try and the last success (also as `*_unix`, read by the helper), the ETags, the ledger held, any trouble |

`tools/shore_sync.py status` prints `sync.json`. Exit status: 0 done, unchanged or not due; 1 a problem
with the local setup; 2 kept the last good copy (offline, the key, the server, no reference set yet);
3 refused the repo's ledger.

## Text rules

A note is normalised to NFC. Control characters (Unicode Cc, except line breaks), bidirectional
formatting characters and the byte-order mark are removed; tabs become spaces; CR, CRLF, U+2028 and
U+2029 become line breaks; trailing spaces and blank lines at either end are dropped. Then it must be
non-empty, at most 500 characters (code points after NFC, which the panel's counter also counts) and
at most 12 lines. The fourth note of a local day is refused; queued notes count.

## Tests

```sh
/usr/bin/python3 -m unittest tests.test_listener tests.test_shore_sync
```

Offline: a mock of the contents API runs on 127.0.0.1 in a thread, and the Keychain and notifications
are faked by replacing `subprocess.run`, which also records every command line, so the tests show the
key is never on one, in a file or in any output.
