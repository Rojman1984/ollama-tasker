"""
tasker.workers.providers.fugu
------------------------------
FuguProvider -- Sakana Fugu OpenAI-compat endpoint.
Fugu is registered with Capability.MULTI_AGENT. It internally
orchestrates its own pool and returns a synthesized result.
The harness treats it as an opaque, high-quality, slow worker.
See SDD Section 5.6.4.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from tasker.workers.base import Capability, ProviderType, WorkerManifest
from tasker.workers.providers.openai_provider import OpenAIProvider

_PostFn = Callable[[str, dict, dict], Awaitable[tuple[int, dict]]]
_GetFn = Callable[[str, dict], Awaitable[tuple[int, dict]]]


class FuguProvider(OpenAIProvider):
    """
    Provider for Sakana Fugu via an OpenAI-compatible endpoint.

    Fugu is an opaque multi-agent worker: the harness sends a single task
    and receives a synthesized result. Internally, Fugu runs its own TRINITY
    coordination. The harness never sees the sub-agent calls.

    Differences from plain OpenAIProvider:
    - supports() checks for ProviderType.FUGU and Capability.MULTI_AGENT
    - default base_url points to the Fugu endpoint
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.sakana.ai/v1",
        *,
        _post_fn: _PostFn | None = None,
        _get_fn: _GetFn | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            _post_fn=_post_fn,
            _get_fn=_get_fn,
        )

    def supports(self, worker: WorkerManifest) -> bool:
        return (
            worker.provider == ProviderType.FUGU
            and Capability.MULTI_AGENT in worker.capabilities
        )
