from collections.abc import Mapping

from .mind_worker import MindClient, ModelTurn
from .scouts import ScoutRunSpec


class ScoutModelRouter:
    """Use the frozen run route for dispatch, matching the persisted run metadata."""

    def __init__(self, clients: Mapping[tuple[str, str], MindClient]) -> None:
        self.clients = dict(clients)

    def run(self, spec: ScoutRunSpec, prompt: str, schema: dict) -> ModelTurn:
        client = self.clients.get((spec.model_provider, spec.model_id))
        if client is None:
            raise ValueError("Scout route is not configured; refusing silent fallback")
        return client.run(spec, prompt, schema)
