"""Focused contract tests for the FastAPI transcript upload route.

Real student transcripts contain PII and are intentionally not repository
fixtures.  These tests use an existing non-PII valid PDF to exercise the real
multipart ASGI route, while replacing only the parser result with deterministic
synthetic rows so the response contract can be asserted exactly.

Usage:
    python -m unittest tests.test_transcript_api -v
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("CC_API_WARMUP", "0")

import httpx

import careercompass.api.app as app_module


VALID_PDF = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "syllabi"
    / "cybersecurity_fundamentals.pdf"
)


def _parsed_transcript() -> dict:
    all_courses = [
        {
            "course_code": "0413405",
            "course_name": "Computer and Network Security",
            "credit_hours": 3,
            "grade": "B+",
            "grade_points": 3.33,
            "grade_strength": "strong",
            "status": "passed",
            "semester": "20241",
            "prerequisite": None,
        },
        {
            "course_code": "A0434505",
            "course_name": "",
            "credit_hours": 3,
            "grade": None,
            "grade_points": None,
            "grade_strength": "unknown",
            "status": "passed",
            "semester": None,
            "prerequisite": None,
        },
    ]
    return {
        "student": {
            "student_name": "Synthetic Student",
            "student_id": "fixture-001",
            "cumulative_gpa": 3.25,
            "rating": "VERY GOOD",
            "level": "Fourth Year",
            "plan_hours": 132,
            "passed_hours": 90,
            "remaining_hours": 42,
            "registered_hours": 15,
        },
        "summary": {
            "total_courses": 2,
            "passed_courses": 2,
            "total_credit_hours": 6,
            "passed_credit_hours": 6,
        },
        "categories": [{
            "category_name": "Major Requirement Compulsory",
            "required_hours": 43,
            "passed_hours": 3,
            "courses": all_courses,
        }],
        "all_courses": all_courses,
    }


class TranscriptApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # ASGITransport drives the actual FastAPI router and exception handlers
        # without starting the unrelated long-running extraction worker.
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_module.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_parse_adds_typed_courses_without_changing_legacy_fields(self):
        parsed = _parsed_transcript()

        with patch.object(app_module, "_parse_transcript_bytes", return_value=parsed):
            response = await self.client.post(
                "/api/v1/transcripts/parse",
                files={
                    "file": (
                        "synthetic-transcript.pdf",
                        VALID_PDF.read_bytes(),
                        "application/pdf",
                    )
                },
                data={"save": "false"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        self.assertEqual(body["student"], parsed["student"])
        self.assertEqual(body["summary"]["total_courses"], 2)
        self.assertEqual(body["categories"], parsed["categories"])
        self.assertEqual(body["all_courses"], parsed["all_courses"])
        self.assertIsNone(body["saved_to"])

        self.assertEqual(
            body["courses"][0],
            {
                "course_code": "0413405",
                "course_name": "Computer and Network Security",
                "grade": "B+",
                "confidence": None,
                "low_confidence": False,
                "warnings": [],
            },
        )
        self.assertEqual(body["courses"][1]["course_code"], "A0434505")
        self.assertIsNone(body["courses"][1]["confidence"])
        self.assertTrue(body["courses"][1]["low_confidence"])
        self.assertEqual(
            body["courses"][1]["warnings"],
            ["Course name is missing.", "Passed course has no grade."],
        )

    async def test_missing_multipart_file_uses_problem_details_validation(self):
        response = await self.client.post(
            "/api/v1/transcripts/parse", data={"save": "false"}
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers["content-type"], "application/problem+json")
        body = response.json()
        self.assertEqual(body["type"], "invalid-request")
        self.assertTrue(any(error["loc"][-1] == "file" for error in body["errors"]))

    async def test_wrong_file_extension_is_rejected_before_parsing(self):
        with patch.object(app_module, "_parse_transcript_bytes") as parser:
            response = await self.client.post(
                "/api/v1/transcripts/parse",
                files={"file": ("transcript.txt", b"not a PDF", "text/plain")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["content-type"], "application/problem+json")
        self.assertEqual(response.json()["type"], "invalid-file-type")
        parser.assert_not_called()

    async def test_invalid_parser_confidence_is_omitted_and_flagged(self):
        parsed = _parsed_transcript()
        parsed["all_courses"] = [dict(parsed["all_courses"][0], confidence=1.5)]

        with patch.object(app_module, "_parse_transcript_bytes", return_value=parsed):
            response = await self.client.post(
                "/api/v1/transcripts/parse",
                files={
                    "file": (
                        "synthetic-transcript.pdf",
                        VALID_PDF.read_bytes(),
                        "application/pdf",
                    )
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        course = response.json()["courses"][0]
        self.assertIsNone(course["confidence"])
        self.assertTrue(course["low_confidence"])
        self.assertIn("Parser confidence is invalid and was omitted.", course["warnings"])


if __name__ == "__main__":
    unittest.main()
