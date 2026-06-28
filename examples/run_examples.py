#!/usr/bin/env python3
"""Run each example payload end-to-end through this mesh.

Usage:
    cd <this template's project root>
    python examples/run_examples.py                 # all scenarios
    python examples/run_examples.py 01_happy_path   # one scenario
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Make agency/ importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Register the audit connector before SDK start
import agency._shared.audit_logger  # noqa: F401

from leafmesh import LeafMesh, LeafMeshLogger

logger = LeafMeshLogger(__name__)
EXAMPLES_DIR = Path(__file__).parent


async def run_scenario(sdk: LeafMesh, scenario_path: Path) -> None:
    scenario = scenario_path.stem
    payload = json.loads(scenario_path.read_text())
    entry_point = payload.pop("_entry_point", "manual_action")
    description = payload.pop("_description", "")
    print()
    print("=" * 78)
    print(f"  SCENARIO: {scenario}")
    print(f"  ENTRY:    {entry_point}")
    if description:
        print(f"  WHAT:     {description}")
    print("=" * 78)
    session_id = f"example-{scenario}"
    try:
        result = await asyncio.wait_for(
            sdk.mesh_call(entry_point, payload, session_id=session_id),
            timeout=120,
        )
        print(f"\n  → result type: {type(result).__name__}")
        try:
            print(f"  → result: {json.dumps(result, indent=2, default=str)[:600]}")
        except Exception:
            print(f"  → result (repr): {repr(result)[:400]}")
    except asyncio.TimeoutError:
        print(f"\n  ✗ TIMED OUT after 120s — the chain may have stalled at HITL.")
        print(f"    Check logs/<audit>.jsonl and any HITL queue for pending requests.")
    except Exception as e:
        print(f"\n  ✗ ERROR: {type(e).__name__}: {e}")


async def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    scenarios = sorted(EXAMPLES_DIR.glob("*.json"))
    if pattern:
        scenarios = [s for s in scenarios if pattern in s.stem]
    if not scenarios:
        print("No scenarios matched.")
        return 1

    sdk = LeafMesh.from_yaml("configs/config.yaml")
    await sdk.start()
    try:
        for scenario_path in scenarios:
            await run_scenario(sdk, scenario_path)
            await asyncio.sleep(2)  # let async chain settle between scenarios
    finally:
        await sdk.stop()
    print()
    print("=" * 78)
    print(f"  Done — ran {len(scenarios)} scenario(s).")
    print("  Audit trail: check logs/*.jsonl for the hash-chained record.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
