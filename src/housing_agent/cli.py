from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="housing-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the FastAPI service")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080)
    evaluate = sub.add_parser("evaluate", help="Run the deterministic 100-task evaluation")
    evaluate.add_argument("--output", type=Path, default=Path("artifacts/eval"))
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("housing_agent.api:app", host=args.host, port=args.port)
    else:
        from .evaluation import run_evaluation
        print(json.dumps(run_evaluation(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
