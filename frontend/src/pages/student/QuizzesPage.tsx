import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { Select } from '../../components/Select';
import {
  Card,
  EmptyState,
  PageHeader,
  PrerequisiteState,
  Skeleton,
  Stat,
} from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as quizzesApi from '../../api/quizzes';
import * as transcriptApi from '../../api/transcript';
import { OPTION_LETTERS, formatPercent } from '../../api/format';
import { isAlreadySubmitted, messageFor, prerequisiteFor } from '../../api/errors';
import type { QuizOption, QuizResultResponse, QuizView } from '../../types';

/**
 * FR-JS-17 through FR-JS-21: generate a quiz for one skill, attempt it, and let the result
 * write back into the skill profile.
 *
 * There is no endpoint that lists a student's quizzes, so a quiz exists on this screen only
 * for as long as the page holds its id. Navigating away loses it — which is why generating
 * one is an explicit act rather than something that happens on load.
 */
export function QuizzesPage() {
  const { session } = useAuth();
  const token = session!.token;
  const [params] = useSearchParams();

  // The dashboard links here with a skill preselected; both values come from its payload.
  const [skillId, setSkillId] = useState(params.get('skill') ?? '');
  const [questionCount, setQuestionCount] = useState(5);
  const [quiz, setQuiz] = useState<QuizView | null>(null);
  const [answers, setAnswers] = useState<Record<number, QuizOption>>({});
  const [result, setResult] = useState<QuizResultResponse | null>(null);

  // The dashboard is the source of quizzable skills: `canonicalSkillId` is what the quiz
  // endpoint keys on, and nothing else in the API exposes it.
  const dashboard = useAsync(() => transcriptApi.getSkillDashboard(token), [token]);
  const generate = useAction(quizzesApi.generateQuiz);
  const submit = useAction(quizzesApi.submitQuiz);

  const prereq = prerequisiteFor(dashboard.error, 'JOB_SEEKER') ?? prerequisiteFor(generate.error, 'JOB_SEEKER');
  const quizzable = (dashboard.data?.skills ?? []).filter((s) => s.canonicalSkillId);

  async function handleGenerate() {
    setResult(null);
    setAnswers({});
    const next = await generate.run(token, { skillId, questionCount });
    if (next) setQuiz(next);
  }

  async function handleSubmit() {
    if (!quiz) return;
    const outcome = await submit.run(token, quiz.quizId, {
      answers: Object.entries(answers).map(([questionId, selectedOption]) => ({
        questionId: Number(questionId),
        selectedOption,
      })),
    });
    if (outcome) setResult(outcome);
  }

  const answered = quiz ? quiz.questions.filter((q) => answers[q.questionId]).length : 0;
  const allAnswered = quiz ? answered === quiz.questions.length : false;

  return (
    <AppShell careerPath={dashboard.data?.careerPathTitle}>
      <PageHeader
        title="Skill quizzes"
        lede="A quiz replaces a grade-based estimate with evidence. Your score is written straight back into the skill dashboard."
      />

      {dashboard.loading && <Skeleton rows={3} />}
      {prereq && <PrerequisiteState to={prereq.to} message={prereq.message} />}

      {/* --- 3. Result ---------------------------------------------------- */}
      {result && quiz && <QuizResult result={result} quiz={quiz} onRetake={() => setQuiz(null)} />}

      {/* --- 2. Attempt --------------------------------------------------- */}
      {quiz && !result && (
        <>
          {submit.failed && (
            <Banner
              message={
                isAlreadySubmitted(submit.error)
                  ? 'This quiz has already been submitted. Generate a new one to try again.'
                  : messageFor(submit.error)
              }
            />
          )}

          <Card>
            <div className="quizhead">
              <div>
                <h2 className="section__title">{quiz.courseName}</h2>
                <p className="section__lede">
                  {quiz.questions.length} question{quiz.questions.length === 1 ? '' : 's'}. No
                  timer — answer them all, then submit.
                </p>
              </div>
              <span className="pill">
                {answered} of {quiz.questions.length} answered
              </span>
            </div>

            {/* Fewer questions than requested is normal: the backend validates that each
                has exactly one correct option and drops the ones that do not. */}
            {quiz.questions.length < questionCount && (
              <p className="notice notice--info">
                {questionCount - quiz.questions.length} question
                {questionCount - quiz.questions.length === 1 ? ' was' : 's were'} discarded
                during checking, so this quiz is shorter than you asked for.
              </p>
            )}

            <ol className="questions">
              {quiz.questions.map((question, index) => {
                const options = [
                  question.optionA,
                  question.optionB,
                  question.optionC,
                  question.optionD,
                ];
                return (
                  <li key={question.questionId} className="question">
                    <fieldset>
                      <legend className="question__text">
                        <span className="question__num">Q{index + 1}</span>
                        {question.questionText}
                      </legend>
                      <div className="question__options">
                        {options.map((text, i) => {
                          // The API takes a LETTER, never the index. Converting here, at the
                          // single point where an index exists, is what keeps that true.
                          const letter = OPTION_LETTERS[i];
                          const chosen = answers[question.questionId] === letter;
                          return (
                            <label
                              key={letter}
                              className={`option${chosen ? ' option--on' : ''}`}
                            >
                              <input
                                type="radio"
                                name={`q${question.questionId}`}
                                className="visually-hidden"
                                checked={chosen}
                                disabled={submit.running}
                                onChange={() =>
                                  setAnswers((a) => ({ ...a, [question.questionId]: letter }))
                                }
                              />
                              <span className="option__letter">{letter}</span>
                              <span>{text}</span>
                            </label>
                          );
                        })}
                      </div>
                    </fieldset>
                  </li>
                );
              })}
            </ol>

            <div className="actions">
              <button
                type="button"
                className="button button--primary button--auto"
                onClick={() => void handleSubmit()}
                disabled={submit.running || !allAnswered}
              >
                {submit.running ? 'Marking…' : 'Submit answers'}
              </button>
              {!allAnswered && (
                <span className="actions__hint">
                  Answer every question first — unanswered ones are marked wrong.
                </span>
              )}
            </div>
          </Card>
        </>
      )}

      {/* --- 1. Pick a skill ---------------------------------------------- */}
      {!quiz && !result && !dashboard.loading && !prereq && (
        <Card>
          {generate.failed && !prereq && <Banner message={messageFor(generate.error)} />}

          {quizzable.length === 0 ? (
            <EmptyState
              title="No skills to quiz yet"
              body="Confirm a transcript first — your skills come from your coursework, and a quiz refines one of them."
            />
          ) : (
            <div className="form">
              <Select
                label="Skill to be quizzed on"
                placeholder="Choose a skill"
                value={skillId}
                onChange={(e) => setSkillId(e.target.value)}
                hint="Your weakest skills come first — those are where a quiz changes the most."
                disabled={generate.running}
                options={quizzable.map((s) => ({
                  value: s.canonicalSkillId!,
                  label: `${s.skillName ?? s.canonicalSkillId} — ${formatPercent(s.score)} ${s.classification ?? ''}`.trim(),
                }))}
              />

              <Select
                label="Number of questions"
                value={questionCount}
                onChange={(e) => setQuestionCount(Number(e.target.value))}
                disabled={generate.running}
                options={[3, 5, 8, 10].map((n) => ({ value: n, label: `${n} questions` }))}
              />

              <button
                type="button"
                className="button button--primary"
                onClick={() => void handleGenerate()}
                disabled={generate.running || !skillId}
              >
                {generate.running ? 'Writing your quiz…' : 'Generate quiz'}
              </button>
              {generate.running && (
                <p className="field__hint">
                  Questions are generated and then checked one by one. This usually takes a few
                  seconds.
                </p>
              )}
            </div>
          )}
        </Card>
      )}
    </AppShell>
  );
}

/** FR-JS-19/20/21: the score, the review, and proof that the dashboard moved. */
function QuizResult({
  result,
  quiz,
  onRetake,
}: {
  result: QuizResultResponse;
  quiz: QuizView;
  onRetake: () => void;
}) {
  const byId = new Map(quiz.questions.map((q) => [q.questionId, q]));

  return (
    <>
      <div className="grid grid--stats">
        <Stat
          label="Score"
          value={formatPercent(result.score)}
          hint={`${result.correctCount} of ${result.totalQuestions} correct`}
        />
        <Stat
          label="Overall readiness"
          value={formatPercent(result.updatedDashboard.overallReadinessPercent)}
          hint="updated just now"
        />
      </div>

      {/* The submit response carries the whole recomputed dashboard, so the write-back is
          shown here as fact rather than promised and fetched again. */}
      <p className="notice notice--info">
        <strong>Your skill dashboard has been updated.</strong> This skill is now scored from
        what you demonstrated rather than estimated from your grades.{' '}
        <Link to="/dashboard">See the dashboard</Link>.
      </p>

      <Card>
        <h2 className="section__title">Review</h2>
        <ol className="questions">
          {result.questionResults.map((answer) => {
            const question = byId.get(answer.questionId);
            const options = question
              ? [question.optionA, question.optionB, question.optionC, question.optionD]
              : [];
            return (
              <li key={answer.questionId} className="question">
                <p className="question__text">{question?.questionText ?? 'Question'}</p>
                <div className="question__options">
                  {options.map((text, i) => {
                    const letter = OPTION_LETTERS[i];
                    const isCorrect = answer.correctOption === letter;
                    const isChosen = answer.selectedOption === letter;
                    const tone = isCorrect
                      ? ' option--correct'
                      : isChosen
                        ? ' option--wrong'
                        : '';
                    return (
                      <div key={letter} className={`option option--static${tone}`}>
                        <span className="option__letter">{letter}</span>
                        <span>{text}</span>
                        {isCorrect && <span className="option__tag">Correct answer</span>}
                        {isChosen && !isCorrect && (
                          <span className="option__tag">You chose this</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ol>
      </Card>

      <div className="actions">
        <button type="button" className="button button--secondary button--auto" onClick={onRetake}>
          Quiz another skill
        </button>
      </div>
    </>
  );
}
