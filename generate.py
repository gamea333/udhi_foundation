"""Run Part A for all 5 concepts and save results.json.

Usage:  python generate.py          (all concepts)
        python generate.py 3        (just concept 3, merged into results.json)
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # reads .env locally; on the host the env var is set directly

from concepts import CONCEPTS, get_concept  # noqa: E402
from pipeline import GenerationError, generate_one, get_client  # noqa: E402

RESULTS = Path(__file__).parent / "results.json"


def main():
    ids = [int(a) for a in sys.argv[1:]] or [c["id"] for c in CONCEPTS]
    existing = {r["id"]: r for r in json.loads(RESULTS.read_text())} if RESULTS.exists() else {}
    client = get_client()

    for cid in ids:
        concept = get_concept(cid)
        print(f"\n=== {cid}. {concept['concept']} ===")
        try:
            r = generate_one(concept, client)
        except GenerationError as e:
            print(f"  FAILED: {e}")
            continue
        existing[cid] = r
        for line in r["log"]:
            print("  " + line.replace("\n", "\n  "))
        print(f"  model={r['model']}  in={r['input_tokens']}  out={r['output_tokens']}  "
              f"cost=${r['cost_usd']:.6f}  retries={r['retries']}  api_retries={r['api_retries']}")
        for name, c in r["checks"].items():
            print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {name}: {c['reason']}")

    RESULTS.write_text(json.dumps([existing[k] for k in sorted(existing)], indent=2, ensure_ascii=False))
    print(f"\nSaved {len(existing)} results to {RESULTS.name}")


if __name__ == "__main__":
    main()
