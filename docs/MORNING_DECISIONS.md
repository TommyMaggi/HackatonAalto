# Morning decisions — overnight run of 20 September 2026

Written as I went, on branch `overnight`. Oldest at the top. The real
repository was touched only by the committed code changes: the dev pipeline
ran in an isolated copy, so the full-run artifacts and `data/features` on this
machine are exactly as you left them (see "Worries").

**First thing:** the nine commits are local. `git push` failed from the VM (no
GitHub credentials there). From your terminal:

```bash
cd ~/Hackaton/trustworthy-monitor && git push origin overnight
```

## Environment I actually had

The shell I was given runs in a Linux VM (aarch64, 3 GB RAM, Python 3.10) with
the repository mounted, not in macOS. Consequences:

- Your `.venv` (Homebrew Python 3.12) is not executable from there. I built a
  Linux venv outside the repository with the same packages as `make setup` and
  ran everything with it. Your `.venv` was not changed.
- `brew` and `ollama` are unreachable, the VM cannot download from `ollama.com`,
  and 3 GB of RAM cannot hold `llama3.1:8b`. Ollama was **not** installed.
- The macOS Terminal is granted to me click-only (no keyboard).
- The VM cannot push to GitHub (no credentials). Commits are local.

## What I did (one line each, in commit order)

- `eee1e93b` item 2 — S4 and S7 fail loudly: `"degraded": true` in the
  artifact, a `config_change` log entry, exit 3; orchestrator continues past
  exit 3 but ends with a DEGRADED banner and exit 3. Stub exits 0; `--no-model`
  is not degraded. Schemas widened for the optional field.
- `da52443c` item 3 prepared — `tools/setup_ollama.sh` (below). Gateway `local`
  path proven against an Ollama-shaped fake: 52/52 columns from the "model",
  4 distinct roles, mixed confidences, `egress: false` on every call, S7
  narrative present, all artifacts valid, `--run` path dry-run end to end.
- `f417962c` item 4 — model selector in the cockpit header with the
  leaves/stays chip; not-ready options disabled with the reason. Also fixed in
  `trust/model_switch.py`: `local` now probes 11434 instead of claiming ready,
  `eu_hosted` (no preset) is refused instead of writing an empty config, the
  google preset no longer names the retired `gemini-2.0-flash`, and switching
  edits the five `llm.*` lines in place instead of dumping YAML and losing every
  comment. Verified over HTTP.
- `6f4166bd` item 5 — `artifacts/from_team/` deleted and untracked,
  `online_retail_II.csv.zip` untracked (left on disk), `.gitignore` confirmed,
  no lock files. History untouched.
- `39569e26` item 6 — S5/rule path: an unresolved rule (or one with no number)
  is `NEEDS_OPERATOR_INPUT`, not a RULE_VIOLATION that degrades the verdict;
  a rule whose executable raises is `NOT_EVALUATED`; stable rule ids; S5 exits
  1 when the batch is missing instead of returning 0; the stray copy of
  `dq_report.json` written into `contracts/` is gone; the `eval/` tests pointed
  at a schema path that no longer exists (4 of 6 failed before, 6 of 6 pass now).
- `446303d0` item 6 — dead `from_team` fallbacks removed from the UI readers;
  two `except Exception: pass` in accept/contest now print what failed.
- `1da665e3` item 7 — README rewritten for a judge, with the 14.8 % / 4.9 %
  numbers and what is not done.
- `e1df942f` — `docs/DEPLOY.md`: tunnel vs static export, which features need
  the backend, the no-auth risk stated first.
- `539610e5` — `make run` pointed at a module that does not exist; the server
  banner printed `/ui_v2/` URLs that 404. Both fixed.
- Confirmed a fresh clone works: `git clone` → `make setup` → `make check`
  green → `ui/server.py` serves all four pages and the APIs on the example
  artifacts.

## What broke and how I fixed it

- S4 with `provider: google` and no `GEMINI_API_KEY` died with a traceback
  (`ValueError` is not an `OSError`) and wrote no `semantics.json`. Now "model
  not usable", same path as an unreachable endpoint, and the run ends loudly.
- `rate_limit_per_min: 15` lives inside the `llm:` block, so switching only
  provider/model/endpoint to local kept the free-tier pacing: a 52-column S4
  took four minutes against a local model. Both the script and the UI switch
  set it to 0 for no-egress providers.
- The S5 verdict on the dev data was DEGRADED partly because of our own rule
  handling (an unresolvable sentence counted as a data violation), not the
  data. Fixed as above; the on-disk full-run `dq_report.json` predates this and
  still shows `RULE_003 … col_051 FAIL` from an older rule set.

## What I did not do, and why

- Install Ollama (item 3): impossible from the VM. Prepared instead — see below.
- Push: no credentials in the VM.
- Re-run S4/S7 on the real artifacts with a real model: no key in my
  environment, and I would not spend yours unasked. The on-disk
  `semantics.json` already has 52 model-answered roles from your Gemini run
  (76 egress calls, 250 KB); it stays as it is.
- A drift-over-time chart on the diagnosis page (roadmap step 4): out of scope
  for the brief; named in the README under "Not done".
- Anything under "ASK BEFORE DOING": no repo created, no DNS, no tunnel, no
  force push, nothing under `data/` touched, no keys, no sudo.

## Decisions waiting for you

### 1. Push the branch

```bash
cd ~/Hackaton/trustworthy-monitor && git push origin overnight
```

### 2. Install Ollama and switch to local (~10 min plus a 4.9 GB pull)

```bash
cd ~/Hackaton/trustworthy-monitor
bash tools/setup_ollama.sh          # install, serve, pull, smoke test, switch config/llm.yaml (logged)
bash tools/setup_ollama.sh --run    # same, then re-run S4 + S7 on the existing artifacts and make check
```

`--run` overwrites `artifacts/semantics.json` and `artifacts/diagnosis.json`
(copies go to `artifacts/snapshots/` first) with roles from the local model,
52 calls, a few minutes on Apple silicon. It touches nothing under `data/` and
none of the drift files. If the install fails the config stays on `google`.
Then `git add config/llm.yaml && git commit`.

If you would rather keep Gemini for the demo: export `GEMINI_API_KEY` in the
shell that runs `ui/server.py`, or the header chip will read "not answering"
and every `/api/chat` call will fail — correctly, but visibly.

### 3. How judges see it — read `docs/DEPLOY.md`

Short version: give them the static export, show the cockpit live only on the
laptop. The server has no authentication.

### 4. Rotate the keys that were shared in chat

Not my call to make and not something I can do; the brief says you will.

### 5. Merge or not

Nothing here was merged into `integrazione`. Nine commits on `overnight`, each
one task, each with `make check` green. Diff it before merging:
`git log --oneline integrazione..overnight` and `git diff integrazione..overnight --stat`.

## Worries

- **`orchestrator.py --mode dev` destroys the full run in this checkout.** S1
  `rmtree`s `data/features` (2.4 GB) and `data/labels`, every stage rewrites
  `artifacts/*.json`, and the eval step rewrites `eval/validation_report.json`
  with two-run numbers (28 % detection, 50 % false alarms — meaningless).
  `artifacts/*.json` is gitignored, so there is no copy in git. The README now
  warns about it. Before anyone runs the pipeline here, copy `artifacts/*.json`,
  `artifacts/decision_log.jsonl` and `eval/validation_report.json` aside, or
  run from a fresh clone. I did not add a guard to the orchestrator because
  deciding what it should refuse is your call.
- **The detection numbers.** 14.8 % overall is explained in the README, but the
  per-fault breakdown shows faults 1, 2 and 6 — textbook-easy for PCA T²/SPE —
  at 6 %, 6 % and 31 %. That is a calibration problem (limits `T2=219.9`,
  `SPE=157.4` fitted on 5,000 samples of one simulation, 16 components), not a
  property of the data. If a judge knows the TE process they will ask. The
  README says so plainly rather than pretending; fixing it is a rerun of S6 on
  the full data, which is hours.
- **The committed `eval/validation_report.json` says S4 put all 52 columns in
  one class.** The on-disk `semantics.json` now has model roles, but the
  validation report was not regenerated after that, and regenerating it means
  the full pipeline. The README describes both states honestly.
- **`compiled_rules_evaluated` gained two statuses** (`NEEDS_OPERATOR_INPUT`,
  `NOT_EVALUATED`). `make validate` passes; no UI reads the field today. If
  Ezequiel's or Giorgio's branches read it, tell them.
- **The eval scripts write to the real decision log.** `eval/test_dq_engine.py`
  and `test_giorgio_integration.py` append S5 entries to
  `artifacts/decision_log.jsonl` when run from the repo root. Pre-existing;
  run them from a copy.
- **The fake model I tested with is not a model.** Everything about the `local`
  path is verified except the one thing that matters at demo time: what
  `llama3.1:8b` actually answers. `setup_ollama.sh --run` prints the number of
  distinct roles and warns if it looks degenerate. Look at that number before
  showing `semantics.json` to anyone.
