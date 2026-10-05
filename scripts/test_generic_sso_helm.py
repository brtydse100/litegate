"""Check generic OAuth chart rendering using only Python's standard library."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "genericClientId": "test-client",
    "genericClientSecret": "test-only-provider-secret",
    "genericAuthorizationEndpoint": "https://idp.example/authorize",
    "genericTokenEndpoint": "https://idp.example/token",
    "genericUserinfoEndpoint": "https://idp.example/userinfo",
    "genericRedirectUri": "https://portal.example/api/auth/callback",
    "genericScope": "openid profile email",
    "genericUserIdAttribute": "identity.employee_id",
    "genericUserEmailAttribute": "mail",
    "genericClientUsePkce": True,
    "genericIncludeClientId": False,
    "oidcGroupsClaim": "identity.groups",
    "oidcGroupTeamMapping": {"Engineering": "team-engineering"},
    "localAuthPassword": "",
}


def render(config):
    with tempfile.TemporaryDirectory() as directory:
        values = Path(directory) / "values.json"
        values.write_text(json.dumps({"config": config}), encoding="utf-8")
        return subprocess.run(
            ["helm", "template", "generic-sso", str(ROOT / "deploy/helm/litegate"), "-f", str(values)],
            text=True,
            capture_output=True,
            check=False,
        )


class GenericSSOHelmTests(unittest.TestCase):
    def test_verification_defaults_and_explicit_opt_outs(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                config = CONFIG if enabled else CONFIG | {"sslVerify": False, "genericRequireVerifiedEmail": False}
                result = render(config)
                self.assertEqual(result.returncode, 0, result.stderr)
                for field in ("SSL_VERIFY", "GENERIC_REQUIRE_VERIFIED_EMAIL"):
                    self.assertIn(f'  {field}: "{str(enabled).lower()}"', result.stdout.splitlines())

    def test_ssl_verification_setting_is_rendered_without_sso(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                result = render({"sslVerify": enabled})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'  SSL_VERIFY: "{str(enabled).lower()}"', result.stdout.splitlines())
                self.assertNotIn("GENERIC_REQUIRE_VERIFIED_EMAIL", result.stdout)

    def test_generic_settings_and_group_mapping_are_rendered_without_oidc(self):
        result = render(CONFIG)
        self.assertEqual(result.returncode, 0, result.stderr)
        documents = result.stdout.split("\n---")
        configmap = next(doc for doc in documents if "kind: ConfigMap\n" in doc)
        secret = next(doc for doc in documents if "kind: Secret\n" in doc)
        expected = {
            "GENERIC_CLIENT_ID": "test-client",
            "GENERIC_AUTHORIZATION_ENDPOINT": CONFIG["genericAuthorizationEndpoint"],
            "GENERIC_TOKEN_ENDPOINT": CONFIG["genericTokenEndpoint"],
            "GENERIC_USERINFO_ENDPOINT": CONFIG["genericUserinfoEndpoint"],
            "GENERIC_REDIRECT_URI": CONFIG["genericRedirectUri"],
            "GENERIC_SCOPE": "openid profile email",
            "GENERIC_USER_ID_ATTRIBUTE": "identity.employee_id",
            "GENERIC_USER_EMAIL_ATTRIBUTE": "mail",
            "GENERIC_CLIENT_USE_PKCE": "true",
            "GENERIC_INCLUDE_CLIENT_ID": "false",
            "OIDC_GROUPS_CLAIM": "identity.groups",
        }
        for field, value in expected.items():
            self.assertIn(f"  {field}: {json.dumps(value)}", configmap.splitlines())
        self.assertIn('OIDC_GROUP_TEAM_MAPPING: "{\\"Engineering\\":\\"team-engineering\\"}"', configmap)
        self.assertNotIn("GENERIC_CLIENT_SECRET", configmap)
        self.assertNotIn(CONFIG["genericClientSecret"], configmap)
        self.assertNotIn("OIDC_ISSUER_URL", configmap)
        self.assertIn(f'GENERIC_CLIENT_SECRET: "{CONFIG["genericClientSecret"]}"', secret)
        self.assertNotIn("LOCAL_AUTH_PASSWORD", secret)

    def test_partial_generic_config_is_rejected(self):
        result = render({"genericAuthorizationEndpoint": CONFIG["genericAuthorizationEndpoint"]})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("together", result.stderr)

    def test_conflicting_modes_are_rejected(self):
        result = render(CONFIG | {"oidcIssuerUrl": "https://oidc.example"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not both", result.stderr)


if __name__ == "__main__":
    unittest.main()
