from __future__ import annotations

import argparse
import re
from pathlib import Path


CHECKS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "live_api_key": re.compile(r"(?i)(?:api[_-]?key|token|password)[ \t]*[:=][ \t]*['\"]?(?!\$\{|<|\[|None|$)[A-Za-z0-9_\-]{20,}"),
    "student_id_line": re.compile(r"(?i)(?:student\s*(?:id|number)|team members?)\s*[:=].*\d{6,8}"),
    "raw_email": re.compile(r"(?i)\b[A-Z0-9._%+-]+@(?!example\.(?:org|com)|localhost)[A-Z0-9.-]+\.[A-Z]{2,}\b"),
}


def audit(root: Path) -> list[str]:
    findings = []
    ignored = {".git", ".venv", ".pytest_cache", "__pycache__"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in CHECKS.items():
            if pattern.search(text):
                findings.append(f"{name}: {path.relative_to(root)}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args()
    findings = audit(args.root.resolve())
    if findings:
        print("\n".join(findings))
        raise SystemExit(1)
    print("public audit: no high-risk secret/PII patterns found")


if __name__ == "__main__":
    main()
