#!/usr/bin/env bash
# Make the local model the default, in one command, on the machine that runs the demo.
#
#   bash tools/setup_ollama.sh          # install, start, pull, smoke-test, switch config
#   bash tools/setup_ollama.sh --run    # ...then re-run S4 and S7 on the existing artifacts
#
# Local is the better end state: nothing leaves the machine (the no-egress bonus)
# and there is no API key to lose. This script only touches config/llm.yaml and,
# with --run, artifacts/semantics.json, artifacts/diagnosis.json and the decision
# log -- after copying the current ones into artifacts/snapshots/.
#
# Written overnight on 20 Sep. It could not be executed then: the shell the
# overnight agent had was a Linux VM without brew, without access to ollama.com
# and with 3 GB of RAM. The gateway's `local` path was verified end to end against
# an Ollama-shaped endpoint instead (52/52 columns answered, egress=false in the
# log), so the only unknown left is the install itself.
set -euo pipefail

cd "$(dirname "$0")/.."
MODEL="${OLLAMA_MODEL:-llama3.1:8b}"
ENDPOINT="${OLLAMA_ENDPOINT:-http://localhost:11434}"
PY=".venv/bin/python"
[ -x "$PY" ] || { echo "no .venv -- run 'make setup' first"; exit 1; }

say() { printf '\n\033[1m→ %s\033[0m\n' "$*"; }

say "1/5 ollama binary"
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install ollama
  else
    # The official installer. It asks for sudo on Linux; on macOS prefer brew.
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi
ollama --version

say "2/5 ollama server on ${ENDPOINT}"
if ! curl -fs "${ENDPOINT}/api/tags" >/dev/null 2>&1; then
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -fs "${ENDPOINT}/api/tags" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fs "${ENDPOINT}/api/tags" >/dev/null 2>&1 || { echo "ollama did not come up; see /tmp/ollama.log"; exit 1; }
fi
echo "server answers"

say "3/5 model ${MODEL} (about 4.9 GB the first time)"
ollama pull "${MODEL}"

say "4/5 smoke test: one structured answer through the same call the gateway makes"
curl -fs "${ENDPOINT}/api/generate" \
  -d "{\"model\":\"${MODEL}\",\"prompt\":\"Reply with JSON: {\\\"ok\\\": true}\",\"stream\":false,\"format\":{\"type\":\"object\",\"properties\":{\"ok\":{\"type\":\"boolean\"}}}}" \
  | "$PY" -c 'import json,sys; r=json.load(sys.stdin); json.loads(r["response"]); print("model answered:", r["response"].strip())'

say "5/5 config/llm.yaml -> local (edited in place, comments kept, logged as config_change)"
"$PY" - "$MODEL" "$ENDPOINT" <<'EOF'
import re, sys
from pathlib import Path
sys.path.insert(0, ".")
from trust.decision_log import DecisionLog

model, endpoint = sys.argv[1], sys.argv[2]
path = Path("config/llm.yaml")
text = path.read_text(encoding="utf-8")

# Find the `llm:` block: from the line `llm:` to the next top-level key.
m = re.search(r"^llm:\n(.*?)(?=^\S)", text, flags=re.S | re.M)
if not m:
    sys.exit("could not find the llm: block in config/llm.yaml")
block = m.group(1)
before = dict(re.findall(r"^  (provider|model): (\S+)", block, flags=re.M))

def set_key(block, key, value):
    pattern = rf"^(  {key}:)[^\n]*$"
    if re.search(pattern, block, flags=re.M):
        return re.sub(pattern, rf"\1 {value}", block, count=1, flags=re.M)
    return block + f"  {key}: {value}\n"

block = set_key(block, "provider", "local")
block = set_key(block, "model", model)
block = set_key(block, "endpoint", endpoint)
block = set_key(block, "api_key_env", "null")
# The free-tier pacing (15 calls/min) is for hosted quotas; on a local model it
# only turns a 52-column S4 into a four-minute wait.
block = set_key(block, "rate_limit_per_min", "0")
text = text[:m.start(1)] + block + text[m.end(1):]
path.write_text(text, encoding="utf-8")

DecisionLog("artifacts/decision_log.jsonl").append(
    stage="trust_gateway", kind="config_change", actor_type="human", actor_name="OP-01",
    summary=(f"Model provider switched from {before.get('provider')}/{before.get('model')} "
             f"to local/{model} by tools/setup_ollama.sh. Egress disabled from this point."),
    override={"target": "config/llm.yaml:llm.provider",
              "from": f"{before.get('provider')}/{before.get('model')}", "to": f"local/{model}",
              "rationale": "Local model installed; nothing needs to leave the machine any more."},
)
print(f"llm.provider: {before.get('provider')} -> local, llm.model: {before.get('model')} -> {model}")
EOF
grep -n "^  provider:\|^  model:\|^  endpoint:" config/llm.yaml | head -3

if [ "${1:-}" != "--run" ]; then
  cat <<EOF

Done. Nothing was re-run. To regenerate the roles and the narrative with the
local model (52 calls, a few minutes on Apple silicon):

  mkdir -p artifacts/snapshots && cp artifacts/semantics.json artifacts/diagnosis.json artifacts/snapshots/ 2>/dev/null
  $PY pipeline/s4_semantics.py
  $PY pipeline/s7_diagnosis.py --drift artifacts/drift_events.json --semantics artifacts/semantics.json --out artifacts/diagnosis.json
  make check

or run this script again with --run to do exactly that.
EOF
  exit 0
fi

say "re-running S4 and S7 with the local model (previous artifacts copied to artifacts/snapshots/)"
mkdir -p artifacts/snapshots
stamp=$(date +%Y%m%d_%H%M%S)
for f in semantics.json diagnosis.json; do
  [ -f "artifacts/$f" ] && cp "artifacts/$f" "artifacts/snapshots/${f%.json}_${stamp}.json"
done
"$PY" pipeline/s4_semantics.py
"$PY" pipeline/s7_diagnosis.py --drift artifacts/drift_events.json --semantics artifacts/semantics.json --out artifacts/diagnosis.json
"$PY" - <<'EOF'
import json, collections
d = json.load(open("artifacts/semantics.json"))
cols = {k: v for k, v in d.items() if k.startswith("col_")}
roles = collections.Counter(v["inferred_role"] for v in cols.values())
conf = collections.Counter(v["confidence"] for v in cols.values())
print(f"\n{len(roles)} distinct roles over {len(cols)} columns; confidences {dict(conf)}; degraded={d.get('degraded')}")
if len(roles) <= 2:
    print("WARNING: roles look degenerate -- check the model output before showing this.")
EOF
make check
