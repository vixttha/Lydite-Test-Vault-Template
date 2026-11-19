"""Check rendered relative links in maintained standalone documentation."""

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_docs import MARKDOWN, heading_anchors, link_targets


ROOT = Path(__file__).resolve().parents[1]
def maintained_paths(root, available):
    paths = set(available)
    homepage = next((root / route for route in (".github/README.md", "README.md", "docs/README.md")
                     if root / route in paths), None)
    return sorted(path for path in paths if path == homepage or (
        path == root / "README.md" or path == root / "versions/README.md"
        or (path.relative_to(root).parts[0] in {"docs", "starter", "languages", "Graphify HQ"})
    ))


def read_text(path):
    return path.read_text(encoding="utf-8")


def validate_paths(root, paths, *, read=read_text, exists=Path.exists, resolve=Path.resolve):
    issues = []
    for path in paths:
        for line, raw in link_targets(MARKDOWN.parse(read(path))):
            where = f"{path.relative_to(root)}:{line}"
            try:
                link = urlsplit(raw)
                if link.scheme or link.netloc:
                    continue
                decoded = unquote(link.path)
                parent = root if decoded.startswith("/") else path.parent
                target = resolve(parent / decoded.lstrip("/")) if decoded else path
                if not target.is_relative_to(root) or not exists(target):
                    issues.append(f"{where}: {raw} has no destination")
                elif link.fragment and target.suffix.lower() == ".md" and unquote(link.fragment) not in heading_anchors(MARKDOWN.parse(read(target))):
                    issues.append(f"{where}: {raw} has no matching heading")
            except (OSError, ValueError) as error:
                issues.append(f"{where}: {raw!r} is invalid: {error}")
    return issues


def check_tree(root, revision):
    git = ["git", "-C", str(root)]
    tree = subprocess.check_output(
        [*git, "rev-parse", "--verify", "--end-of-options", revision + "^{tree}"], text=True,
    ).strip()
    available = {}
    for row in subprocess.check_output([*git, "ls-tree", "-rtz", tree]).split(b"\0"):
        if row:
            header, name = row.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split()
            if mode != "120000" and kind in {"blob", "tree"}:
                available[root / os.fsdecode(name)] = (kind, object_id)
    paths = maintained_paths(root, (path for path in available if path.suffix.lower() == ".md"))
    def read(path):
        kind, object_id = available[path]
        if kind != "blob":
            raise ValueError(f"{path.relative_to(root)} is a directory")
        return subprocess.check_output([*git, "cat-file", "blob", object_id]).decode("utf-8")
    return paths, validate_paths(
        root, paths, read=read, exists=available.__contains__, resolve=lambda path: Path(os.path.normpath(path)),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", metavar="REVISION", help="verify only links in the named committed Git tree")
    args = parser.parse_args(argv)
    if args.tree:
        paths, issues = check_tree(ROOT, args.tree)
        scope = f"Git tree {args.tree}"
    else:
        paths = maintained_paths(ROOT, (p for p in ROOT.rglob("*.md") if p.is_file()))
        issues = validate_paths(ROOT, paths)
        scope = "the working tree"
    if issues:
        raise SystemExit("\n".join(issues))
    print(f"Verified relative links in {len(paths)} maintained Markdown files in {scope}.")


if __name__ == "__main__":
    main()
