import asyncio
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from version_maps import build_map, publish_batch, read_archive, verify


class ArchiveTests(unittest.TestCase):
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
