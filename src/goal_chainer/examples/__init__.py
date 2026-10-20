"""Purpose: hold example host adapters, each of which a caller selects by importing it; no other GoalChainer module imports one.

A host adapter is the host's side of a reviewed proposal: it prepares what the proposal's action
would release from a record the caller supplies, checks it, and keeps the host's authorization and
receipt apart from the review. The generic request, review and planning modules know nothing of any
adapter here, so a domain's example never becomes part of the core.
"""
