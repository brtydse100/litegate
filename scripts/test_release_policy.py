"""Regression tests for release image publication policy."""

import unittest

from scripts.release_policy import validate


class ReleasePolicyTests(unittest.TestCase):
    def test_release_tag_on_older_main_does_not_publish_latest(self) -> None:
        self.assertFalse(
            validate(
                event="push",
                sha="old",
                main_sha="new",
                manual_tag="",
                publish_latest=False,
            )
        )

    def test_release_tag_on_current_main_publishes_latest(self) -> None:
        self.assertTrue(
            validate(
                event="push",
                sha="main",
                main_sha="main",
                manual_tag="",
                publish_latest=False,
            )
        )

    def test_manual_tag_cannot_use_official_namespace(self) -> None:
        for tag in ("2.11.0", "latest", "edge"):
            with (
                self.subTest(tag=tag),
                self.assertRaisesRegex(ValueError, "test- or dev-"),
            ):
                validate(
                    event="workflow_dispatch",
                    sha="same",
                    main_sha="same",
                    manual_tag=tag,
                    publish_latest=False,
                )

    def test_manual_test_tag_is_allowed(self) -> None:
        validate(
            event="workflow_dispatch",
            sha="branch",
            main_sha="main",
            manual_tag="test-2.11.0",
            publish_latest=False,
        )

    def test_manual_latest_requires_current_main(self) -> None:
        with self.assertRaisesRegex(ValueError, "current main"):
            validate(
                event="workflow_dispatch",
                sha="branch",
                main_sha="main",
                manual_tag="dev-feature",
                publish_latest=True,
            )

    def test_manual_latest_from_current_main(self) -> None:
        self.assertTrue(
            validate(
                event="workflow_dispatch",
                sha="main",
                main_sha="main",
                manual_tag="test-current",
                publish_latest=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
