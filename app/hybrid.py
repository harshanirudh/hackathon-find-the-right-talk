"""Reciprocal rank fusion in application code; retrieval stays in Elasticsearch."""
from collections import defaultdict


def reciprocal_rank_fusion(keyword_talks, semantic_talks, limit=12):
    scores, talks, methods = defaultdict(float), {}, defaultdict(set)
    for method, results in (("keyword", keyword_talks), ("semantic", semantic_talks)):
        seen = set()
        for rank, talk in enumerate(results, 1):
            identifier = talk["id"]
            if identifier in seen:
                continue
            seen.add(identifier)
            talks[identifier] = {key: value for key, value in talk.items()
                                 if key not in ("embedding", "embedding_model")}
            scores[identifier] += 1 / (60 + rank)
            methods[identifier].add(method)
    ordered = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))[:limit]
    return [{**talks[i], "match_type": "hybrid" if len(methods[i]) == 2 else next(iter(methods[i])),
             "retrieval_score": round(scores[i], 6)} for i in ordered]
