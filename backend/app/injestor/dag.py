from __future__ import annotations


class DagBuilder:
    @staticmethod
    def build() -> dict:
        nodes = [
            {"id": "dataset", "type": "dataset", "upstream": [], "downstream": ["preprocessing"]},
            {"id": "preprocessing", "type": "preprocessing", "upstream": ["dataset"], "downstream": ["model_initialization"]},
            {"id": "model_initialization", "type": "model_initialization", "upstream": ["preprocessing"], "downstream": ["training"]},
            {"id": "training", "type": "training", "upstream": ["model_initialization"], "downstream": ["evaluation"]},
            {"id": "evaluation", "type": "evaluation", "upstream": ["training"], "downstream": ["claim_comparison"]},
            {"id": "claim_comparison", "type": "claim_comparison", "upstream": ["evaluation"], "downstream": []},
        ]
        edges = []
        for node in nodes:
            for target in node["downstream"]:
                edges.append({"source": node["id"], "target": target})
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def validate(graph: dict) -> dict:
        nodes = {node["id"]: node for node in graph.get("nodes", [])}
        for edge in graph.get("edges", []):
            if edge["source"] not in nodes or edge["target"] not in nodes:
                raise ValueError(f"Invalid dependency edge: {edge}")
        seen = set()
        visiting = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"Cycle detected at {node_id}")
            if node_id in seen:
                return
            visiting.add(node_id)
            for target in nodes[node_id].get("downstream", []):
                visit(target)
            visiting.remove(node_id)
            seen.add(node_id)

        for node_id in nodes:
            visit(node_id)
        return {"valid": True, "node_count": len(nodes), "edge_count": len(graph.get("edges", []))}
