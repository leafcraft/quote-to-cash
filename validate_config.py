#!/usr/bin/env python3
"""validate_config.py — pre-flight checks for a LeafMesh project config.

Run from the project root BEFORE `python main.py`:

    python validate_config.py            # checks configs/config.yaml
    python validate_config.py path/to/other.yaml

Catches, with file/line context where possible:
  1. YAML syntax errors (bad indentation, tabs, missing colons)
  2. can_call / entry_point / wait_for targets that don't exist
  3. conditions referencing yields the calling agent never returns
     (human agents may only use the SDK's human-response meta fields)
  4. yields ↔ prompt contract mismatches on LLM agents — the SDK
     refuses to boot when the prompt's JSON keys have NO overlap with
     the declared yields (the "Hello!" silent-fallback class)
  5. timeout fallback messages that match none of the gate's routes
  6. one wake_up per agent + 5-field cron shape
  7. module reconciliation — a *_agent.py that matches no agent (silent
     dead code), and an external agent with no shaper bound

Exit code 0 = clean, 1 = problems found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install PyYAML")
    sys.exit(2)

HUMAN_META = frozenset({
    "from_agent", "human_data", "human_decision", "human_initiated",
    "human_message", "original_webhook_data", "source_agent", "timestamp",
})
COND_RE = re.compile(r"calling_agent_response\.([A-Za-z_][\w]*)")
CRON_RE = re.compile(r"^\s*\S+\s+\S+\s+\S+\s+\S+\s+\S+\s*$")

problems: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    problems.append(msg)
    print(f"  ✗ {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  ⚠ {msg}")


def load(path: Path) -> dict | None:
    raw = path.read_text(encoding="utf-8")
    for i, line in enumerate(raw.splitlines(), 1):
        if "\t" in line.split("#")[0]:
            err(f"{path}:{i}: TAB character in YAML indentation — use spaces")
    raw = raw.replace("quote-to-cash", "validate-check")
    raw = re.sub(r"\{\{\w+\}\}", "0", raw)
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        loc = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        err(f"{path}: YAML parse failed{loc}: "
            f"{getattr(e, 'problem', e)} — check indentation around that line")
        return None


def is_human(a: dict) -> bool:
    return a.get("agent_type") == "human" or bool(a.get("is_human_powered"))


def cond_fires_for_message(cond: str, message: str) -> bool:
    def atom(expr: str) -> bool:
        m = re.match(r"\s*calling_agent_response\.(\w+)\s*([!=]=)\s*'([^']*)'\s*$", expr)
        if not m:
            return False
        field, op, val = m.groups()
        if field != "human_message":
            return False
        return (message == val) if op == "==" else (message != val)
    return any(all(atom(x) for x in part.split(" and "))
               for part in cond.split(" or "))


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("configs/config.yaml")
    if not target.exists():
        print(f"config not found: {target}")
        return 1

    print(f"Validating {target} ...")
    cfg = load(target)
    if cfg is None:
        return 1
    agents = cfg.get("agents") or {}
    names = set(agents.keys())

    # 2. targets exist
    for n, a in agents.items():
        if not isinstance(a, dict):
            err(f"agent '{n}' is not a mapping — check indentation under it")
            continue
        for cc in a.get("can_call") or []:
            if isinstance(cc, dict) and cc.get("agent") not in names:
                err(f"{n}: can_call → '{cc.get('agent')}' does not exist")
        wf = a.get("wait_for")
        if wf:
            for tok in re.findall(r"[A-Za-z_][\w]*", str(wf)):
                if tok not in names and tok not in ("AND", "OR", "and", "or"):
                    err(f"{n}: wait_for references unknown agent '{tok}'")
    for ep in cfg.get("entry_points") or []:
        if isinstance(ep, dict) and ep.get("target") not in names:
            err(f"entry_point '{ep.get('name')}' → '{ep.get('target')}' does not exist")

    # 3. conditions vs yields / human meta
    for n, a in agents.items():
        if not isinstance(a, dict):
            continue
        yields = set((a.get("yields") or {}).keys())
        human = is_human(a)
        for cc in a.get("can_call") or []:
            if not isinstance(cc, dict) or not cc.get("condition"):
                continue
            for ref in COND_RE.findall(str(cc["condition"])):
                if human and ref not in HUMAN_META:
                    err(f"{n}→{cc.get('agent')}: human gate condition uses "
                        f"'{ref}' — human responses only deliver "
                        f"{sorted(HUMAN_META)[:3]}... (use human_message)")
                elif not human and ref not in yields and ref not in HUMAN_META:
                    err(f"{n}→{cc.get('agent')}: condition uses '{ref}' "
                        f"which is not in {n}'s yields")

    # 4. yields ↔ prompt contract (LLM agents)
    for n, a in agents.items():
        if not isinstance(a, dict) or a.get("agent_type") != "llm":
            continue
        yields = set((a.get("yields") or {}).keys())
        prompt = a.get("prompt") or ""
        if not yields or not prompt:
            continue
        mentioned = {k for k in yields if re.search(rf'["\-\s]{re.escape(k)}["\s]*:', prompt)}
        if not mentioned:
            err(f"{n}: prompt mentions NONE of its {len(yields)} yields keys — "
                f"the SDK will refuse to boot. Add an OUTPUT CONTRACT line "
                f"listing them, e.g.\n      OUTPUT CONTRACT — respond with "
                f"ONLY valid JSON containing exactly these keys:\n      "
                + "{" + ", ".join(f'"{k}": ...' for k in sorted(yields)) + "}")
        elif len(mentioned) < len(yields):
            print(f"  ⚠ {n}: prompt mentions {len(mentioned)}/{len(yields)} "
                  f"yields keys (missing: {sorted(yields - mentioned)[:5]}...) — "
                  f"boots, but enforce_yields retries are likelier")

    # 5. timeout fallbacks route somewhere
    for n, a in agents.items():
        if not isinstance(a, dict) or not is_human(a):
            continue
        edges = [cc for cc in a.get("can_call") or [] if isinstance(cc, dict)]
        fr = a.get("fallback_response") or {}
        msg = str(fr.get("message", ""))
        if not edges or not fr or not msg:
            continue
        if not any(not cc.get("condition")
                   or cond_fires_for_message(str(cc["condition"]), msg)
                   for cc in edges):
            err(f"{n}: timeout fallback message {msg!r} matches no route — "
                f"an unanswered approval would silently kill the flow")

    # 6. cron shape
    for n, a in agents.items():
        if isinstance(a, dict) and a.get("wake_up") \
                and not CRON_RE.match(str(a["wake_up"])):
            err(f"{n}: wake_up {a['wake_up']!r} is not a 5-field cron")

    # 7. Module reconciliation — catch the silent dead-code class: a
    #    `*_agent.py` in ./agency that matches no agent never binds (it's
    #    written but unreachable). And an `external` agent whose intended
    #    shaper lives in _shared/ must be registered in main.py — flag
    #    when neither a top-level module nor a registration is evident.
    agency = target.parent.parent / "agency"
    if agency.is_dir():
        for mod in sorted(agency.glob("*_agent.py")):
            if mod.stem not in names:
                warn(f"agency/{mod.name}: matches no agent in config — it will "
                     f"never bind (dead code). Rename it to a real agent, or "
                     f"remove it.")
        # External agents whose module DOES exist top-level auto-bind; but
        # if an external agent has no top-level module AND main.py has no
        # explicit registration for it, its connector result is returned
        # raw (no shaping). Surface it so it's a choice, not a surprise.
        main_py = (target.parent.parent / "main.py")
        main_src = main_py.read_text(encoding="utf-8") if main_py.exists() else ""
        for n, a in agents.items():
            if not isinstance(a, dict) or a.get("agent_type") != "external":
                continue
            if a.get("framework") == "custom":
                continue  # custom sinks (e.g. audit) register their own way
            has_module = (agency / f"{n}.py").exists()
            registered = f'"{n}"' in main_src or f"'{n}'" in main_src
            if not has_module and not registered:
                warn(f"{n}: external agent with no shaper — connector result is "
                     f"returned raw (unmapped to yields). Add agency/{n}.py "
                     f"(auto-binds) or register a shaper in main.py if you need "
                     f"to shape it.")

    if problems:
        print(f"\n{len(problems)} problem(s) found — fix before running main.py")
        return 1
    suffix = f" ({len(warnings)} warning(s))" if warnings else ""
    print(f"OK — {len(names)} agents, "
          f"{len(cfg.get('entry_points') or [])} entry points, all checks pass{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
