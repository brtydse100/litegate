"""Check bundled hierarchy rendering and chart validation without dependencies."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HIERARCHY = {
    "levels": [
        {"name": "Division", "groups": [{"members": [{"name": "Engineering", "litellmTeamId": "engineering", "budget": {"perUser": 50, "groupTotal": 5000}}]}]},
        {"name": "Squad", "groups": [{"parent": "Engineering", "members": [
            {"name": "Platform", "ssoGroups": ["platform", "platform-external"], "budget": {"perUser": 100}},
            {"name": "Cloud", "userIds": ["local:alice"], "budget": {"perUser": 0}},
            {"name": "Research", "budget": {"perUser": None}},
        ]}]},
    ]
}


def render(hierarchy):
    with tempfile.TemporaryDirectory() as directory:
        values = Path(directory) / "values.json"
        values.write_text(json.dumps({"organizationHierarchy": hierarchy}), encoding="utf-8")
        return subprocess.run(
            ["helm", "template", "organization", str(ROOT / "deploy/helm/litegate"), "-f", str(values)],
            text=True, capture_output=True, check=False,
        )


class OrganizationHelmTests(unittest.TestCase):
    def test_inline_siblings_multiple_mappings_and_budget_semantics_survive_rendering(self):
        result = render(HIERARCHY)
        self.assertEqual(result.returncode, 0, result.stderr)
        field = next(line for line in result.stdout.splitlines() if line.startswith("  ORGANIZATION_HIERARCHY:"))
        self.assertEqual(json.loads(json.loads(field.split(":", 1)[1].strip())), HIERARCHY)

    def test_configuration_change_updates_deployment_checksum(self):
        before = render(HIERARCHY)
        changed = copy.deepcopy(HIERARCHY)
        changed["levels"][1]["groups"][0]["members"][0]["budget"]["perUser"] = 200
        after = render(changed)
        checksum = lambda output: next(line for line in output.splitlines() if "checksum/organization:" in line)
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertNotEqual(checksum(before.stdout), checksum(after.stdout))

    def test_invalid_budgets_and_unknown_fields_fail_before_deployment(self):
        for budget in ({"perUser": -1}, {"perKey": 10}, {"perUser": "fifty"}):
            with self.subTest(budget=budget):
                changed = copy.deepcopy(HIERARCHY)
                changed["levels"][0]["groups"][0]["members"][0]["budget"] = budget
                self.assertNotEqual(render(changed).returncode, 0)


if __name__ == "__main__":
    unittest.main()
