from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.services import agents_memory_sync


class TestAgentsMemorySync(unittest.TestCase):
    def test_project_name_normalizes_to_lowercase_slug(self) -> None:
        result = agents_memory_sync._project_name("/Users/cliff/workspace/agent/Synapse-Network-Growing")
        self.assertEqual(result, "synapse-network-growing")

    def test_push_requirement_completed_uses_normalized_project(self) -> None:
        requirement = SimpleNamespace(
            id=7,
            title="Launch readiness",
            description_markdown="Ship the release.",
            priority="high",
            completed_at="2026-04-12T08:00:00Z",
            created_at="2026-04-12T07:00:00Z",
            target_project_path="/tmp/Synapse-Network",
        )

        with patch.object(agents_memory_sync, "_push") as push_mock:
            agents_memory_sync.push_requirement_completed(requirement, [], "ready", ["README.md"])

        push_mock.assert_called_once()
        content, source_type, project = push_mock.call_args.args
        self.assertEqual(source_type, "requirement_completion")
        self.assertEqual(project, "synapse-network")
        self.assertIn("project: synapse-network", content)


if __name__ == "__main__":
    unittest.main()
