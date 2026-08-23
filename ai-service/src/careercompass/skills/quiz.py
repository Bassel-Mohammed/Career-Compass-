"""
CareerCompass — M5: Quiz generation and grading

Generates a multiple-choice quiz for one skill, so a student can demonstrate
proficiency the transcript cannot show. The score replaces the grade-inferred
value in the skill vector through ``vector.apply_quiz_results``, which is what
makes correctness here a data-integrity concern rather than a cosmetic one: a
confidently wrong answer key overwrites a real measurement with a false one.

Two halves, deliberately separated:

    generate_quiz   the model writes questions; every one is validated, and
                    an invalid question is dropped rather than repaired
    grade_quiz      pure arithmetic, no model — FR-JS-19 requires grading not
                    be model-based, and a model that grades can disagree with
                    its own key

This service holds no quiz state. It returns the questions *and* the answer
key to its caller, which stores them, shows the student only the questions,
and grades the submission. `API_DESIGN.md`'s concern is the key reaching the
browser; a server-to-server response does not. That keeps this service
stateless, as `/skill-vector` and `/skill-gap` already are.
"""

import re
import unicodedata
from fractions import Fraction

from careercompass.skills.reranker import _char_grams, _dice

OPTION_COUNT = 4
MAX_QUESTIONS = 10
DEFAULT_QUESTIONS = 5

# Two options this close are effectively the same answer, and a question with
# two right answers scores the student wrongly.
#
# Measured with the character-trigram Dice overlap the lexical reranker
# already uses — no model, no download, no VRAM. An embedding check would
# catch more ("builds an image" against "creates an image"), but it needs a
# second model loaded beside Ollama, which does not fit this card, and the
# cheap check catches the common case: options that differ only in wording,
# punctuation or a trailing qualifier.
DISTRACTOR_SIMILARITY = 0.80

# Two *questions* this close are testing the same fact. Lower than the
# within-question bar because the failure looks different: the options do not
# have to be reworded, they are often character-for-character the same set.
#
# Measured on real output: a five-question Docker quiz asked "which command
# builds an image", "which runs a container", "which pushes", "which pulls" —
# four questions over one identical option set (docker run / build / push /
# pull), question-text overlap 0.57-0.86. The SQL quiz did the same with
# SELECT / INSERT / UPDATE / DELETE and rotated the correct index 0, 1, 2, 3 in
# order. Both passed every existing check, because duplicate detection only ever
# compared question *text* for exact equality, and the self-check happily
# answers its own recall questions correctly.
#
# A five-question quiz measuring two facts is not a five-question quiz, and the
# score overwrites the student's grade-derived proficiency.
# Deliberately conservative. The identical-option-set rule above is the precise
# signal and catches every Docker/SQL pair measured; this one is the backstop for
# a restatement that varies its distractors, so it is set where it cannot reject
# a well-formed quiz. The Git quiz measured on real output peaked at 0.55 between
# any two of its questions, and the Docker pairs this must catch ran 0.68-0.86.
QUESTION_SIMILARITY = 0.70


def _option_signature(options: list) -> frozenset:
    """The set of answers a question offers, order and wording folded."""
    return frozenset(_normalise(option) for option in options)


def _restates_an_earlier_question(text: str, options: list, asked: list):
    """Whether this question re-asks one already accepted, or None.

    Two signals, either of which is enough:

    * the same four options. Order and which one is keyed do not matter — a
      student who knows the answer to one knows the answer to all of them.
    * question text that overlaps an earlier one past the threshold.
    """
    signature = _option_signature(options)
    grams = _char_grams(text)
    for earlier_text, earlier_signature, earlier_grams in asked:
        if signature == earlier_signature:
            return "same four options as an earlier question"
        if _dice(grams, earlier_grams) > QUESTION_SIMILARITY:
            return "restates an earlier question"
    return None

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": OPTION_COUNT,
                        "maxItems": OPTION_COUNT,
                    },
                    "correct_index": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": OPTION_COUNT - 1,
                    },
                    "explanation": {"type": "string"},
                },
                "required": ["question", "options", "correct_index"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

PROMPT = """Write {count} multiple-choice questions that test practical \
knowledge of one skill.

Skill: {label}
{description}

Rules:
- Each question has exactly {options} options and exactly one correct answer.
- Test whether someone can use the skill, not whether they memorised a \
definition. Prefer questions about what a command does, which approach fits a \
situation, or what a piece of code or configuration produces.
- The three wrong options must be plausible to someone who half-knows the \
subject, and each must be clearly wrong to someone who knows it. Do not use \
"all of the above", "none of the above", or joke answers.
- Options must be mutually exclusive. Never write two options that mean the \
same thing.
- Vary which position holds the correct answer.
- Keep each option under 120 characters.

Return only the JSON object the schema requires."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": OPTION_COUNT - 1},
        }
    },
    "required": ["answers"],
    "additionalProperties": False,
}

VERIFY_PROMPT = """Answer each multiple-choice question. Reply with the index \
of the correct option for each, 0-based, in order.

{questions}

Return only the JSON object the schema requires."""


# Characters that carry meaning inside an answer and must survive folding.
# Stripping them collapsed "1/2" and "1.2" onto the same string, so a maths
# question with fractions and decimals among its options was rejected as
# having duplicate options and silently dropped — a quiz asked for 5 questions
# came back with 2. Prose folding still works: "Docker  Build!" and
# "docker build" agree, because only the separators are collapsed.
MEANINGFUL_CHARS = r"a-z0-9.,/%+\-^=<>"


def _normalise(text: str) -> str:
    """Fold a string for comparison: case, accents, spacing and punctuation.

    Deliberately keeps the characters that distinguish one numeric or symbolic
    answer from another. Two options must only compare equal when they really
    are the same answer.
    """
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(rf"[^{MEANINGFUL_CHARS}]+", " ", text.lower())
    # A trailing separator is punctuation, not part of the answer: "0.5." and
    # "0.5" are the same, but "0.5" and "0.50" are not.
    text = re.sub(r"(?<=\w)[.,]+(?=\s|$)", "", text)
    return re.sub(r"\s+", " ", text).strip()


_NUMERIC_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:/\s*([+-]?\d+(?:\.\d+)?))?\s*(%?)\s*$")


def _as_number(option: str):
    """The value of an option that is purely a number, else None.

    Handles integers, decimals, fractions and percentages. Anything with words
    in it is left alone: "2 hours" is a label, not a quantity to compare.
    """
    match = _NUMERIC_RE.match(str(option or ""))
    if not match:
        return None
    numerator, denominator, percent = match.groups()
    try:
        value = Fraction(numerator)
        if denominator is not None:
            divisor = Fraction(denominator)
            if divisor == 0:
                return None
            value /= divisor
        if percent:
            value /= 100
        return value
    except (ValueError, ZeroDivisionError):
        return None


def _equivalent_numbers(options: list) -> bool:
    """Whether two options are the same number written differently.

    A string check cannot see this: "1/3" and "2/6" share no characters worth
    counting, yet a question offering both has two correct answers and marks a
    student who knows the answer wrong. Observed in a real generated quiz on
    probability theory.
    """
    seen = set()
    for option in options:
        value = _as_number(option)
        if value is None:
            continue
        if value in seen:
            return True
        seen.add(value)
    return False


def _similar_options(options: list) -> bool:
    """Whether any two options are near-restatements of each other.

    Exact duplicates are already caught by normalisation; this catches
    "docker build image" against "docker builds an image", where a student who
    knows the answer can still be marked wrong.
    """
    grams = [_char_grams(option) for option in options]
    for i in range(len(grams)):
        for j in range(i + 1, len(grams)):
            if _dice(grams[i], grams[j]) > DISTRACTOR_SIMILARITY:
                return True
    return False


def validate_question(question: dict, seen: set, asked: list = None):
    """
    Return ``(clean_question, reason)``; exactly one is None.

    Structure is guaranteed by the schema, so these checks exist for what a
    schema cannot express: an answer index that points at nothing meaningful,
    two options that say the same thing, the same question twice — and, given
    ``asked``, a question that re-tests a fact an accepted question already
    covers.

    Args:
        question: one raw generated question.
        seen: normalised texts already accepted, for exact-duplicate rejection.
        asked: ``(text, option signature, char grams)`` per accepted question.
            Omitted, no cross-question check runs and only this question's own
            internal consistency is enforced.
    """
    text = str(question.get("question") or "").strip()
    if not text:
        return None, "empty question"

    options = [str(option or "").strip() for option in question.get("options") or []]
    if len(options) != OPTION_COUNT:
        return None, f"expected {OPTION_COUNT} options, got {len(options)}"
    if any(not option for option in options):
        return None, "blank option"

    if len({_normalise(option) for option in options}) != OPTION_COUNT:
        return None, "duplicate options"

    index = question.get("correct_index")
    if not isinstance(index, int) or not 0 <= index < OPTION_COUNT:
        return None, f"correct_index out of range: {index!r}"

    key = _normalise(text)
    if key in seen:
        return None, "duplicate question"

    if _equivalent_numbers(options):
        return None, "two options are the same number"

    if _similar_options(options):
        return None, "options too similar to distinguish"

    if asked is not None:
        repeats = _restates_an_earlier_question(text, options, asked)
        if repeats:
            return None, repeats
        asked.append((text, _option_signature(options), _char_grams(text)))

    seen.add(key)
    return {
        "question": text,
        "options": options,
        "correct_index": index,
        "explanation": str(question.get("explanation") or "").strip() or None,
    }, None


def _render(questions: list) -> str:
    lines = []
    for n, item in enumerate(questions, start=1):
        lines.append(f"{n}. {item['question']}")
        for i, option in enumerate(item["options"]):
            lines.append(f"   {i}. {option}")
    return "\n".join(lines)


def _self_consistent(questions: list, decider) -> tuple:
    """Drop questions the model will not answer the way it keyed them.

    Every other check here is structural — four options, a valid index, no
    duplicates — and none of them can tell whether a key is *correct*. Asking
    the model to answer its own questions without the key is the cheapest
    available signal that it was not guessing, and it is the only defence
    against a confidently wrong key overwriting a student's proficiency.
    """
    import json

    text = decider.structured(VERIFY_PROMPT.format(questions=_render(questions)),
                              VERIFY_SCHEMA)
    try:
        answers = json.loads(text or "").get("answers") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        return questions, ["self-check unavailable; questions kept unverified"]

    if len(answers) != len(questions):
        return questions, ["self-check returned the wrong number of answers; "
                           "questions kept unverified"]

    kept, warnings = [], []
    for item, answer in zip(questions, answers):
        if answer == item["correct_index"]:
            kept.append(item)
        else:
            warnings.append(f"dropped (failed self-check): {item['question'][:60]}")
    return kept, warnings


def generate_quiz(skill: dict, question_count: int = DEFAULT_QUESTIONS, *,
                  decider=None, verify: bool = True, attempts: int = 3) -> dict:
    """
    Generate a validated multiple-choice quiz for one skill.

    Args:
        skill: ``{"id": ..., "label": ..., "description": ...}``. The
            description anchors the model on the right subject; without it a
            bare label like "Python" invites definition questions.
        question_count: how many to return, capped at ``MAX_QUESTIONS``.
        decider: an object with ``.available`` and ``.structured(prompt, schema)``.
            Defaults to the configured LLM.
        verify: run the self-consistency pass.
        attempts: how many times to ask before giving up. Validation drops bad
            questions rather than repairing them, so a short quiz is retried.

    Returns:
        ``{skill_id, skill_label, question_count, questions, answer_key,
        warnings}``. ``questions`` carries no answers; ``answer_key`` maps
        question_id to the correct index.

    Raises:
        RuntimeError: the model is unavailable, or produced nothing valid.
    """
    import json

    if decider is None:
        from careercompass.skills.llm import LLMDecider
        decider = LLMDecider()

    if not getattr(decider, "available", False):
        raise RuntimeError("no LLM is available; a quiz cannot be generated")

    wanted = max(1, min(int(question_count or DEFAULT_QUESTIONS), MAX_QUESTIONS))
    description = (skill.get("description") or "").strip()
    # Over-ask generously. Validation drops questions rather than repairing
    # them, and the self-check drops more, so asking for exactly `wanted`
    # reliably returns fewer. Half again, minimum three spare.
    prompt = PROMPT.format(
        count=min(MAX_QUESTIONS + 5, wanted + max(3, wanted // 2)),
        label=skill.get("label") or skill.get("id"),
        description=f"What it means: {description}" if description else "",
        options=OPTION_COUNT,
    )

    seen, asked, questions, warnings = set(), [], [], []
    for _ in range(max(1, attempts)):
        if len(questions) >= wanted:
            break
        try:
            payload = json.loads(decider.structured(prompt, QUIZ_SCHEMA) or "")
        except (json.JSONDecodeError, TypeError):
            warnings.append("model returned unparsable output")
            continue

        for raw in payload.get("questions") or []:
            if len(questions) >= wanted:
                break
            clean, reason = validate_question(raw, seen, asked)
            if clean is None:
                warnings.append(f"dropped ({reason})")
            else:
                questions.append(clean)

    if verify and questions:
        questions, verify_warnings = _self_consistent(questions, decider)
        warnings.extend(verify_warnings)

    if not questions:
        raise RuntimeError(
            "no valid questions were produced; " + ("; ".join(warnings[:3]) or "no detail"))

    # Say so plainly. A caller asking for five and receiving two should not
    # have to count the response or read a list of per-question drops to
    # notice, and the count is what a UI paginates against.
    if len(questions) < wanted:
        warnings.insert(0, f"returned {len(questions)} of {wanted} requested; "
                           f"the rest failed validation after {attempts} attempts")

    payload, answer_key = [], {}
    for n, item in enumerate(questions, start=1):
        question_id = f"q{n}"
        payload.append({
            "question_id": question_id,
            "question": item["question"],
            "options": item["options"],
        })
        answer_key[question_id] = {
            "correct_index": item["correct_index"],
            "correct_answer": item["options"][item["correct_index"]],
            "explanation": item["explanation"],
        }

    return {
        "skill_id": skill.get("id"),
        "skill_label": skill.get("label"),
        "question_count": len(payload),
        "questions": payload,
        "answer_key": answer_key,
        "warnings": warnings,
    }


def grade_quiz(answer_key: dict, answers: list) -> dict:
    """
    Grade a submission. Arithmetic only — no model is involved.

    An answer may be given as ``answer_index`` or as ``answer`` text; the text
    form is compared on the normalised string, so whitespace and casing from a
    form submission do not fail a correct answer.

    Unanswered questions count as wrong rather than being skipped: the score
    feeds ``apply_quiz_results``, which treats it as a measurement of the
    skill, and silently shrinking the denominator would inflate it.
    """
    given = {}
    for answer in answers or []:
        question_id = answer.get("question_id")
        if question_id:
            given[question_id] = answer

    results, correct = [], 0
    for question_id, key in answer_key.items():
        answer = given.get(question_id)
        index = answer.get("answer_index") if answer else None
        text = answer.get("answer") if answer else None

        if isinstance(index, int):
            is_correct = index == key["correct_index"]
        elif text is not None:
            is_correct = _normalise(text) == _normalise(key["correct_answer"])
        else:
            is_correct = False

        correct += is_correct
        results.append({
            "question_id": question_id,
            "correct": is_correct,
            "answered": answer is not None,
            "expected": key["correct_answer"],
            "explanation": key.get("explanation"),
        })

    total = len(answer_key)
    return {
        "score": round(correct / total, 4) if total else 0.0,
        "correct": correct,
        "total": total,
        "results": results,
    }
