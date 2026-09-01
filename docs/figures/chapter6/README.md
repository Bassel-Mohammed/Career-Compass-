# Chapter 6.3.1 Algorithm Figures and Code Screenshots

Insert each diagram after the algorithm's problem description and before its numbered step table. Insert the corresponding code screenshot after the step table.

Use `Figure 6.x` and `Listing 6.x` as temporary labels, then update `x` to match the final sequence in Word.

## Algorithm 1: Skill Matching Decision Cascade

- Figure: `algorithm-1-skill-matching-cascade.png`
- Suggested caption: `Figure 6.x: Skill matching decision cascade from an extracted phrase to an accepted skill, no match, or human review.`
- Primary code screenshot: `ai-service/src/careercompass/skills/matcher.py`, lines 522-545.
- Optional continuation: `ai-service/src/careercompass/skills/matcher.py`, lines 547-584.
- Suggested listing caption: `Listing 6.x: Reranking thresholds and fallback decisions used by the skill matcher.`

## Algorithm 2: Student Skill Vector

- Figure: `algorithm-2-student-skill-vector.png`
- Suggested caption: `Figure 6.x: Construction of proficiency and coverage values in the student skill vector.`
- Primary code screenshot: `ai-service/src/careercompass/skills/vector.py`, lines 208-250.
- Optional quiz override screenshot: `ai-service/src/careercompass/skills/vector.py`, lines 305-327.
- Suggested listing caption: `Listing 6.x: Separate accumulation of graded proficiency and total evidence coverage.`

## Algorithm 3: Skill Gap and Priority

- Figure: `algorithm-3-skill-gap-priority.png`
- Suggested caption: `Figure 6.x: Skill-gap calculation, classification, and market-demand prioritization.`
- Primary code screenshot: `ai-service/src/careercompass/skills/gap.py`, lines 191-232.
- Optional sorting screenshot: `ai-service/src/careercompass/skills/gap.py`, lines 238-245.
- Suggested listing caption: `Listing 6.x: Calculation of gap, classification, and demand-weighted priority.`

## Algorithm 4: Course Recommendation Ranking

- Figure: `algorithm-4-course-recommendation-ranking.png`
- Suggested caption: `Figure 6.x: Relevance calculation, language adjustment, and final course ranking.`
- Primary code screenshot: `ai-service/src/careercompass/skills/recommend.py`, lines 50-88.
- Optional recommendation assembly screenshot: `ai-service/src/careercompass/skills/recommend.py`, lines 154-179.
- Suggested listing caption: `Listing 6.x: Course relevance and rank-score formulas.`

## Algorithm 5: Quiz Generation, Validation, and Grading

- Figure: `algorithm-5-quiz-generation-grading.png`
- Suggested caption: `Figure 6.x: Separation of model-based quiz generation from deterministic grading.`
- Validation screenshot: `ai-service/src/careercompass/skills/quiz.py`, lines 267-306.
- Generation and key-separation screenshot: `ai-service/src/careercompass/skills/quiz.py`, lines 394-440.
- Backend grading screenshot: `backend/src/main/java/com/careercompass/service/QuizService.java`, lines 139-175.
- Suggested listing captions: `Listing 6.x: Programmatic validation of generated quiz questions.` and `Listing 6.x: Deterministic quiz grading in the backend.`

## Algorithm 6: Mentor Matching Score

- Figure: `algorithm-6-mentor-matching-score.png`
- Suggested caption: `Figure 6.x: Mentor scoring from evidence quality, skill-gap coverage, and seniority.`
- Primary code screenshot: `ai-service/src/careercompass/skills/mentor_matching.py`, lines 226-268.
- Ranking screenshot: `ai-service/src/careercompass/skills/mentor_matching.py`, lines 271-285.
- Suggested listing caption: `Listing 6.x: Mentor score calculation and deterministic tie-breaking.`

## Screenshot Formatting

- Use a light editor theme so the screenshot prints clearly.
- Show line numbers and the source filename.
- Use a monospace font at 14-16 pt.
- Hide the file explorer, terminal, minimap, and unrelated tabs.
- Crop to the listed lines and keep the text readable at normal page width.
- Add a thin grey border after inserting the screenshot into Word.

## Image Generation Prompt Set

The figures were generated with the built-in image generator using a consistent prompt structure: a scientific-educational diagram for a graduation-project report, 16:9 landscape layout, white background, flat academic style, blue and teal process boxes, orange calculation or decision boxes, dark navy arrows, large readable text, and no logos or watermarks.

The six subjects were:

1. Skill matching cascade with exact matching, retrieval, reranking, thresholds, constrained LLM selection, and three outcomes.
2. Student skill vector with separate proficiency and coverage lanes plus quiz replacement.
3. Skill gap, classification, demand-weighted priority, and deterministic ordering.
4. Course relevance, language penalty, gap-priority ranking, and missing-catalogue reporting.
5. Quiz generation, validation, answer-key separation, arithmetic grading, and skill-profile update.
6. Mentor evidence signals, gap coverage, confidence, seniority, scoring, and deterministic tie-breaking.
