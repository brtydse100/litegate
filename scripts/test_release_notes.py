"""Check the shared release format and GitHub-ready links."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
NOTES = sorted((ROOT / "docs/releases").glob("v*.md"))


class ReleaseNotesTests(unittest.TestCase):
    def test_every_release_uses_the_shared_structure_and_versioned_image(self):
        for note in NOTES:
            with self.subTest(tag=note.stem):
                text = note.read_text(encoding="utf-8")
                self.assertTrue(text.startswith(f"# LiteGate {note.stem}\n"))
                headings = re.findall(r"^## (.*)$", text, re.MULTILINE)
                self.assertEqual(headings[:2], ["Highlights", "Release Artifacts"])
                self.assertEqual(headings[-1], "Contributors")
                self.assertTrue(set(headings) <= {"Highlights", "Release Artifacts", "Upgrade Notes", "Contributors"})
                prose = "\n".join(line for line in text.splitlines() if not line.startswith("|"))
                self.assertLessEqual(len(prose.split()), 300, "Keep detail in focused guides, not release summaries")
                self.assertIn("| Artifact | Get it |", text)
                self.assertIn(f"docker pull ghcr.io/brtydse100/litegate:{note.stem[1:]}", text)
                self.assertIn(f"/blob/{note.stem}/docs/README.md", text)
                self.assertIn("**Full Changelog**:", text)
                self.assertLess(text.index("**Full Changelog**:"), text.index("## Contributors"))
                self.assertIn("Thanks to @", text)

    def test_github_release_bodies_keep_content_and_use_absolute_links(self):
        with tempfile.TemporaryDirectory() as directory:
            for note in NOTES:
                with self.subTest(tag=note.stem):
                    output = Path(directory) / note.name
                    subprocess.run([sys.executable, str(ROOT / "scripts/release_body.py"), str(note), str(output)], check=True)
                    body = output.read_text(encoding="utf-8")
                    self.assertTrue(body.startswith("## Highlights\n"))
                    self.assertIn("## Release Artifacts\n", body)
                    self.assertIn("## Contributors\n", body)
                    self.assertNotIn(f"# LiteGate {note.stem}", body)
                    for target in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", body):
                        self.assertTrue("://" in target or target.startswith(("#", "mailto:")), target)
                    source = note.read_text(encoding="utf-8")
                    for label, target in re.findall(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)", source):
                        if "://" not in target and not target.startswith(("#", "mailto:")):
                            path, _, fragment = target.partition("#")
                            relative = (note.parent / path).resolve().relative_to(ROOT).as_posix()
                            expected = f"https://github.com/brtydse100/litegate/blob/{note.stem}/{relative}"
                            if fragment:
                                expected += f"#{fragment}"
                            self.assertIn(f"[{label}]({expected})", body)

    def test_pr_notes_are_explicitly_unreleased_and_link_real_artifacts(self):
        text = (ROOT / "docs/releases/unreleased-pr-49.md").read_text(encoding="utf-8")
        self.assertIn("Unreleased", text)
        self.assertIn("## Highlights", text)
        self.assertIn("https://github.com/brtydse100/litegate/pull/49", text)
        self.assertNotRegex(text, r"docker pull ghcr.io/brtydse100/litegate:\d")
        self.assertNotIn("/blob/v2.19.0/", text)


if __name__ == "__main__":
    unittest.main()
