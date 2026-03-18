from __future__ import annotations

import unittest
from types import SimpleNamespace

from ctf import adapters


class AdapterDebugHelperTests(unittest.TestCase):
    def test_console_preview_marks_truncation(self) -> None:
        preview, truncated = adapters._console_preview("abcdef", limit=4)
        self.assertEqual(preview, "abcd")
        self.assertTrue(truncated)

        preview, truncated = adapters._console_preview("abc", limit=4)
        self.assertEqual(preview, "abc")
        self.assertFalse(truncated)

    def test_response_incomplete_reason_from_dict(self) -> None:
        response = SimpleNamespace(incomplete_details={"reason": "max_output_tokens"})
        self.assertEqual(
            adapters._response_incomplete_reason(response),
            "max_output_tokens",
        )

    def test_response_incomplete_reason_from_object(self) -> None:
        response = SimpleNamespace(
            incomplete_details=SimpleNamespace(reason="content_filter")
        )
        self.assertEqual(
            adapters._response_incomplete_reason(response),
            "content_filter",
        )

    def test_response_incomplete_reason_from_status(self) -> None:
        response = SimpleNamespace(incomplete_details=None, status="incomplete")
        self.assertEqual(
            adapters._response_incomplete_reason(response),
            "response status is incomplete",
        )

    def test_classify_response_output_items_reasoning_only(self) -> None:
        response = SimpleNamespace(
            output=[SimpleNamespace(type="reasoning", content=None)]
        )
        self.assertEqual(
            adapters._classify_response_output_items(response),
            "reasoning-only output items",
        )

    def test_classify_response_output_items_mixed_types(self) -> None:
        response = SimpleNamespace(
            output=[
                SimpleNamespace(type="reasoning", content=None),
                SimpleNamespace(type="message", content=[]),
            ]
        )
        self.assertEqual(
            adapters._classify_response_output_items(response),
            "output item types: message,reasoning",
        )


if __name__ == "__main__":
    unittest.main()
