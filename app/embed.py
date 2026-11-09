"""Backfill configured semantic vectors after seeding: python -m app.embed."""
from .store import Store
from .elastic_ai import CloudSemanticError


def main():
    try:
        store = Store()
        count = store.embed_catalogue()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, CloudSemanticError) else type(exc).__name__
        raise SystemExit(f"Embedding failed ({detail}). Check Elasticsearch and configured semantic provider availability.") from None
    print(f"Indexed {store.semantic_provider} semantic content for {count} talks. Existing session data preserved.")


if __name__ == "__main__":
    main()
