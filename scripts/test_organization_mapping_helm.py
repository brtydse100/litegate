"""Render organization mapping chart settings using the standard library."""

import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAPPING = {
    "levels": [{"name": "companies", "groups": {
        "company": {"team_id": "team-company", "members": ["jordan@example.com"]},
    }}, {"name": "departments", "groups": {
        "engineering": {
            "team_id": "team-engineering",
            "parent": "company",
            "members": ["sam@example.com"],
        },
    }}, {"name": "teams", "groups": {
        "platform": {
            "team_id": "team-platform",
            "parent": "engineering",
            "members": ["alice@example.com", "bob@example.com"],
        },
    }}]
}


def render(values):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "values.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        return subprocess.run(
            [
                "helm",
                "template",
                "organization",
                str(ROOT / "deploy/helm/litegate"),
                "-f",
                str(path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )


def document(output, kind):
    return next(doc for doc in output.split("\n---") if f"kind: {kind}\n" in doc)


def env_value(output, name):
    configmap = document(output, "ConfigMap")
    line = next(
        line for line in configmap.splitlines() if line.startswith(f"  {name}: ")
    )
    return json.loads(line.split(": ", 1)[1])


def checksum(output):
    return re.search(r'checksum/organization-mapping: "([a-f0-9]{64})"', output).group(
        1
    )


class OrganizationMappingHelmTests(unittest.TestCase):
    def test_defaults_leave_feature_and_rollout_annotation_absent(self):
        result = render({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ORGANIZATION_MAPPING", result.stdout)
        self.assertNotIn("checksum/organization-mapping", result.stdout)
        self.assertNotIn("organization.json", result.stdout)

    def test_inline_mapping_roundtrips_lists_without_credentials(self):
        result = render({"config": {"organizationMapping": MAPPING}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(env_value(result.stdout, "ORGANIZATION_MAPPING")), MAPPING
        )
        self.assertNotIn("ORGANIZATION_MAPPING_FILE", result.stdout)
        configmap = document(result.stdout, "ConfigMap")
        for credential in ("LITELLM_MASTER_KEY", "JWT_SECRET", "LOCAL_AUTH_PASSWORD"):
            self.assertNotIn(credential, configmap)
        self.assertTrue(checksum(result.stdout))

    def test_yaml_multiline_members_match_inline_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.yaml"
            path.write_text(
                "config:\n  organizationMapping:\n    levels:\n      - name: teams\n        groups:\n          platform:\n"
                "            team_id: team-platform\n            members:\n"
                "              - alice@example.com\n              - bob@example.com\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "helm",
                    "template",
                    "organization",
                    str(ROOT / "deploy/helm/litegate"),
                    "-f",
                    str(path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(env_value(result.stdout, "ORGANIZATION_MAPPING")),
            {
                "levels": [{"name": "teams", "groups": {
                    "platform": {
                        "team_id": "team-platform",
                        "members": ["alice@example.com", "bob@example.com"],
                    }
                }}]
            },
        )

    def test_empty_inline_allows_existing_configmap_file_mount(self):
        result = render(
            {
                "config": {
                    "organizationMapping": {},
                    "organizationMappingFile": "/etc/litegate/organization.json",
                },
                "extraVolumes": [
                    {
                        "name": "organization",
                        "configMap": {"name": "organization-members"},
                    }
                ],
                "extraVolumeMounts": [
                    {
                        "name": "organization",
                        "mountPath": "/etc/litegate",
                        "readOnly": True,
                    }
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            env_value(result.stdout, "ORGANIZATION_MAPPING_FILE"),
            "/etc/litegate/organization.json",
        )
        self.assertNotIn("  ORGANIZATION_MAPPING:", result.stdout)
        deployment = document(result.stdout, "Deployment")
        self.assertIn("name: organization-members", deployment)
        self.assertIn("mountPath: /etc/litegate", deployment)
        self.assertIn("readOnly: true", deployment)

    def test_conflicting_sources_fail_rendering(self):
        result = render(
            {
                "config": {
                    "organizationMapping": MAPPING,
                    "organizationMappingFile": "organization.json",
                }
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("organizationMapping", result.stderr)
        self.assertIn("not both", result.stderr)

    def test_inline_edit_changes_pod_checksum(self):
        original = render({"config": {"organizationMapping": MAPPING}})
        changed_mapping = copy.deepcopy(MAPPING)
        changed_mapping["levels"][2]["groups"]["platform"]["members"].append("carol@example.com")
        changed = render({"config": {"organizationMapping": changed_mapping}})
        for result in (original, changed):
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(checksum(original.stdout), checksum(changed.stdout))

    def test_existing_sso_mapping_and_required_flag_remain_available(self):
        result = render(
            {
                "config": {
                    "organizationMapping": MAPPING,
                    "oidcIssuerUrl": "https://login.example.com",
                    "oidcGroupTeamMapping": {
                        "SSO-Platform": ["team-platform", "team-shared"]
                    },
                    "ssoRequireTeamMapping": True,
                    "ssoDefaultTeamId": "team-default",
                }
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(env_value(result.stdout, "OIDC_GROUP_TEAM_MAPPING")),
            {"SSO-Platform": ["team-platform", "team-shared"]},
        )
        self.assertEqual(env_value(result.stdout, "OIDC_REQUIRE_TEAM_MAPPING"), "true")
        self.assertEqual(
            env_value(result.stdout, "SSO_DEFAULT_TEAM_ID"), "team-default"
        )


if __name__ == "__main__":
    unittest.main()
