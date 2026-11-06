"""Check public login appearance values reach the Helm ConfigMap."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LoginCustomizationHelmTests(unittest.TestCase):
    def test_login_values_are_rendered_as_environment_strings(self):
        for config, expected in (
            ({}, {"LOGIN_TEXT": "", "LOGO_URL": ""}),
            (
                {
                    "loginText": 'Welcome "Example"\nUse <b>work</b> account',
                    "logoUrl": "https://images.example.com/logo.svg",
                },
                {
                    "LOGIN_TEXT": 'Welcome "Example"\nUse <b>work</b> account',
                    "LOGO_URL": "https://images.example.com/logo.svg",
                },
            ),
        ):
            with (
                self.subTest(config=config),
                tempfile.TemporaryDirectory() as directory,
            ):
                values = Path(directory) / "values.json"
                values.write_text(json.dumps({"config": config}), encoding="utf-8")
                result = subprocess.run(
                    [
                        "helm",
                        "template",
                        "login-customization",
                        str(ROOT / "deploy/helm/litegate"),
                        "-f",
                        str(values),
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                for key, value in expected.items():
                    self.assertIn(
                        f"  {key}: {json.dumps(value)}", result.stdout.splitlines()
                    )


if __name__ == "__main__":
    unittest.main()
