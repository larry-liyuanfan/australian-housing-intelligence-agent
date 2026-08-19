from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)


def main() -> None:
    parser = argparse.ArgumentParser(prog="housing-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the FastAPI service")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080)
    evaluate = sub.add_parser("evaluate", help="Run the deterministic 100-task evaluation")
    evaluate.add_argument("--output", type=Path, default=Path("artifacts/eval"))
    live = sub.add_parser("evaluate-live", help="Run live Model Studio tool-planning evaluation")
    live.add_argument("--tasks", type=Path, default=Path("eval/reviewed_tasks.jsonl"))
    live.add_argument("--output", type=Path, default=Path("artifacts/live_eval"))
    live.add_argument("--env-file", type=Path, default=Path(".env"))
    seed = sub.add_parser("seed-fixture-index", help="seed deidentified fixtures into Elasticsearch")
    seed.add_argument("--mapping-dir", type=Path, default=Path("deploy/elasticsearch"))
    seed.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("housing_agent.api:app", host=args.host, port=args.port)
    elif args.command == "evaluate":
        from .evaluation import run_evaluation
        print(json.dumps(run_evaluation(args.output), ensure_ascii=False, indent=2))
    elif args.command == "evaluate-live":
        _load_env_file(args.env_file)
        from .live_evaluation import run_live_evaluation
        print(json.dumps(run_live_evaluation(args.output, args.tasks), ensure_ascii=False, indent=2))
    else:
        _load_env_file(args.env_file)
        from .config import Settings
        from .fixture_index import seed_fixture_indices
        print(json.dumps(seed_fixture_indices(Settings.from_env(), args.mapping_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
