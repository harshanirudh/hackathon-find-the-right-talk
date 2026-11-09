"""Download only the explicitly listed local demo models into Ollama."""
import json
import sys
from urllib.request import Request, urlopen


def main():
    models = sys.argv[1:] or ["embeddinggemma", "qwen2.5:1.5b"]
    for model in models:
        print(f"Downloading {model}", flush=True)
        request = Request("http://127.0.0.1:11434/api/pull",
                          data=json.dumps({"model": model, "stream": True}).encode(),
                          headers={"Content-Type": "application/json"})
        last = None
        with urlopen(request, timeout=120) as response:
            for line in response:
                event = json.loads(line)
                if event.get("error"):
                    raise SystemExit(event["error"])
                total = event.get("total", 0)
                quarter = min(4, int(4 * event.get("completed", 0) / total)) if total else None
                status = (event.get("status"), event.get("digest"), quarter)
                if status != last:
                    progress = f" {quarter * 25}%" if quarter is not None else ""
                    print(f"{model}: {event.get('status')}{progress}", flush=True)
                    last = status


if __name__ == "__main__":
    main()
