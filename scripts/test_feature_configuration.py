"""Helm/Docker parity for governance and personal analytics settings."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "organizationAccessDesignations": (
        "organization_access_designations",
        "ORGANIZATION_ACCESS_DESIGNATIONS",
        {},
    ),
    "organizationGroupAdmins": (
        "organization_group_admins",
        "ORGANIZATION_GROUP_ADMINS",
        {},
    ),
    "organizationCleanupEnabled": (
        "organization_cleanup_enabled",
        "ORGANIZATION_CLEANUP_ENABLED",
        False,
    ),
    "analyticsEnabled": ("analytics_enabled", "ANALYTICS_ENABLED", True),
    "analyticsRetentionDays": (
        "analytics_retention_days",
        "ANALYTICS_RETENTION_DAYS",
        90,
    ),
    "analyticsBatchConcurrency": (
        "analytics_batch_concurrency",
        "ANALYTICS_BATCH_CONCURRENCY",
        5,
    ),
    "hierarchicalBudgetsEnabled": (
        "hierarchical_budgets_enabled",
        "HIERARCHICAL_BUDGETS_ENABLED",
        False,
    ),
    "hierarchicalBudgetsEnforced": (
        "hierarchical_budgets_enforced",
        "HIERARCHICAL_BUDGETS_ENFORCED",
        False,
    ),
    "keyRotationSettleSeconds": (
        "key_rotation_settle_seconds",
        "KEY_ROTATION_SETTLE_SECONDS",
        12,
    ),
}


def render(*args):
    result = subprocess.run(
        ["helm", "template", "litegate", str(ROOT / "deploy/helm/litegate"), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


class FeatureConfiguration(unittest.TestCase):
    def test_defaults_and_docker_yaml_have_matching_typed_values(self):
        docs = render()
        env = next(doc["data"] for doc in docs if doc["kind"] == "ConfigMap")
        docker = yaml.safe_load(
            (ROOT / "deploy/docker-compose/config.yaml").read_text()
        )
        for name, variable, default in FIELDS.values():
            self.assertEqual(docker[name], default)
            self.assertEqual(json.loads(env[variable]), default)

    def test_explicit_mappings_and_limits_survive_helm_rendering(self):
        config = {
            "organizationAccessDesignations": {"alice": ["engineering", "platform"]},
            "organizationGroupAdmins": {"engineering": ["alice", "bob"]},
            "organizationCleanupEnabled": True,
            "analyticsEnabled": False,
            "analyticsRetentionDays": 366,
            "analyticsBatchConcurrency": 20,
            "hierarchicalBudgetsEnabled": True,
            "hierarchicalBudgetsEnforced": True,
            "keyRotationSettleSeconds": 30,
        }
        with tempfile.TemporaryDirectory() as directory:
            values = Path(directory) / "values.json"
            values.write_text(json.dumps({"config": config}))
            docs = render("-f", str(values))
        env = next(doc["data"] for doc in docs if doc["kind"] == "ConfigMap")
        for name, (_, variable, _) in FIELDS.items():
            with self.subTest(field=name):
                self.assertEqual(json.loads(env[variable]), config[name])

    def test_minimum_analytics_limits_are_accepted(self):
        docs = render(
            "--set",
            "config.analyticsRetentionDays=1",
            "--set",
            "config.analyticsBatchConcurrency=1",
        )
        env = next(doc["data"] for doc in docs if doc["kind"] == "ConfigMap")
        self.assertEqual(json.loads(env["ANALYTICS_RETENTION_DAYS"]), 1)
        self.assertEqual(json.loads(env["ANALYTICS_BATCH_CONCURRENCY"]), 1)

    def test_invalid_types_and_bounds_are_rejected(self):
        invalid = [
            ("analyticsRetentionDays", 0),
            ("analyticsRetentionDays", 367),
            ("analyticsBatchConcurrency", 0),
            ("analyticsBatchConcurrency", 21),
            ("analyticsEnabled", "true"),
            ("organizationCleanupEnabled", "false"),
            ("hierarchicalBudgetsEnabled", "true"),
            ("hierarchicalBudgetsEnforced", "true"),
            ("keyRotationSettleSeconds", -1),
            ("keyRotationSettleSeconds", 121),
            ("organizationAccessDesignations", {"alice": "engineering"}),
            ("organizationGroupAdmins", {"engineering": [1]}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            values = Path(directory) / "values.json"
            for name, value in invalid:
                with self.subTest(field=name, value=value):
                    values.write_text(json.dumps({"config": {name: value}}))
                    result = subprocess.run(
                        [
                            "helm",
                            "template",
                            "litegate",
                            str(ROOT / "deploy/helm/litegate"),
                            "-f",
                            str(values),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("schema", result.stderr.lower())

    def test_configuration_change_rolls_pod(self):
        def checksum(docs):
            deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
            return deployment["spec"]["template"]["metadata"]["annotations"][
                "checksum/config"
            ]

        self.assertNotEqual(
            checksum(render()),
            checksum(render("--set", "config.analyticsEnabled=false")),
        )


if __name__ == "__main__":
    unittest.main()
