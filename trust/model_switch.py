"""Read and change the active model provider at runtime.

Deliverable 8 asks us to show that the model layer is swappable by configuration
rather than by a rewrite. Until now that meant editing config/llm.yaml by hand
between runs, which is true but invisible to anyone watching a demo.

This module makes the same swap available from the operator UI, and records it.
The rules it enforces:

* Only providers registered in trust.gateway may be selected. The UI cannot
  invent one, and cannot point the pipeline at an arbitrary endpoint.
* API keys are never accepted over the API and never written to disk. The config
  names an environment variable; if that variable is not set, the switch is
  refused with a message saying which one to export. A key posted from a browser
  would end up in a log, a shell history and a screen recording.
* Every switch is written to the decision log as `config_change`, so the egress
  summary and the audit trail stay honest about which model answered when.
* config/llm.yaml is edited in place, line by line. The file is committed and
  carries the reasoning behind every setting; dumping the parsed YAML back would
  throw all of that away on the first click.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "config" / "llm.yaml"

# Providers that never send anything off the machine. Shown to the operator as
# the safe choice, because for this challenge it is the scoring one too.
NO_EGRESS = {"local", "stub"}

# Sensible defaults per provider, so the UI offers a working choice rather than
# an empty form. Whatever config/llm.yaml already says for the active provider
# wins over these. A registered provider with no preset here (eu_hosted) cannot
# be chosen from the UI: it needs an endpoint and a model typed into the config
# first, and the UI must not invent either.
PRESETS: dict[str, dict[str, Any]] = {
    "local": {"model": "llama3.1:8b", "endpoint": "http://localhost:11434",
              "api_key_env": None},
    "stub": {"model": "none", "endpoint": "", "api_key_env": None},
    # gemini-2.0-flash was retired by Google (calls 404). This is the model the
    # config settled on after testing; see the comments in config/llm.yaml.
    "google": {"model": "gemini-flash-lite-latest",
               "endpoint": "https://generativelanguage.googleapis.com/v1beta",
               "api_key_env": "GEMINI_API_KEY"},
    "anthropic": {"model": "claude-sonnet-4-5", "endpoint": "https://api.anthropic.com/v1",
                  "api_key_env": "ANTHROPIC_API_KEY"},
    "openai": {"model": "gpt-4o-mini", "endpoint": "https://api.openai.com/v1",
               "api_key_env": "OPENAI_API_KEY"},
}

# How long to wait for the local server before calling it "not running". A
# status call runs on every cockpit load, so this stays short.
_LOCAL_PROBE_TIMEOUT_S = 1.0


def _load() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _registered() -> list[str]:
    from trust.gateway import _PROVIDERS
    return sorted(_PROVIDERS)


def _local_server_answers(endpoint: str) -> tuple[bool, str | None]:
    """Is anything Ollama-shaped listening? Reads the model list, sends nothing."""
    import urllib.error
    import urllib.request

    url = f"{endpoint.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=_LOCAL_PROBE_TIMEOUT_S) as resp:
            resp.read(1)
        return True, None
    except urllib.error.URLError as exc:
        return False, f"nothing answers at {endpoint} ({exc.reason}); start it with: ollama serve"
    except OSError as exc:
        return False, f"nothing answers at {endpoint} ({exc}); start it with: ollama serve"


def _readiness(name: str, preset: dict[str, Any], active: dict[str, Any]) -> tuple[bool, str | None]:
    if not preset:
        return False, (f"{name} has no preset: set endpoint, model and api_key_env for it "
                       f"in config/llm.yaml by hand")
    key_var = preset.get("api_key_env")
    if key_var and not os.environ.get(key_var):
        return False, f"export {key_var} in the shell that runs the server"
    if name == "local":
        endpoint = (active.get("endpoint") if active.get("provider") == "local" else None) \
            or preset["endpoint"]
        return _local_server_answers(endpoint)
    return True, None


def status() -> dict[str, Any]:
    """What is active now, and what could be chosen, with each one's readiness."""
    cfg = _load()
    llm = cfg.get("llm", {})
    options = []
    for name in _registered():
        preset = PRESETS.get(name, {})
        ready, reason = _readiness(name, preset, llm)
        # The active provider is described by the config, not the preset: that
        # is the model actually answering.
        model = llm.get("model") if llm.get("provider") == name else preset.get("model")
        options.append({
            "provider": name,
            "model": model,
            "egress": name not in NO_EGRESS,
            "ready": ready,
            "not_ready_because": reason,
        })
    return {
        "active": {
            "provider": llm.get("provider"),
            "model": llm.get("model"),
            "endpoint": llm.get("endpoint"),
            "egress": llm.get("provider") not in NO_EGRESS,
        },
        "options": options,
        "note": "Switching rewrites the llm block of config/llm.yaml and is logged as "
                "config_change. Keys are read from the environment and never stored here.",
    }


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    # Quote only when YAML would otherwise misread it (empty, or a leading
    # character that starts a flow collection, anchor, comment or quote).
    if text == "" or text[0] in "[]{}&*#?|>!%@`'\"" or text.strip() != text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _edit_llm_block(text: str, updates: dict[str, Any]) -> str:
    """Set keys inside the top-level `llm:` block, touching nothing else.

    A key that exists is rewritten on its own line; one that does not is added
    at the end of the block. Comments, order and every other block survive.
    """
    m = re.search(r"^llm:[ \t]*\n(.*?)(?=^\S|\Z)", text, flags=re.S | re.M)
    if not m:
        raise ValueError("config/llm.yaml has no top-level `llm:` block")
    block = m.group(1)
    for key, value in updates.items():
        line = f"  {key}: {_yaml_scalar(value)}"
        pattern = rf"^  {re.escape(key)}:[^\n]*$"
        if re.search(pattern, block, flags=re.M):
            block = re.sub(pattern, line.replace("\\", "\\\\"), block, count=1, flags=re.M)
        else:
            if not block.endswith("\n"):
                block += "\n"
            block += line + "\n"
    return text[:m.start(1)] + block + text[m.end(1):]


def switch(provider: str, model: str | None = None, log=None,
           by: str = "OP-01") -> dict[str, Any]:
    """Point the pipeline at a different provider. Returns the new status."""
    if provider not in _registered():
        raise ValueError(f"unknown provider {provider!r}; choose one of {_registered()}")

    preset = PRESETS.get(provider)
    if not preset:
        raise ValueError(
            f"{provider} has no preset. Set its endpoint, model and api_key_env in "
            f"config/llm.yaml by hand; the UI will not invent an endpoint."
        )
    key_var = preset.get("api_key_env")
    if key_var and not os.environ.get(key_var):
        raise ValueError(
            f"{provider} needs the {key_var} environment variable. Export it in the "
            f"shell that runs the server and restart it. Keys are deliberately not "
            f"accepted over this API."
        )

    cfg = _load()
    before = dict(cfg.get("llm", {}))
    # Switching back to the provider that is already configured keeps its
    # model: the config was tuned by hand, the preset is only a fallback.
    same_as_before = before.get("provider") == provider
    updates: dict[str, Any] = {
        "provider": provider,
        "model": model or (before.get("model") if same_as_before else None) or preset["model"],
        "endpoint": (before.get("endpoint") if same_as_before else None) or preset["endpoint"],
        "api_key_env": key_var,
    }
    if provider in NO_EGRESS:
        # The client-side pacing exists for hosted free-tier quotas. On a local
        # model it only turns a 52-column S4 into a four-minute wait.
        updates["rate_limit_per_min"] = 0

    text = CONFIG_PATH.read_text(encoding="utf-8")
    new_text = _edit_llm_block(text, updates)
    # Prove the edit parses before it lands. A config that does not parse
    # would take every model call down with it on the next request.
    parsed = yaml.safe_load(new_text)
    if parsed.get("llm", {}).get("provider") != provider:
        raise ValueError("editing config/llm.yaml did not take; file left unchanged")
    CONFIG_PATH.write_text(new_text, encoding="utf-8")
    llm = parsed["llm"]

    if log is not None:
        log.append(
            stage="trust_gateway",
            kind="config_change",
            summary=(f"Model provider switched from {before.get('provider')}/"
                     f"{before.get('model')} to {llm['provider']}/{llm['model']}."),
            actor_type="human",
            actor_name=by,
            override={
                "target": "config/llm.yaml:llm.provider",
                "from": f"{before.get('provider')}/{before.get('model')}",
                "to": f"{llm['provider']}/{llm['model']}",
                "rationale": ("Operator changed the model layer from the cockpit. "
                              "Egress " + ("enabled" if provider not in NO_EGRESS
                                           else "disabled") + " from this point."),
            },
        )
    return status()
