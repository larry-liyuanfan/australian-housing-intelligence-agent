from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".txt", ".html", ".json", ".gitignore", ".gitlab-ci.yml"}


def sanitize_text(text: str) -> str:
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(
        r"(?m)^# Team members:.*$",
        "# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.",
        text,
    )
    text = re.sub(
        r"(?m)^\*\*Team 12:\*\*.*$",
        "**Attribution:** COMP90024 Team 12 (member identities removed from this public portfolio copy).  ",
        text,
    )
    text = text.replace(
        "| Member | Student ID | Role label | Main responsibility | Contribution summary |",
        "| Role label | Main responsibility | Contribution summary |",
    ).replace(
        "| --- | --- | --- | --- | --- |",
        "| --- | --- | --- |",
    )
    text = re.sub(
        r"(?m)^\| [^|\n]+ \| \d{6,8} \| ([A-E]) \| ([^|\n]+) \| ([^|\n]+) \|$",
        r"| \1 | \2 | \3 |",
        text,
    )
    text = re.sub(r"(?m)^(\s*only:\s*\n\s*- main\s*\n)(?:\s*- [^\n]+\n)+", r"\1", text)
    text = text.replace('os.getenv("ES_PASSWORD", "elastic")', 'os.getenv("ES_PASSWORD", "")')
    text = text.replace('  ES_PASSWORD: "elastic"\n', "")
    text = text.replace(
        '- {name: ES_PASSWORD, value: elastic}',
        '- {name: ES_PASSWORD, valueFrom: {secretKeyRef: {name: housing-es-credentials, key: password}}}',
    )
    text = text.replace("handle1=password1,handle2=password2", "<HANDLE>=<APP_PASSWORD>")
    text = text.replace("aus.social=token1,mastodon.au=token2", "<INSTANCE>=<TOKEN>")
    return text


def sanitize_notebook(path: Path) -> None:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    for cell in notebook.get("cells", []):
        if "source" in cell:
            source = cell["source"]
            joined = "".join(source) if isinstance(source, list) else str(source)
            cleaned = sanitize_text(joined)
            cell["source"] = cleaned.splitlines(keepends=True)
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    notebook.get("metadata", {}).pop("team_members", None)
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanitize a private Team 12 course-repository export for public portfolio use")
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    notebook = root / "frontend" / "housing_api_dashboard.ipynb"
    if notebook.exists():
        sanitize_notebook(notebook)
    for path in root.rglob("*"):
        if not path.is_file() or path == notebook:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"llm_report", ".gitignore", ".gitlab-ci.yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        cleaned = sanitize_text(text)
        if cleaned != text:
            path.write_text(cleaned, encoding="utf-8")


if __name__ == "__main__":
    main()
