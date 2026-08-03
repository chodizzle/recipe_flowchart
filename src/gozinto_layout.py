"""Gozinto node graph -> layered columns via longest-path-from-source leveling."""

from __future__ import annotations


def layer_nodes(nodes: list[dict]) -> list[list[dict]]:
    """Group nodes into columns.

    Layer 0 is every ingredient and every zero-input ("setup") operation. Each
    later layer is 1 + the deepest layer among a node's own `inputs`, so a
    node never renders before anything it depends on.
    """
    by_id = {n["id"]: n for n in nodes}
    depth: dict[str, int] = {}

    def layer_of(node_id: str) -> int:
        if node_id not in depth:
            inputs = by_id[node_id].get("inputs") or []
            depth[node_id] = 0 if not inputs else 1 + max(layer_of(i) for i in inputs)
        return depth[node_id]

    for node in nodes:
        layer_of(node["id"])

    max_layer = max(depth.values(), default=-1)
    layers: list[list[dict]] = [[] for _ in range(max_layer + 1)]
    for node in nodes:
        layers[depth[node["id"]]].append(node)
    return layers
