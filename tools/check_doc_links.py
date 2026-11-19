"""Check rendered relative links in maintained standalone documentation."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_docs import MARKDOWN, link_targets


ROOT = Path(__file__).resolve().parents[1]
def anchors(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if heading := re.match(r"^#{1,6} (.+?)\s*#*\s*$", line):
            yield re.sub(r"[^\w\s-]", "", heading[1].lower()).replace(" ", "-")


def maintained_paths(root, available):
    paths = set(available)
    homepage = next((root / route for route in (".github/README.md", "README.md", "docs/README.md")
                     if root / route in paths), None)
    return sorted(path for path in paths if path == homepage or (
        path == root / "README.md" or path == root / "versions/README.md"
        or (path.relative_to(root).parts[0] in {"docs", "starter", "languages", "Graphify HQ"})
    ))


def main():
    maintained = maintained_paths(ROOT, ROOT.rglob("*.md"))
    issues = []
    for path in sorted(maintained):
        for line, raw in link_targets(MARKDOWN.parse(path.read_text(encoding="utf-8"))):
            try:
                link = urlsplit(raw)
            except ValueError as error:
                issues.append(f"{path.relative_to(ROOT)}:{line}: {raw!r} is invalid: {error}")
                continue
            if link.scheme or link.netloc:
                continue
            decoded = unquote(link.path)
            parent = ROOT if decoded.startswith("/") else path.parent
            target = (parent / decoded.lstrip("/")).resolve() if decoded else path
            if not target.is_relative_to(ROOT) or not target.exists():
                issues.append(f"{path.relative_to(ROOT)}:{line}: {raw} has no destination")
            elif link.fragment and target.suffix == ".md" and unquote(link.fragment) not in anchors(target):
                issues.append(f"{path.relative_to(ROOT)}:{line}: {raw} has no matching heading")
    if issues:
        raise SystemExit("\n".join(issues))
    print(f"Verified relative links in {len(maintained)} maintained Markdown files.")


if __name__ == "__main__":
    main()
