import unittest

from markdown_docs import MARKDOWN, link_targets


class MarkdownNavigationTests(unittest.TestCase):
    def targets(self, content):
        return list(link_targets(MARKDOWN.parse(content)))

    def test_reference_titled_and_html_links(self):
        text = ("[Ref][install] and [Title](a.md \"label\").\n"
                "\n[install]: /docs/guide.md\n"
                "\n<a href=\"another.md\">Another</a>\n")
        self.assertEqual(self.targets(text), [(1, "/docs/guide.md"), (1, "a.md"), (5, "another.md")])
