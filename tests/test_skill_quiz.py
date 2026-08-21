"""
CareerCompass — M5 Quiz Tests

The guarantee worth testing hardest is that a bad question never reaches a
student. A quiz score replaces the grade-inferred proficiency through
``vector.apply_quiz_results``, so a question with two right answers, or a key
pointing at the wrong option, overwrites a real measurement with a false one.

Every test runs against a fake decider. Nothing here may depend on a running
Ollama: a suite that needs a model is a suite nobody runs.

Usage:
    python -m tests.test_skill_quiz
"""

import json
import hashlib
import sys

from careercompass.skills.quiz import (
    DEFAULT_QUESTIONS, MAX_QUESTIONS, OPTION_COUNT,
    generate_quiz, grade_quiz, validate_question,
)
from careercompass.skills.vector import apply_quiz_results

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


class FakeDecider:
    """Returns canned payloads in order; answers its own key on the verify pass."""

    def __init__(self, *payloads, available=True, verify_answers=None):
        self.available = available
        self._payloads = list(payloads)
        self._verify_answers = verify_answers
        self.prompts = []

    def structured(self, prompt, schema):
        self.prompts.append(prompt)
        if "Answer each multiple-choice question" in prompt:
            if self._verify_answers is None:
                return ""
            return json.dumps({"answers": self._verify_answers})
        if not self._payloads:
            return ""
        payload = self._payloads.pop(0)
        return payload if isinstance(payload, str) else json.dumps(payload)


def question(text="What does X do?", options=None, correct=1):
    """One generated question.

    Default options are tagged with a digest of the question text so that two
    different questions get two different answer sets. A fixture that gave every
    question the same four options was exactly the shape `validate_question` now
    rejects — real output did it too, four times over one option set — so the
    fixture has to be at least as realistic as the check.
    """
    if options is None:
        tag = hashlib.md5(text.encode("utf-8")).hexdigest()[:4]
        options = [f"alpha {tag}", f"bravo {tag}", f"charlie {tag}", f"delta {tag}"]
    return {
        "question": text,
        "options": options,
        "correct_index": correct,
    }


def default_options(text="What does X do?"):
    """The options `question(text)` will produce, for assertions."""
    tag = hashlib.md5(text.encode("utf-8")).hexdigest()[:4]
    return [f"alpha {tag}", f"bravo {tag}", f"charlie {tag}", f"delta {tag}"]


def quiz_of(*questions):
    return {"questions": list(questions)}


SKILL = {"id": "custom:docker", "label": "Docker", "description": "Containers."}


# ── validation ─────────────────────────────────────────────────
def test_rejects_malformed_questions():
    cases = [
        ("empty text", question(text="   "), "empty question"),
        ("too few options", question(options=["a", "b", "c"]),
         f"expected {OPTION_COUNT} options, got 3"),
        ("blank option", question(options=["a", "", "c", "d"]), "blank option"),
        ("duplicate options", question(options=["a", "A ", "c", "d"]), "duplicate options"),
        ("index too high", question(correct=4), "correct_index out of range: 4"),
        ("index negative", question(correct=-1), "correct_index out of range: -1"),
        ("index not an int", question(correct="1"), "correct_index out of range: '1'"),
    ]
    for label, raw, expected in cases:
        clean, reason = validate_question(raw, set())
        check(f"{label} rejected", clean, None)
        check(f"{label} reason", reason, expected)


def test_rejects_options_that_mean_the_same_thing():
    """Two right answers marks a student who knows the answer wrong."""
    clean, reason = validate_question(
        question(options=["docker build an image", "docker builds an image",
                          "docker run", "docker pull"]), set())
    check("near-restatement rejected", clean, None)
    check("reason", reason, "options too similar to distinguish")


def test_rejects_a_repeated_question():
    seen = set()
    first, _ = validate_question(question(text="Which command builds?"), seen)
    check("first kept", first is not None, True)
    second, reason = validate_question(question(text="which  COMMAND builds ?"), seen)
    check("repeat rejected", second, None)
    check("reason", reason, "duplicate question")


def test_accepts_a_good_question():
    clean, reason = validate_question(question(), set())
    check("no reason", reason, None)
    check("options preserved", clean["options"], default_options())
    check("index preserved", clean["correct_index"], 1)
    check("explanation optional", clean["explanation"], None)


# ── generation ─────────────────────────────────────────────────
def test_generates_and_splits_the_key_out():
    payload = quiz_of(question("Q1", correct=0), question("Q2", correct=2))
    quiz = generate_quiz(SKILL, 2, decider=FakeDecider(payload), verify=False)

    check("count", quiz["question_count"], 2)
    check("skill id", quiz["skill_id"], "custom:docker")
    # The whole point: nothing in `questions` reveals the answer.
    for item in quiz["questions"]:
        check(f"{item['question_id']} keys",
              sorted(item), ["options", "question", "question_id"])
    check("key covers every question",
          sorted(quiz["answer_key"]), [i["question_id"] for i in quiz["questions"]])
    check("key holds the answer", quiz["answer_key"]["q1"]["correct_answer"],
          default_options("Q1")[0])


def test_drops_bad_questions_and_says_so():
    payload = quiz_of(question("Good"), question("Bad", options=["a", "a", "b", "c"]))
    quiz = generate_quiz(SKILL, 5, decider=FakeDecider(payload), verify=False)
    check("only the good one", quiz["question_count"], 1)
    check("warned", any("duplicate options" in w for w in quiz["warnings"]), True)


def test_rejects_questions_that_re_test_one_fact():
    """Four questions over one option set is one question, asked four times.

    Taken from real generated output. A five-question Docker quiz asked which
    command builds an image, which runs a container, which pushes and which
    pulls — four questions sharing the identical option set
    (docker run / build / push / pull), with the key rotating through positions.
    The SQL quiz did the same with SELECT / INSERT / UPDATE / DELETE. Every
    existing check passed them: duplicate detection compared question text for
    exact equality, and the self-check answers its own recall questions
    correctly. The score then overwrites the student's grade-derived
    proficiency, so a quiz measuring two facts is recorded as measuring five.
    """
    commands = ["docker run", "docker build", "docker push", "docker pull"]
    seen, asked = set(), []

    first, reason = validate_question(
        question("Which command builds an image from a Dockerfile?",
                 options=commands, correct=1), seen, asked)
    check("the first is fine", reason, None)
    check("and is kept", first is not None, True)

    second, reason = validate_question(
        question("Which command runs a container from an existing image?",
                 options=list(reversed(commands)), correct=2), seen, asked)
    check("the second is refused", second, None)
    check("...for re-testing one fact", reason, "same four options as an earlier question")

    # A different fact with different answers is still welcome.
    other, reason = validate_question(
        question("Which Dockerfile instruction sets the base image?",
                 options=["FROM", "RUN", "CMD", "EXPOSE"], correct=0), seen, asked)
    check("a genuinely new question is kept", reason, None)
    check("and returned", other is not None, True)

    # Near-identical wording, even with fresh distractors, is a restatement.
    _, reason = validate_question(
        question("Which Dockerfile instruction sets the base image for a build?",
                 options=["ADD", "COPY", "ENV", "LABEL"], correct=0), seen, asked)
    check("a reworded restatement is refused", reason, "restates an earlier question")

    # Without the `asked` context the check does not run, so callers that
    # validate one question in isolation are unaffected.
    lone, reason = validate_question(
        question("Which command runs a container from an existing image?",
                 options=commands, correct=2), set())
    check("no context, no cross-question check", reason, None)
    check("still validated on its own terms", lone is not None, True)


def test_honours_the_requested_count():
    payload = quiz_of(*[question(f"Q{i}") for i in range(8)])
    quiz = generate_quiz(SKILL, 3, decider=FakeDecider(payload), verify=False)
    check("trimmed to request", quiz["question_count"], 3)

    capped = generate_quiz(SKILL, 99, decider=FakeDecider(payload), verify=False)
    check("capped at the maximum", capped["question_count"], min(MAX_QUESTIONS, 8))


def test_retries_when_the_first_attempt_is_thin():
    # Genuinely different questions, not one question spelt two ways: a retry
    # that returns near-restatements is what the redundancy check is for.
    first = quiz_of(question("Which flag publishes a container port?"))
    second = quiz_of(question("What does a multi-stage build reduce?"),
                     question("Where are image layers cached?"))
    quiz = generate_quiz(SKILL, 3, decider=FakeDecider(first, second), verify=False)
    check("combined across attempts", quiz["question_count"], 3)


def test_unavailable_model_is_fatal():
    """Unlike the gap narrative, half a quiz is not worth returning."""
    try:
        generate_quiz(SKILL, 3, decider=FakeDecider(available=False))
        check("should have raised", True, False)
    except RuntimeError as exc:
        check("explains why", "no LLM is available" in str(exc), True)


def test_nothing_valid_raises_rather_than_returning_empty():
    payload = quiz_of(question(options=["a", "a", "a", "a"]))
    try:
        generate_quiz(SKILL, 3, decider=FakeDecider(payload, payload), verify=False)
        check("should have raised", True, False)
    except RuntimeError as exc:
        check("explains why", "no valid questions" in str(exc), True)


def test_unparsable_output_is_survived():
    quiz = generate_quiz(SKILL, 1, decider=FakeDecider("not json", quiz_of(question())),
                         verify=False)
    check("recovered on retry", quiz["question_count"], 1)
    check("warned", any("unparsable" in w for w in quiz["warnings"]), True)


def test_numeric_options_are_not_false_duplicates():
    """A maths quiz must survive folding.

    "1/2" and "1.2" both folded to "1 2" once, so any question mixing
    fractions with decimals was rejected as having duplicate options. A quiz
    asked for 5 questions on probability came back with 2.
    """
    for options in (["1/8", "3/8", "1/4", "1/2"],
                    ["0.25", "0.5", "1.0", "0.75"],
                    ["1/2", "1.2", "2/1", "2.1"],
                    # 0.5 and 0.50 are deliberately NOT here: they fold to
                    # different strings but are the same number, so
                    # test_equivalent_numbers_are_rejected owns that case.
                    ["0.5", "0.55", "5.0", "50"]):
        clean, reason = validate_question(
            {"question": "Q", "options": options, "correct_index": 1}, set())
        check(f"{options} kept", reason, None)

    # Prose folding must still ignore case, spacing and trailing punctuation.
    duplicate, reason = validate_question(
        {"question": "Q", "options": ["docker build", "Docker  Build!", "c", "d"],
         "correct_index": 0}, set())
    check("prose duplicates still caught", reason, "duplicate options")


def test_equivalent_numbers_are_rejected():
    """Two options that are the same number give a question two right answers.

    Observed in a real generated quiz: "P(rolling a 4 or a 6)?" offered
    1/6, 1/3, 2/6, 3/6 and keyed 2/6. A student answering 1/3 is correct and
    marked wrong, and the false score overwrites their proficiency. No string
    comparison sees this — the options share almost no characters.
    """
    cases = [
        (["1/6", "1/3", "2/6", "3/6"], "fraction pair"),
        (["0.5", "1/2", "0.25", "0.75"], "decimal against fraction"),
        (["50%", "0.5", "0.25", "0.75"], "percentage against decimal"),
        (["3", "3.0", "4", "5"], "integer against decimal"),
    ]
    for options, label in cases:
        clean, reason = validate_question(
            {"question": "Q", "options": options, "correct_index": 1}, set())
        check(f"{label} rejected", reason, "two options are the same number")

    # Distinct numbers, and anything with words in it, must survive.
    for options in (["1/8", "3/8", "1/4", "1/2"],
                    ["0.25", "0.5", "1.0", "0.75"],
                    ["2 hours", "3 hours", "2.0 days", "48 hours"],
                    ["docker run", "docker build", "docker push", "docker pull"]):
        clean, reason = validate_question(
            {"question": "Q", "options": options, "correct_index": 1}, set())
        check(f"{options} kept", reason, None)


def test_short_quiz_is_reported_in_the_warnings():
    """A caller asking for five and getting two should be told, not left to count."""
    payload = quiz_of(question("Good"), question("Bad", options=["a", "a", "b", "c"]))
    quiz = generate_quiz(SKILL, 5, decider=FakeDecider(payload), verify=False)
    check("short", quiz["question_count"] < 5, True)
    check("said so plainly",
          any("of 5 requested" in w for w in quiz["warnings"]), True)
    check("warning comes first", "requested" in quiz["warnings"][0], True)


# ── self-consistency ───────────────────────────────────────────
def test_self_check_drops_questions_the_model_contradicts():
    payload = quiz_of(question("Kept", correct=0), question("Dropped", correct=1))
    # The model answers 0 then 0: it agrees with itself only on the first.
    decider = FakeDecider(payload, verify_answers=[0, 0])
    quiz = generate_quiz(SKILL, 2, decider=decider, verify=True)
    check("one survived", quiz["question_count"], 1)
    check("the consistent one", quiz["questions"][0]["question"], "Kept")
    check("warned", any("failed self-check" in w for w in quiz["warnings"]), True)


def test_self_check_failure_keeps_questions_unverified():
    """An unusable self-check must not silently empty the quiz."""
    payload = quiz_of(question("A"), question("B"))
    quiz = generate_quiz(SKILL, 2, decider=FakeDecider(payload, verify_answers=None),
                         verify=True)
    check("both kept", quiz["question_count"], 2)
    check("said so", any("unverified" in w for w in quiz["warnings"]), True)


# ── grading ────────────────────────────────────────────────────
def make_key():
    payload = quiz_of(question("Q1", correct=0), question("Q2", correct=1),
                      question("Q3", correct=2), question("Q4", correct=3))
    return generate_quiz(SKILL, 4, decider=FakeDecider(payload), verify=False)


def test_grading_is_arithmetic():
    quiz = make_key()
    key = quiz["answer_key"]
    perfect = [{"question_id": q, "answer_index": key[q]["correct_index"]} for q in key]
    result = grade_quiz(key, perfect)
    check("perfect score", result["score"], 1.0)
    check("all correct", result["correct"], 4)
    check("total", result["total"], 4)

    half = [{"question_id": "q1", "answer_index": key["q1"]["correct_index"]},
            {"question_id": "q2", "answer_index": key["q2"]["correct_index"]},
            {"question_id": "q3", "answer_index": 0},
            {"question_id": "q4", "answer_index": 0}]
    check("half", grade_quiz(key, half)["score"], 0.5)


def test_unanswered_counts_as_wrong():
    """Shrinking the denominator would inflate a score that rewrites a profile."""
    quiz = make_key()
    result = grade_quiz(quiz["answer_key"], [])
    check("zero", result["score"], 0.0)
    check("denominator intact", result["total"], 4)
    check("marked unanswered", [r["answered"] for r in result["results"]],
          [False] * 4)


def test_answer_text_is_accepted_and_normalised():
    quiz = make_key()
    key = quiz["answer_key"]
    answers = [{"question_id": q, "answer": f"  {key[q]['correct_answer'].upper()} "}
               for q in key]
    check("text form graded", grade_quiz(key, answers)["score"], 1.0)


def test_grading_is_deterministic():
    quiz = make_key()
    key = quiz["answer_key"]
    answers = [{"question_id": "q1", "answer_index": 0},
               {"question_id": "q2", "answer_index": 3}]
    first = json.dumps(grade_quiz(key, answers), sort_keys=True)
    for _ in range(3):
        check("stable", json.dumps(grade_quiz(key, answers), sort_keys=True), first)


# ── the loop back into M2 ──────────────────────────────────────
def test_score_writes_back_into_the_vector():
    quiz = make_key()
    key = quiz["answer_key"]
    graded = grade_quiz(key, [{"question_id": q, "answer_index": key[q]["correct_index"]}
                              for q in key])

    vector = {
        "taxonomy_version": "1.0", "source": "grades",
        "skills": [{"skill_id": "custom:docker", "label": "Docker",
                    "proficiency": 0.25, "coverage": 1.0, "evidence": "grades",
                    "course_count": 1, "courses": [], "quiz_score": None}],
    }
    apply_quiz_results(vector, {"custom:docker": graded["score"]})
    entry = vector["skills"][0]
    check("quiz replaced the inference", entry["proficiency"], 1.0)
    check("grade value kept", entry["proficiency_from_grades"], 0.25)
    check("evidence", entry["evidence"], "grades+quizzes")
    check("source", vector["source"], "grades+quizzes")


def main():
    test_rejects_malformed_questions()
    test_rejects_options_that_mean_the_same_thing()
    test_rejects_a_repeated_question()
    test_accepts_a_good_question()
    test_generates_and_splits_the_key_out()
    test_drops_bad_questions_and_says_so()
    test_rejects_questions_that_re_test_one_fact()
    test_honours_the_requested_count()
    test_retries_when_the_first_attempt_is_thin()
    test_unavailable_model_is_fatal()
    test_nothing_valid_raises_rather_than_returning_empty()
    test_unparsable_output_is_survived()
    test_numeric_options_are_not_false_duplicates()
    test_equivalent_numbers_are_rejected()
    test_short_quiz_is_reported_in_the_warnings()
    test_self_check_drops_questions_the_model_contradicts()
    test_self_check_failure_keeps_questions_unverified()
    test_grading_is_arithmetic()
    test_unanswered_counts_as_wrong()
    test_answer_text_is_accepted_and_normalised()
    test_grading_is_deterministic()
    test_score_writes_back_into_the_vector()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
