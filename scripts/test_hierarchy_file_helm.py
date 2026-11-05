"""File hierarchy chart input and composition contracts."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(values):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "values.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        return subprocess.run(
            [
                "helm",
                "template",
                "file",
                str(ROOT / "deploy/helm/litegate"),
                "-f",
                str(path),
            ],
            capture_output=True,
            text=True,
        )


class HierarchyFileHelmTests(unittest.TestCase):
    def documents(self, values):
        result = render(values)
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = list(yaml.safe_load_all(result.stdout))
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        config = next(d for d in docs if d["kind"] == "ConfigMap")
        return deployment["spec"]["template"], config["data"]

    def test_default_off_preserves_inline_checksum(self):
        pod, config = self.documents({})
        self.assertNotIn("ORGANIZATION_HIERARCHY_FILE", config)
        self.assertEqual(json.loads(config["ORGANIZATION_HIERARCHY"]), {"levels": []})
        self.assertIn("checksum/organization", pod["metadata"]["annotations"])
        self.assertFalse(
            any(v["name"] == "organization-hierarchy" for v in pod["spec"]["volumes"])
        )

    def test_file_defaults_and_custom_paths(self):
        for options in (
            {"configMap": "litegate-hierarchy"},
            {
                "configMap": "custom",
                "key": "tree.json",
                "mountPath": "/custom/tree.json",
            },
        ):
            with self.subTest(options=options):
                pod, config = self.documents({"organizationHierarchyFile": options})
                destination = options.get(
                    "mountPath", "/etc/litegate/organization.json"
                )
                self.assertEqual(config["ORGANIZATION_HIERARCHY_FILE"], destination)
                self.assertNotIn("ORGANIZATION_HIERARCHY", config)
                mount = next(
                    m
                    for m in pod["spec"]["containers"][0]["volumeMounts"]
                    if m["name"] == "organization-hierarchy"
                )
                self.assertEqual(
                    mount,
                    {
                        "name": "organization-hierarchy",
                        "mountPath": destination,
                        "subPath": options.get("key", "organization.json"),
                        "readOnly": True,
                    },
                )
                volume = next(
                    v
                    for v in pod["spec"]["volumes"]
                    if v["name"] == "organization-hierarchy"
                )
                self.assertEqual(volume["configMap"]["name"], options["configMap"])

    def test_rejects_invalid_inputs(self):
        for value in (
            "invalid",
            [],
            False,
            {"key": "tree.json"},
            {"mountPath": "/tree.json"},
            {"configMap": ""},
            {"configMap": 42},
            {"configMap": "tree", "key": 42},
            {"configMap": "tree", "key": ""},
            {"configMap": "tree", "key": "../tree.json"},
            {"configMap": "tree", "key": "."},
            {"configMap": "tree", "key": ".."},
            {"configMap": "tree", "unexpected": True},
            {"configMap": "tree", "mountPath": 42},
            *(
                {"configMap": "tree", "mountPath": p}
                for p in ("relative.json", "/", "/etc/", "/etc/..", "/etc/./tree.json")
            ),
        ):
            with self.subTest(value=value):
                self.assertNotEqual(
                    render({"organizationHierarchyFile": value}).returncode, 0
                )

    def test_rejects_nonempty_inline(self):
        from scripts.test_organization_helm import HIERARCHY

        result = render(
            {
                "organizationHierarchyFile": {"configMap": "tree"},
                "organizationHierarchy": HIERARCHY,
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("organizationHierarchy", result.stderr)

    def test_composes_persistence_ca_and_extras(self):
        pod, _ = self.documents(
            {
                "organizationHierarchyFile": {"configMap": "tree"},
                "customCA": {"configMap": "ca"},
                "extraVolumes": [{"name": "extra", "emptyDir": {}}],
                "extraVolumeMounts": [{"name": "extra", "mountPath": "/extra"}],
            }
        )
        container = pod["spec"]["containers"][0]
        self.assertEqual(
            {v["name"] for v in pod["spec"]["volumes"]},
            {"data", "custom-ca", "extra", "organization-hierarchy"},
        )
        self.assertEqual(
            {v["name"] for v in container["volumeMounts"]},
            {"data", "custom-ca", "extra", "organization-hierarchy"},
        )
        self.assertEqual(
            container["env"],
            [
                {
                    "name": "SSL_CERT_FILE",
                    "value": "/etc/ssl/certs/litegate-custom-ca.pem",
                }
            ],
        )

    def test_file_option_change_updates_checksum(self):
        before, _ = self.documents({"organizationHierarchyFile": {"configMap": "tree"}})
        for option in (
            {"configMap": "other"},
            {"configMap": "tree", "key": "other.json"},
            {"configMap": "tree", "mountPath": "/other/tree.json"},
        ):
            after, _ = self.documents({"organizationHierarchyFile": option})
            self.assertNotEqual(
                before["metadata"]["annotations"], after["metadata"]["annotations"]
            )
