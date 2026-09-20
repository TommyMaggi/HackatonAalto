# Letting judges reach the UI — prepared, not deployed

Written overnight on 20 Sep. Nothing in this file has been run. Every command
below is a decision for the morning, because each one opens the machine to the
outside in a way that is not undone by closing the laptop.

## First, the fact that decides everything

`ui/server.py` has **no authentication**. Every `POST` route — `/api/decision`,
`/api/diagnosis_decision`, `/api/model`, `/api/machine_context`,
`/api/clear_decision_log`, `/api/save_decision_log`, the chat routes — accepts a
request from anyone who can reach the port. Reachable from the internet means:
anyone can accept or overturn diagnoses in the judges' name, switch the model
provider, wipe the decision log, and burn through the API key's quota via
`/api/chat`. The decision log is Deliverable 6; a stranger writing to it during
judging is the one demo failure that cannot be explained away.

So: **if judges need a link, give them the static export (option B).** Expose
the live server (option A) only on a screen you are standing next to, for the
minutes it is being shown, and take it down after.

## What needs the backend, and what does not

| Works as static files (option B) | Needs `ui/server.py` running (option A) |
|---|---|
| Sensor report (`index.html`), reading `semantics.json`, `profiles.json`, `relations.json` | Accept / contest / override on roles |
| Diagnosis page (`diagnosis.html`), including the technical-evidence panel | Accept / question / overturn on a diagnosis |
| Decision log page (`decision_log.html`), read-only | The "why?" question box (calls the model) |
| `dq_report.json` trust indicator | Cockpit channel series (`/api/series`, reads Parquet) |
| | Cockpit chat, hypotheses, unit notes |
| | Model switch (`/api/model`) and the live egress count (`/api/provenance`) |
| | Decision log download / save / clear |

The cockpit (`cockpit.html`) is almost entirely API-driven and does not work as
a static file. The three older pages do, because they `fetch` the JSON
artifacts by relative path.

## Option A — a tunnel to the live server (fastest, no DNS, no auth)

```bash
# terminal 1, in the repository
.venv/bin/python ui/server.py            # binds localhost:8000 only

# terminal 2
brew install cloudflared                 # once
cloudflared tunnel --url http://localhost:8000
```

`cloudflared` prints a random `https://<words>.trycloudflare.com` URL; paste it
to the judges. It lives as long as the process does. Killing it (Ctrl-C) closes
the door. No account, no DNS, no `vucumpra.com` involved.

Before choosing this, know:

- Everything in the right-hand column above is writable by whoever has the URL.
  Anyone who guesses or is forwarded the link can do it too.
- `/api/chat` and `/api/ask` call the configured model. On `google` that spends
  the key's quota; on `local` it spends the laptop's CPU.
- `ui/server.py` binds `localhost` only (`ui/server.py`, `ThreadingHTTPServer`),
  so nothing on the venue Wi-Fi sees the port directly; the tunnel is the only
  way in, and it dies with the `cloudflared` process.
- Snapshot the decision log first: `cp artifacts/decision_log.jsonl
  artifacts/snapshots/before_judging.jsonl` (the "Save" button on the log page
  does the same through `/api/save_decision_log`).

If you do open it, do it for the duration of the demo only, and stop
`cloudflared` before walking away.

## Option B — a static export (safer; needs no server, no model, no network)

Copy the three static pages and the artifacts they read into one folder, and
serve or host that folder. Nothing in it accepts a write.

```bash
cd ~/Hackaton/trustworthy-monitor
out=/tmp/norrin_static && rm -rf "$out" && mkdir -p "$out/ui" "$out/artifacts"
cp ui/index.html ui/diagnosis.html ui/decision_log.html "$out/ui/"
cp -r ui/assets "$out/ui/" 2>/dev/null || true
cp artifacts/semantics.json artifacts/profiles.json artifacts/relations.json \
   artifacts/diagnosis.json artifacts/drift_events.json artifacts/dq_report.json \
   artifacts/decision_log.jsonl "$out/artifacts/"
# check it locally first -- the pages fetch ../artifacts/*.json by relative path
(cd "$out" && python3 -m http.server 8001)   # open http://localhost:8001/ui/
```

To put it on the web, host that folder anywhere static: `netlify deploy --dir
/tmp/norrin_static`, `vercel /tmp/norrin_static`, GitHub Pages from a branch, or
`cloudflared tunnel --url http://localhost:8001` in front of the local
`http.server`, which is read-only by construction. The buttons for accept /
contest / override will show an error when clicked, because there is no API;
say so on the slide, or hide them with one CSS line before exporting:

```bash
# optional: hide the write controls in the export
for f in "$out"/ui/*.html; do
  sed -i '' 's#</head>#<style>.btn-act,.qa-ask-btn{display:none}</style></head>#' "$f"
done
```

(`.btn-act` is the class every accept / contest / override / overturn button
carries today, `.qa-ask-btn` is the question box; re-check with
`grep -o 'class="btn-[^"]*"' ui/*.html | sort -u` before relying on it.)

What the export cannot show: the model switch with the egress count going to
zero (Deliverable 8 performed), the "why?" box, and the cockpit. Those are for
the live demo on the laptop, where the server is only on `localhost`.

## What to say if asked "can we see it live?"

Show the cockpit on the laptop, on `localhost:8000`. Switch the model from
`google` to `local` in the header with the Raw room open beside it, and let the
egress count speak. Then hand out the static link for them to read at their own
pace. That is both halves of Deliverable 8 without exposing a write API.

## Not in scope of this file, on purpose

- Pointing `vucumpra.com` at anything. DNS changes take longer to undo than the
  judging takes.
- Exposing the Ollama port (11434). An unauthenticated model endpoint on a
  public address is somebody else's compute bill.
- Adding authentication to `ui/server.py`. It would take an hour to do badly
  and a day to do well; the static export removes the need for the demo.
