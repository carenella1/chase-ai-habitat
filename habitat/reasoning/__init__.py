from habitat.reasoning.reasoning_chain import (
    start_chain, advance_chain, get_active_chain,
    get_chain_context, should_start_chain, get_recent_conclusions,
)
__all__ = ["start_chain", "advance_chain", "get_active_chain",
           "get_chain_context", "should_start_chain", "get_recent_conclusions"]

from habitat.reasoning.contradiction_engine import (
    check_and_register_contradictions, needs_resolution,
    get_oldest_unresolved, build_resolution_prompt,
    record_resolution, get_contradiction_summary,
)