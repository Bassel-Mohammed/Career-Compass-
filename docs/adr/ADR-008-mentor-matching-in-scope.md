# ADR-008: Mentor matching is in scope for v1

- Status: Accepted — supersedes [ADR-005](ADR-005-mentor-matching-scope.md)
- Date: 2026-08-24

## Context

ADR-005 deferred AI mentor ranking because the stronger reading of FR-JS-24 had not been
approved and no mentor data existed. The product owner has since asked for mentor matching
explicitly, which settles the first point. The second has not changed and is dealt with below.

The requirement ambiguity ADR-005 recorded is therefore resolved in favour of the stronger
interpretation: FR-JS-24 includes AI-ranked mentor matching, not only mentor viewing.

## Decision

Mentor matching is part of internal API v1, served by `POST /api/v1/mentor-matches` and added
to the contract in **v1.1.0**. The addition is purely additive, so every v1.0.0 request and
response stays valid and no consumer has to change.

Java's existing mentor listing and consultation booking remain unchanged and remain Java's
responsibility, exactly as ADR-005 required. Booking never moves.

**Mentors are ranked against the student's gaps, not their strengths.** A mentor matched to
what a student already knows is the one who can teach them least. Weighting is by `priority`,
which already scales a shortfall by market demand.

### Evidence, and its honest limits

An expert record carries a name, a study field, a starting year and a status. It says nothing
about what the person actually knows, and collecting that is Java-side work outside the scope
this decision covers. Rather than block on it, each mentor is scored from the best evidence
available and **the response states which was used**:

| `signal` | Evidence | Treatment |
|---|---|---|
| `stated` | `expertise_terms` supplied by the caller, resolved onto the taxonomy | Full weight |
| `inferred` | Study field mapped to career paths, whose requirements stand in | Discounted and capped |
| `none` | Study field absent from the reviewed mapping | No skills attributed; experience only |

Two consequences are binding on consumers:

- An `inferred` match **must not** be presented to a student as though the mentor had claimed
  the skill. It is the system's guess, not the mentor's statement.
- Inferred coverage is capped. An inferred profile is the union of a whole career path's
  requirements and would otherwise cover nearly every gap by construction, letting a mentor
  nobody had asked about outrank one who explicitly listed the skills the student lacks. That
  ordering failure was observed before the cap existed and is regression-tested.

The study-field to career-path mapping is a **reviewed data file**, not a fuzzy match. A field
the mapping does not know attributes no skills at all. Admitting ignorance is correct here:
guessing would confidently route a student to a mentor in an unrelated discipline.

## Consequences

- FR-JS-24 can be claimed as implemented, with the `signal` caveat stated rather than hidden.
- Ranking quality is capped by evidence, not by the algorithm. The single highest-value
  improvement is Java collecting mentor expertise terms; the contract already accepts them, so
  that lands without a contract change.
- The mapping file needs review whenever an administrator introduces a study field.
- Scoring is deterministic and involves no model, so it is cheap and repeatable — the same
  request always produces the same ranking, and ties break on mentor id rather than on dict
  ordering.
- Job matching remains out of scope and is unaffected by this decision.
