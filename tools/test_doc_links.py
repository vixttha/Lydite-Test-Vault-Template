import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from check_doc_links import check_tree, main, validate_paths

from markdown_docs import MARKDOWN, heading_anchors, link_targets


class MarkdownNavigationTests(unittest.TestCase):
    def targets(self, content):
        return list(link_targets(MARKDOWN.parse(content)))

    def test_reference_titled_and_html_links(self):
        text = ("[Ref][install] and [Title](a.md \"label\").\n"
                "\n[install]: /docs/guide.md\n"
                "\n<a href=\"another.md\">Another</a>\n")
        self.assertEqual(self.targets(text), [(1, "/docs/guide.md"), (1, "a.md"), (5, "another.md")])

    def test_empty_alt_images_and_inline_code(self):
        self.assertEqual(self.targets(chr(96) + "[Example](missing.md)" + chr(96)
                                      + " ![](decoration.png) [Real](guide.md)\n"),
                         [(1, "decoration.png"), (1, "guide.md")])

    def test_html_comments_hide_only_their_own_links(self):
        self.assertEqual(self.targets("[Left](left.md) <!-- [Ignored](retired.md) --> [Right](right.md)\n"
                                      "\n<!--\n[Hidden](retired.md)\n-->\n\n[Visible](visible.md)\n"),
                         [(1, "left.md"), (1, "right.md"), (7, "visible.md")])

    def test_malformed_url_and_later_missing_link_are_both_reported(self):
        with TemporaryDirectory() as directory, patch("check_doc_links.ROOT", Path(directory)):
            (Path(directory) / "README.md").write_text(
                "[Address](https://[bad) [Later](missing.md)\n", encoding="utf-8"
            )
            with self.assertRaises(SystemExit) as verdict:
                main([])
            self.assertIn("is invalid", str(verdict.exception))
            self.assertIn("missing.md has no destination", str(verdict.exception))

    def test_committed_link_scope_does_not_use_untracked_content(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            readme.write_text("[Draft](draft.md)\n")
            git = ["git", "-C", directory]
            subprocess.run([*git, "init", "-q"], check=True)
            subprocess.run([*git, "add", "README.md"], check=True)
            subprocess.run([*git, "-c", "user.name=Test Vault", "-c", "user.email=test@example.invalid",
                            "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], check=True)
            (root / "draft.md").write_text("# Draft\n")
            self.assertEqual(validate_paths(root, [readme]), [])
            paths, problems = check_tree(root, "HEAD")
            self.assertEqual(paths, [readme])
            self.assertIn("draft.md has no destination", problems[0])

    def test_rendered_heading_anchors_are_unique_and_visible(self):
        text = ("# Setup\n\n# Setup\n\n# Setup-1\n\n"
                + chr(96) * 3 + "\n# Hidden\n" + chr(96) * 3
                + "\n\n<!--\n# Comment\n-->\n\n# **Quick** Start\n")
        self.assertEqual(list(heading_anchors(MARKDOWN.parse(text))),
                         ["setup", "setup-1", "setup-1-1", "quick-start"])
