import asyncio
import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from version_maps import build_map, markdown_sections, publish_batch, read_archive, verify


class ArchiveTests(unittest.TestCase):
    def test_unicode_separator_does_not_shift_physical_heading_lines(self):
        self.assertEqual(list(markdown_sections("# First\u2028still first\n# Second\n"))[-1],
                         (2, 1, "Second"))

    def archived_graph(self, directory, readme, extra):
        output = Path(directory) / "graph"
        source = {"README.md": readme, **extra}
        files = {name: ("versions/v0.0.1/" + name, "b" * 40, content) for name, content in source.items()}
        build_map("v0.0.1", {"source_commit": "a" * 40, "source_path": "source"}, files, output)
        return json.loads((output / "graph.json").read_bytes())

    def test_archived_fence_samples_are_not_navigation(self):
        fence = chr(96) * 3
        readme = f"# Readme\n\n{fence}md\n[Example](guide.md)\n{fence}\n"
        with TemporaryDirectory() as directory:
            graph = self.archived_graph(directory, readme, {"guide.md": "# Guide\n"})
            self.assertFalse(any(edge["relation"] == "links_to" for edge in graph["links"]))

    def test_binary_and_latin1_sources_keep_pinned_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "source-repo"
            inputs = {"README.md": b"# Guide\n\n![Tiny](tiny.png)\n",
                      "tiny.png": bytes.fromhex("89504e470d0a1a0a00ff00"),
                      "fixture.py": b"# coding: latin-1\ndef label(): return 'caf\xe9'\n"}
            source = root / "source"
            archive = root / "versions"
            copy = archive / "v0.0.1"
            for folder in (source, copy):
                folder.mkdir(parents=True)
                for name, data in inputs.items():
                    (folder / name).write_bytes(data)
            git = ["git", "-C", str(root)]
            subprocess.run([*git, "init", "-q"], check=True)
            subprocess.run([*git, "add", "."], check=True)
            subprocess.run([*git, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], check=True)
            sha = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
            record = {"source_commit": sha, "source_path": "source"}
            with patch("version_maps.ROOT", root), patch("version_maps.ARCHIVE", archive):
                files = read_archive("v0.0.1", record)
            self.assertIsNone(files["tiny.png"][2])
            self.assertIn("café", files["fixture.py"][2])
            self.assertEqual(files["tiny.png"][1], hashlib.sha1(
                f"blob {len(inputs['tiny.png'])}\0".encode() + inputs["tiny.png"]
            ).hexdigest())
            output = Path(directory) / "graph"
            receipt = build_map("v0.0.1", record, files, output)
            asyncio.run(verify(output, receipt))
            inside_git = root / "graph"
            shutil.copytree(output, inside_git)
            asyncio.run(verify(inside_git, receipt))

    def test_mcp_rejects_changed_digest_and_nonmatching_source_line(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "graph"
            record = {"source_commit": "a" * 40, "source_path": "source"}
            files = {"README.md": ("versions/v0.0.1/README.md", "b" * 40, "# Readme\n")}
            receipt = build_map("v0.0.1", record, files, output)
            asyncio.run(verify(output, receipt))
            graph = output / "graph.json"
            data = json.loads(graph.read_bytes())
            file = next(node for node in data["nodes"] if node["id"] == "file:README.md")
            file["source_location"] = "L10"
            graph.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest differs"):
                asyncio.run(verify(output, receipt))
            receipt["graph_sha256"] = hashlib.sha256(graph.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "could not resolve"):
                asyncio.run(verify(output, receipt))

    def test_failed_batch_keeps_destination_reusable(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "maps"
            output.mkdir()
            def interrupted(stage, *_):
                (stage / "partial.json").touch()
                raise ValueError("second archive failed")
            with patch("version_maps.rebuild", side_effect=interrupted):
                with self.assertRaisesRegex(ValueError, "second archive failed"):
                    publish_batch(output, {}, False)
            self.assertEqual(list(output.iterdir()), [])
            def success(stage, *_):
                (stage / "README.md").write_text("# Complete\n")
                return {"complete": True}
            with patch("version_maps.rebuild", side_effect=success):
                self.assertEqual(publish_batch(output, {}, False), {"complete": True})
            self.assertTrue((output / "README.md").is_file())
