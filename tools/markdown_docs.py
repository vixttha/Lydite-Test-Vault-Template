"""Extract rendered Markdown navigation with physical source locations."""

import re
from html.parser import HTMLParser

from markdown_it import MarkdownIt
from markdown_it.rules_inline import image, link


def record_line(rule):
    def apply(state, silent):
        position, count = state.pos, len(state.tokens)
        handled = rule(state, silent)
        if handled and not silent and len(state.tokens) > count:
            state.tokens[count].meta["line_offset"] = state.src.count("\n", 0, position)
        return handled
    return apply


MARKDOWN = MarkdownIt("commonmark").enable(["table", "strikethrough"])
# Retain the source destination so diagnostic code can identify malformed URLs.
MARKDOWN.normalizeLink = lambda value: value
MARKDOWN.inline.ruler.at("link", record_line(link), {"alt": []})
MARKDOWN.inline.ruler.at("image", record_line(image), {"alt": []})


class HtmlNavigation(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.anchors = []

    def handle_starttag(self, tag, attributes):
        fields = dict(attributes)
        target = fields.get({"a": "href", "img": "src"}.get(tag))
        if target is not None:
            self.links.append((self.getpos()[0] - 1, target))
        for key in ("id", "name") if tag == "a" else ("id",):
            if fields.get(key):
                self.anchors.append(fields[key])


def html_navigation(markup):
    parser = HtmlNavigation()
    parser.feed(markup)
    parser.close()
    return parser


def link_targets(tokens):
    for token in tokens:
        first = token.map[0] + 1 if token.map else 1
        if token.type == "html_block":
            yield from ((first + offset, href) for offset, href in html_navigation(token.content).links)
        for child in token.children or ():
            line = first + child.meta.get("line_offset", 0)
            if child.type == "link_open":
                yield line, child.attrGet("href")
            elif child.type == "image":
                yield line, child.attrGet("src")
            elif child.type == "html_inline":
                yield from ((line + offset, href) for offset, href in html_navigation(child.content).links)


def headings(tokens):
    for token, inline in zip(tokens, tokens[1:]):
        if token.type == "heading_open" and inline.type == "inline":
            title = "".join(
                " " if child.type in {"softbreak", "hardbreak"} else child.content
                for child in inline.children or () if child.type in
                {"text", "code_inline", "image", "softbreak", "hardbreak"}
            )
            yield token.map[0] + 1, int(token.tag[1:]), title


def heading_ids(tokens):
    used = set()
    for line, _, title in headings(tokens):
        slug = re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-")
        if not slug:
            continue
        candidate, number = slug, 1
        while candidate in used:
            candidate = f"{slug}-{number}"
            number += 1
        used.add(candidate)
        yield candidate, line


def heading_anchors(tokens):
    yield from (slug for slug, _ in heading_ids(tokens))
    for token in tokens:
        if token.type == "html_block":
            yield from html_navigation(token.content).anchors
        for child in token.children or ():
            if child.type == "html_inline":
                yield from html_navigation(child.content).anchors
