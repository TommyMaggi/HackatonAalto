#!/usr/bin/env python3
"""Static scan for the four rules that cost points if broken.

Run it before every commit. It reads source, not data, so it is instant.

    python tools/gate_check.py

Rules, in the order they appear in CONTRACTS.md:
  0. Raw data never leaves       -> no LLM SDK imported outside trust/
  2. Column identity             -> no original column names after S1
  3. Label quarantine            -> no faultNumber/fault_status under pipeline/
  5. No domain terms in prompts  -> no chemistry vocabulary in string literals
  1. Stage isolation             -> no stage imports another stage
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RED, GREEN, YELLOW, DIM, OFF = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"

# Files that are allowed to break a given rule, because that is their job.
EXEMPT = {
    "gate": {"trust/gateway.py", "tools/gate_check.py", "config/llm.yaml"},
    "colnames": {"pipeline/s1_ingest.py", "tools/gate_check.py", "config/llm.yaml"},
    "labels": {"tools/gate_check.py", "config/llm.yaml"},
    "domain": {"tools/gate_check.py"},
}

LLM_SDKS = re.compile(
    r"^\s*(?:import|from)\s+(anthropic|openai|google\.generativeai|google\.genai"
    r"|mistralai|cohere|litellm|ollama|transformers)\b",
    re.MULTILINE,
)
COLNAMES = re.compile(r"\b(xmeas|xmv)\b", re.IGNORECASE)
LABELS = re.compile(r"\b(faultNumber|fault_status)\b")
DOMAIN = re.compile(
    r"\b(reactor|stripper|condenser|separator|compressor|catalyst|distillation"
    r"|tennessee\s+eastman)\b",
    re.IGNORECASE,
)
STRING_LITERAL = re.compile(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'|"[^"\n]*"|\'[^\'\n]*\'')
STAGE_IMPORT = re.compile(r"^\s*(?:import|from)\s+pipeline\.(s[1-7]_\w+)", re.MULTILINE)


class Finding(tuple):
    pass


def scan() -> list[tuple[str, str, int, str]]:
    """Returns (rule, relpath, lineno, detail)."""
    out: list[tuple[str, str, int, str]] = []
    py_files = [p for p in ROOT.rglob("*.py")
                if ".venv" not in p.parts and "__pycache__" not in p.parts]

    for path in py_files:
        rel = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        def lineno(idx: int) -> int:
            return text.count("\n", 0, idx) + 1

        # Rule 0 — the gate
        if rel not in EXEMPT["gate"]:
            for m in LLM_SDKS.finditer(text):
                out.append(("GATE", rel, lineno(m.start()),
                            f"imports {m.group(1)} directly. All model calls go through "
                            f"trust.gateway.call_model()."))

        # Rule 2 — column identity
        if rel not in EXEMPT["colnames"]:
            for m in COLNAMES.finditer(text):
                out.append(("COLNAMES", rel, lineno(m.start()),
                            f"contains original column name {m.group(1)!r}. Use col_NNN."))

        # Rule 3 — label quarantine
        if rel.startswith("pipeline/") and rel not in EXEMPT["labels"]:
            for m in LABELS.finditer(text):
                out.append(("LABELS", rel, lineno(m.start()),
                            f"references {m.group(1)!r} inside pipeline/. Labels live in eval/."))

        # Rule 1 — stage isolation
        if rel.startswith("pipeline/"):
            me = Path(rel).stem
            for m in STAGE_IMPORT.finditer(text):
                if m.group(1) != me:
                    out.append(("ISOLATION", rel, lineno(m.start()),
                                f"imports {m.group(1)}. Stages communicate through "
                                f"artifacts/, never imports."))

        # Rule 5 — no domain vocabulary in string literals
        if rel not in EXEMPT["domain"]:
            for lit in STRING_LITERAL.finditer(text):
                # Docstrings explaining the rules are fine; prompt text is not.
                body = lit.group(0)
                if body.startswith(('"""', "'''")):
                    continue
                for m in DOMAIN.finditer(body):
                    out.append(("DOMAIN", rel, lineno(lit.start()),
                                f"prompt literal contains domain term {m.group(0)!r}. "
                                f"Prompts are generated from profiles, not from what we know."))
    return out


def main() -> int:
    findings = scan()
    if not findings:
        print(f"{GREEN}gate check passed{OFF}  "
              f"{DIM}no leaks, no label bleed, no hard-coded domain terms{OFF}")
        return 0

    by_rule: dict[str, list] = {}
    for rule, rel, line, detail in findings:
        by_rule.setdefault(rule, []).append((rel, line, detail))

    explain = {
        "GATE": "Raw data must never leave. This is the challenge's pass/fail condition.",
        "COLNAMES": "Original names after S1 break portability to the second dataset.",
        "LABELS": "Fault labels are for evaluation only. Using them in detection is cheating.",
        "ISOLATION": "Stage imports couple modules and break parallel work.",
        "DOMAIN": "Hand-fed domain knowledge forfeits the autonomy criterion.",
    }

    for rule, items in by_rule.items():
        print(f"{RED}{rule}{OFF}  {DIM}{explain.get(rule, '')}{OFF}")
        for rel, line, detail in items:
            print(f"   {rel}:{line}  {detail}")
        print()

    print(f"{RED}{len(findings)} violation(s).{OFF} "
          f"{DIM}Fix them before committing; CI runs this too.{OFF}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
