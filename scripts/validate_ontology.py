import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "data" / "ontology" / "v1"


def load(name):
    return json.loads((ONTOLOGY / name).read_text(encoding="utf-8"))


def validate():
    terms = load("terms.json")
    edges = load("edges.json")
    synonyms = load("synonyms.json")

    codes = [t["code"] for t in terms["terms"]]
    if len(codes) != len(set(codes)):
        raise SystemExit("Duplicate ontology term code")
    code_set = set(codes)

    for edge in edges["edges"]:
        if edge["from"] not in code_set or edge["to"] not in code_set:
            raise SystemExit(f"Unknown edge term: {edge}")
        if edge["relation"] not in {"BROADER","NARROWER","RELATED","PART_OF"}:
            raise SystemExit(f"Unknown relation: {edge}")
        if not 0 < edge["weight"] <= 1:
            raise SystemExit(f"Invalid edge weight: {edge}")

    seen_synonyms = set()
    for synonym in synonyms["synonyms"]:
        if synonym["term"] not in code_set:
            raise SystemExit(f"Unknown synonym term: {synonym}")
        if not 0 < synonym["weight"] <= 1:
            raise SystemExit(f"Invalid synonym weight: {synonym}")
        key = (synonym["term"], synonym["language"], synonym["text"].casefold())
        if key in seen_synonyms:
            raise SystemExit(f"Duplicate synonym: {synonym}")
        seen_synonyms.add(key)

    broader = defaultdict(list)
    for edge in edges["edges"]:
        if edge["relation"] == "BROADER":
            broader[edge["from"]].append(edge["to"])

    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            raise SystemExit(f"BROADER cycle detected at {node}")
        if node in visited:
            return
        visiting.add(node)
        for parent in broader[node]:
            visit(parent)
        visiting.remove(node)
        visited.add(node)

    for code in codes:
        visit(code)

    print(
        f"OK ontology v1: {len(codes)} terms, "
        f"{len(edges['edges'])} edges, {len(synonyms['synonyms'])} synonyms"
    )


if __name__ == "__main__":
    validate()
