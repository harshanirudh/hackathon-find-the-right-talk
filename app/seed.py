from .store import Store

if __name__ == "__main__":
    try:
        store = Store()
        count = store.seed()
        places = store.seed_places()
        print(f"Elasticsearch ready: {count} talks and {places} venue places indexed.")
    except Exception as exc:
        raise SystemExit(f"Seed failed ({type(exc).__name__}). Check Elasticsearch connectivity and .env configuration.") from None
