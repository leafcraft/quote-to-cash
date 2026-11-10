"""quote-to-cash — Quote-to-Cash Pod (LeafMesh).

Boot order matters (SDK 2.4.131):
  1. import agency.tools  -> the @global_tool decorators run BEFORE from_store/
     start, so Cass's price/history/competitor tools and billing's
     read/claim tools are registered.
  2. LeafMesh.from_store() -> auto_discover wires agency/*_agent.py to YAML.
  3. audit_logger.register(...) -> attach the WORM sink to the custom external
     qtc_audit_logger_agent (after from_store, before start).
  4. leafmesh.start().
"""
import asyncio
import signal
import sys

from dotenv import load_dotenv
from leafmesh import EventType, LeafMesh, LeafMeshLogger

import agency.tools  # noqa: F401 — registers @global_tool tools before start()
from agency._shared import audit_logger as _audit_logger

load_dotenv()
logger = LeafMeshLogger(__name__)
leafmesh = LeafMesh.from_store()

# Register the WORM audit sink as the intelligence function for the
# custom external qtc_audit_logger_agent (SDK 2.4+ API).
_audit_logger.register(leafmesh, "qtc_audit_logger_agent")


async def _on_agent_error(e): logger.warning(f"[qtc-audit] AGENT_ERROR {e.session_id}")
async def _on_manager_intervention(e): logger.warning(f"[qtc-ops] MANAGER_INT {e.session_id}")
async def _on_intervention_needed(e): logger.error(f"[qtc-ops] INT_NEEDED {e.session_id}")
async def _on_human_input_timeout(e): logger.warning(f"[qtc-audit] HITL TIMEOUT {e.session_id}")


async def main():
    await leafmesh.start()
    leafmesh.event_bus.subscribe(EventType.AGENT_ERROR, _on_agent_error)
    leafmesh.event_bus.subscribe(EventType.MANAGER_INTERVENTION, _on_manager_intervention)
    leafmesh.event_bus.subscribe(EventType.INTERVENTION_NEEDED, _on_intervention_needed)
    leafmesh.event_bus.subscribe(EventType.HUMAN_INPUT_TIMEOUT, _on_human_input_timeout)
    # Self-healing is automatic — the SDK enables it during start() on
    # every operator-facing mesh. No call is needed.
    logger.info("quote-to-cash — Quote to Cash mesh running")

    stop = asyncio.Event(); loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
    else:
        try: await stop.wait()
        except KeyboardInterrupt: pass
    await leafmesh.stop()


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
