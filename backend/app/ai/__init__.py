"""The AI layer: budget governor, provider adapters, prompts, tools and the
LangGraph graph that wires the three tools together.

Everything a caller outside this package needs is one of:

- `app.ai.budget`  - spend tracking, the hard cap, response caching.
- `app.ai.graph`   - `run_extract` / `run_edit` / `run_assess`, each an
                     explicit-`recursion_limit` LangGraph invocation.
- `app.ai.tools`   - the three tools directly, for callers that don't need
                     the graph's routing (the graph itself is one such
                     caller).

`app.ai.providers` is an internal seam: only `app.ai.tools.*` and
`app.ai.graph` should import it.
"""
