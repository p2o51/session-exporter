import json
import os
import tempfile
import unittest
from unittest import mock

import exporters
import pricing
from parsers import kimi


class KimiParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session_dir = os.path.join(
            self.tmp.name, "sessions", "wd_project_123", "session_test"
        )
        self.main_dir = os.path.join(self.session_dir, "agents", "main")
        self.sub_dir = os.path.join(self.session_dir, "agents", "agent-0")
        os.makedirs(self.main_dir)
        os.makedirs(self.sub_dir)
        self.state_path = os.path.join(self.session_dir, "state.json")
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "title": "New session",
                    "createdAt": 1_700_000_000_000,
                    "updatedAt": 1_700_000_005_000,
                    "workDir": "/tmp/example-project",
                },
                fh,
            )

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _write_wire(path, events):
        with open(path, "w", encoding="utf-8") as fh:
            for event in events:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _build_fixture(self):
        self._write_wire(
            os.path.join(self.main_dir, "wire.jsonl"),
            [
                {"type": "metadata", "protocol_version": "1", "created_at": 1_700_000_000_000},
                {
                    "type": "turn.prompt",
                    "input": [{"type": "text", "text": "Add the export feature"}],
                    "origin": {"kind": "user"},
                    "time": 1_700_000_001_000,
                },
                {
                    "type": "llm.request",
                    "provider": "kimi",
                    "model": "k3",
                    "modelAlias": "kimi-code/k3",
                    "time": 1_700_000_002_000,
                },
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "content.part",
                        "part": {"type": "think", "think": "I should inspect the exporter."},
                    },
                    "time": 1_700_000_002_100,
                },
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "tool.call",
                        "name": "Read",
                        "args": {"path": "exporter.py"},
                    },
                    "time": 1_700_000_002_200,
                },
                {
                    "type": "usage.record",
                    "model": "kimi-code/k3",
                    "usageScope": "turn",
                    "usage": {
                        "inputOther": 1000,
                        "output": 200,
                        "inputCacheRead": 3000,
                        "inputCacheCreation": 100,
                    },
                    "time": 1_700_000_003_000,
                },
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "content.part",
                        "part": {"type": "text", "text": "Export support is ready."},
                    },
                    "time": 1_700_000_004_000,
                },
            ],
        )
        self._write_wire(
            os.path.join(self.sub_dir, "wire.jsonl"),
            [
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "tool.result",
                        "result": {"output": "file contents", "truncated": True},
                    },
                    "time": 1_700_000_002_300,
                }
            ],
        )

    def test_summarizes_recorded_usage_and_prices_k3_alias(self):
        self._build_fixture()
        pattern = os.path.join(self.tmp.name, "sessions", "*", "*", "state.json")
        with mock.patch.object(kimi, "_SESSIONS_GLOB", pattern):
            sessions = kimi.list_sessions()

        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertEqual(session["id"], "session_test")
        self.assertEqual(session["title"], "Add the export feature")
        self.assertEqual(session["project"], "example-project")
        self.assertEqual(session["model"], "kimi-code/k3")
        self.assertEqual(session["message_count"], 2)
        self.assertEqual(
            session["tokens"],
            {
                "input": 1000,
                "output": 200,
                "cache_creation": 100,
                "cache_read": 3000,
                "reasoning": 0,
                "total": 4300,
                "cache_hit_rate": 3000 / 4100,
                "basis": "recorded",
            },
        )
        self.assertEqual(pricing.cost_for(session)["usd"], 0.0072)

    def test_loads_main_and_subagent_messages_in_timestamp_order(self):
        self._build_fixture()
        messages = kimi.load_messages("session_test", self.session_dir)
        self.assertEqual(
            [message["role"] for message in messages],
            ["user", "reasoning", "tool", "tool", "assistant"],
        )
        self.assertEqual(messages[3]["meta"]["agent"], "agent-0")
        self.assertIn("[truncated]", messages[3]["text"])
        self.assertEqual(messages[-1]["meta"]["model"], "kimi-code/k3")

    def test_unwraps_host_prompt_for_title_and_transcript(self):
        wrapped = """# Instructions (read first)\ninternal context\n# User request\n\n## user\nFirst request\n\n## assistant\nDone\n\n## user\nFix the menu\n"""
        self._write_wire(
            os.path.join(self.main_dir, "wire.jsonl"),
            [
                {
                    "type": "turn.prompt",
                    "input": [{"type": "text", "text": wrapped}],
                    "time": 1_700_000_001_000,
                }
            ],
        )
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "title": "# Instructions (read first) internal context",
                    "workDir": "/tmp/example-project",
                },
                fh,
            )
        session = kimi._summarize_session(self.state_path)
        messages = kimi.load_messages("session_test", self.session_dir)
        self.assertEqual(session["title"], "Fix the menu")
        self.assertEqual(messages[0]["text"], "Fix the menu")
        self.assertEqual(
            kimi._human_prompt("Document the # User request heading"),
            "Document the # User request heading",
        )

    def test_current_kimi_code_model_aliases_are_priced(self):
        expected = {
            "k3": (3.0, 15.0, 0.30),
            "kimi-code/k3": (3.0, 15.0, 0.30),
            "kimi-for-coding": (0.95, 4.0, 0.19),
            "kimi-code/kimi-for-coding": (0.95, 4.0, 0.19),
            "kimi-for-coding-highspeed": (1.90, 8.0, 0.38),
            "kimi-code/kimi-for-coding-highspeed": (1.90, 8.0, 0.38),
        }
        for alias, rates in expected.items():
            with self.subTest(alias=alias):
                resolved = pricing.rates_for(alias)
                self.assertEqual(
                    (resolved["input"], resolved["output"], resolved["cache_read"]), rates
                )

    def test_kimi_export_uses_label_and_includes_cache_creation(self):
        self._build_fixture()
        session = kimi._summarize_session(self.state_path)
        session.update(pricing.cost_for(session))
        markdown = exporters.render_markdown(
            session, kimi.load_messages(session["id"], session["ref"])
        )
        row = exporters._csv_row(session["title"], session)
        self.assertIn("**Source:** Kimi Code", markdown)
        self.assertIn("cache write 100", markdown)
        self.assertEqual(
            row[exporters.CSV_HEADER.index("Cache Write Tokens")], 100
        )


if __name__ == "__main__":
    unittest.main()
