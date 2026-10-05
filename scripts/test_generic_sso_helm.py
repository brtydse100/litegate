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


def render(config, **chart_values):
    with tempfile.TemporaryDirectory() as directory:
        values = Path(directory) / "values.json"
        values.write_text(json.dumps({"config": config, **chart_values}), encoding="utf-8")
        return subprocess.run(
            ["helm", "template", "generic-sso", str(ROOT / "deploy/helm/litegate"), "-f", str(values)],
            text=True,
            capture_output=True,
            check=False,
        )


class GenericSSOHelmTests(unittest.TestCase):
    def test_custom_ca_requires_a_certificate_source(self):
        for custom_ca in ({"mountPath": "/etc/ssl/certs/custom.pem"}, {"key": "custom.pem"}, {"key": "custom.pem", "mountPath": "/tmp/custom.pem"}):
            with self.subTest(custom_ca=custom_ca):
                result = render({}, customCA=custom_ca)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("set customCA.configMap or customCA.secret", result.stderr)
                self.assertIn("destination inside the pod", result.stderr)

    def test_custom_ca_source_volume_mount_and_environment_match(self):
        for source in ("configMap", "secret"):
            for persistence_enabled in (True, False):
                for custom_path in (False, True):
                    with self.subTest(source=source, persistence=persistence_enabled, custom_path=custom_path):
                        path = "/etc/ssl/certs/custom.pem" if custom_path else "/etc/ssl/certs/litegate-custom-ca.pem"
                        key = "custom.pem" if custom_path else "ca-bundle.crt"
                        custom_ca = {source: "corporate-ca"}
                        if custom_path:
                            custom_ca.update(mountPath=path, key=key)
                        result = render({}, customCA=custom_ca, persistence={"enabled": persistence_enabled})
                        self.assertEqual(result.returncode, 0, result.stderr)
                        deployment = next(doc for doc in result.stdout.split("\n---") if "kind: Deployment\n" in doc)
                        self.assertIn(f'- name: SSL_CERT_FILE\n              value: "{path}"', deployment)
                        self.assertIn(
                            f'- name: custom-ca\n              mountPath: "{path}"\n              subPath: "{key}"\n              readOnly: true',
                            deployment,
                        )
                        name_field = "name" if source == "configMap" else "secretName"
                        self.assertIn(f'- name: custom-ca\n          {source}:\n            {name_field}: "corporate-ca"', deployment)

    def test_empty_custom_ca_disables_mount_and_environment(self):
        result = render({}, customCA={}, persistence={"enabled": False})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("name: custom-ca", result.stdout)
        self.assertNotIn("SSL_CERT_FILE", result.stdout)

    def test_custom_ca_empty_or_conflicting_sources_remain_rejected(self):
        for custom_ca in ({"configMap": ""}, {"secret": ""}, {"configMap": "one", "secret": "two"}):
            with self.subTest(custom_ca=custom_ca):
                result = render({}, customCA=custom_ca)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("customCA", result.stderr)

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
