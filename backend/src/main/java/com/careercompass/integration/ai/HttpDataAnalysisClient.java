package com.careercompass.integration.ai;

import com.careercompass.exception.AiServiceException;
import com.careercompass.integration.dto.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

/**
 * The real HTTP implementation of {@link DataAnalysisClient}, speaking
 * {@code docs/contracts/careercompass-ai-internal-v1.yaml}.
 *
 * <p>This class is the anti-corruption boundary. Everything the Python service does differently
 * from the Java domain is translated here and only here:
 *
 * <ul>
 *   <li><b>Naming.</b> The wire is {@code snake_case}; {@link AiWire} holds those shapes so they
 *       never appear in a domain DTO.</li>
 *   <li><b>Scale.</b> The wire carries {@code 0.0..1.0}; Java persists and displays
 *       {@code 0..100}. Converting in one place is what stops {@code 0.82} being rendered as
 *       "0.82%" on one screen and "82%" on another.</li>
 *   <li><b>Enums.</b> The wire is lower case; FR-JS-13 uses "Strong"/"Moderate"/"Weak".</li>
 *   <li><b>Answer keys.</b> The wire gives a zero-based index into an options array; Java stores
 *       an A/B/C/D letter. One off-by-one here would mis-grade every attempt ever taken, so the
 *       conversion is deliberately not spread across the service layer.</li>
 *   <li><b>Errors.</b> RFC 9457 problem documents become {@link AiServiceException} with a
 *       status this backend can actually answer with.</li>
 * </ul>
 *
 * <p>Active only when {@code careercompass.ai-service.use-mock=false}.
 */
@Component
@ConditionalOnProperty(name = "careercompass.ai-service.use-mock", havingValue = "false")
@RequiredArgsConstructor
@Slf4j
public class HttpDataAnalysisClient implements DataAnalysisClient {

    /** Java's quiz tables model exactly four options; a quiz with any other shape cannot be stored. */
    private static final int REQUIRED_OPTION_COUNT = 4;
    private static final List<String> OPTION_LETTERS = List.of("A", "B", "C", "D");

    private final WebClient aiServiceWebClient;
    private final AiServiceProperties aiServiceProperties;

    // ── M1 transcripts ────────────────────────────────────────────────────

    /** {@code POST multipart/form-data /api/v1/transcripts/parse}. */
    @Override
    public TranscriptExtractionResponse extractTranscript(TranscriptExtractionRequest request) {
        if (request == null || request.getFileContent() == null || request.getFileContent().length == 0) {
            throw new IllegalArgumentException("Transcript file content is required.");
        }

        String filename = StringUtils.hasText(request.getOriginalFilename())
                ? request.getOriginalFilename()
                : "transcript.pdf";

        MultipartBodyBuilder multipart = new MultipartBodyBuilder();
        multipart.part("file", new NamedByteArrayResource(request.getFileContent(), filename))
                .contentType(resolveContentType(request.getContentType()));
        // The AI service must not persist student uploads; Java owns review and persistence.
        multipart.part("save", "false");

        AiWire.TranscriptParseResponse wire = call(
                "transcript-extract",
                aiServiceWebClient.post()
                        .uri("/api/v1/transcripts/parse")
                        .contentType(MediaType.MULTIPART_FORM_DATA)
                        .body(BodyInserters.fromMultipartData(multipart.build())),
                AiWire.TranscriptParseResponse.class,
                aiServiceProperties.getTimeouts().getTranscriptSeconds());

        List<TranscriptExtractionResponse.ExtractedCourseDto> courses = new ArrayList<>();
        for (AiWire.CanonicalCourse course : safe(wire == null ? null : wire.courses())) {
            courses.add(TranscriptExtractionResponse.ExtractedCourseDto.builder()
                    .courseCode(course.courseCode())
                    .courseName(course.courseName())
                    .grade(course.grade())
                    // A null confidence means "not scored", which is not the same as zero
                    // confidence and must not be rendered as such.
                    .confidence(course.confidence() == null ? null : BigDecimal.valueOf(course.confidence()))
                    .lowConfidence(course.lowConfidence())
                    .warnings(safe(course.warnings()))
                    .build());
        }
        return TranscriptExtractionResponse.builder().courses(courses).build();
    }

    // ── M2 skill vector ───────────────────────────────────────────────────

    /** {@code POST /api/v1/skill-vector}. */
    @Override
    public SkillVectorResponse buildSkillVector(BuildSkillVectorRequest request) {
        AiWire.SkillVectorRequest body = new AiWire.SkillVectorRequest(
                toWireCourses(request.getCourses()),
                toWireQuizScores(request.getQuizScores()),
                false);

        AiWire.SkillVectorResponse wire = call(
                "skill-vector",
                aiServiceWebClient.post().uri("/api/v1/skill-vector").bodyValue(body),
                AiWire.SkillVectorResponse.class,
                aiServiceProperties.getTimeouts().getSkillVectorSeconds());

        List<SkillScoreDto> skills = new ArrayList<>();
        for (AiWire.SkillVectorItem item : safe(wire == null ? null : wire.skills())) {
            skills.add(SkillScoreDto.builder()
                    .skillId(item.skillId())
                    .skillName(item.label())
                    .score(toPercent(item.proficiency(), "skill-vector.proficiency"))
                    .build());
        }
        return SkillVectorResponse.builder()
                .taxonomyVersion(wire == null ? null : wire.taxonomyVersion())
                .skills(skills)
                .build();
    }

    // ── M3 skill gap ──────────────────────────────────────────────────────

    /** {@code POST /api/v1/skill-gap}. */
    @Override
    public SkillGapAnalysisResponse analyzeSkillGap(SkillGapAnalysisRequest request) {
        AiWire.SkillGapRequest body = new AiWire.SkillGapRequest(
                toWireCourses(request.getCourses()),
                toWireQuizScores(request.getQuizScores()),
                false,
                requireCareerPath(request.getCareerPathName()),
                true,
                request.isIncludeNarrative());

        AiWire.SkillGapResponse wire = call(
                "skill-gap",
                aiServiceWebClient.post().uri("/api/v1/skill-gap").bodyValue(body),
                AiWire.SkillGapResponse.class,
                aiServiceProperties.getTimeouts().getSkillGapSeconds());

        List<SkillGapAnalysisResponse.SkillGapItemDto> gaps = new ArrayList<>();
        for (AiWire.SkillGapItem item : safe(wire == null ? null : wire.skills())) {
            gaps.add(SkillGapAnalysisResponse.SkillGapItemDto.builder()
                    .skillId(item.skillId())
                    .skillName(item.label())
                    .currentScore(toPercent(item.currentLevel(), "skill-gap.current_level"))
                    .targetScore(toPercent(item.requiredProficiency(), "skill-gap.required_proficiency"))
                    .classification(toDisplayClassification(item.classification()))
                    .explanation(null) // per-skill prose is not part of the v1 gap contract
                    .importancePercent(toPercent(item.importance(), "skill-gap.importance"))
                    // Banded by the AI service beside the ontology that justifies the
                    // thresholds. Deriving it here would be a second definition of
                    // "critical", and the two would part company the first time either moved.
                    .demandBand(item.demandBand())
                    .postingCount(item.postingCount())
                    .requiredLevel(item.requiredLevel())
                    .skillType(item.skillType())
                    .priority(item.priority() == null
                            ? null
                            : BigDecimal.valueOf(item.priority()).setScale(4, RoundingMode.HALF_UP))
                    .evidenceSource(item.evidence())
                    .sourceCourses(toCourseEvidence(item.courses()))
                    .build());
        }

        return SkillGapAnalysisResponse.builder()
                .skillGaps(gaps)
                .overallReadinessPercent(readinessPercent(wire))
                .narrative(wire == null ? null : wire.narrative())
                .bandSummary(wire == null ? null : wire.bandSummary())
                .sampleSize(wire == null ? null : wire.sampleSize())
                .marketCapturedAt(wire == null ? null : wire.capturedAt())
                .coursesCounted(wire == null ? null : wire.coursesCounted())
                .syntheticCounted(wire == null ? null : wire.syntheticCounted())
                .coursesSkipped(toSkippedCourses(wire == null ? null : wire.coursesSkipped()))
                .build();
    }

    private static List<SkillGapAnalysisResponse.CourseEvidenceDto> toCourseEvidence(
            List<AiWire.VectorCourseEvidence> courses) {
        List<SkillGapAnalysisResponse.CourseEvidenceDto> evidence = new ArrayList<>();
        for (AiWire.VectorCourseEvidence course : safe(courses)) {
            evidence.add(SkillGapAnalysisResponse.CourseEvidenceDto.builder()
                    .courseCode(course.courseCode())
                    .courseName(course.courseName())
                    .grade(course.grade())
                    .level(course.level())
                    .build());
        }
        return evidence;
    }

    private static List<SkillGapAnalysisResponse.SkippedCourseDto> toSkippedCourses(
            List<AiWire.SkippedCourse> wire) {
        List<SkillGapAnalysisResponse.SkippedCourseDto> skipped = new ArrayList<>();
        for (AiWire.SkippedCourse course : safe(wire)) {
            skipped.add(SkillGapAnalysisResponse.SkippedCourseDto.builder()
                    .courseCode(course.courseCode())
                    .reason(course.reason())
                    .status(course.status())
                    .build());
        }
        return skipped;
    }

    /** {@code GET /api/v1/career-paths/skills}. */
    @Override
    public CareerPathSkillsResponse getCareerPathSkills(String careerPathName) {
        String careerPath = requireCareerPath(careerPathName);

        // A query parameter, not a path segment: two of the nine path names contain a slash
        // ("UI/UX Design"), and encoding that into a segment is normalised or rejected by
        // enough proxies to be a real bug rather than a theoretical one.
        AiWire.CareerPathSkillsResponse wire = call(
                "career-path-skills",
                aiServiceWebClient.get().uri(builder -> builder
                        .path("/api/v1/career-paths/skills")
                        .queryParam("career_path", careerPath)
                        .build()),
                AiWire.CareerPathSkillsResponse.class,
                aiServiceProperties.getTimeouts().getSkillGapSeconds());

        List<CareerPathSkillsResponse.CareerPathSkillDto> skills = new ArrayList<>();
        for (AiWire.CareerPathSkill item : safe(wire == null ? null : wire.skills())) {
            skills.add(CareerPathSkillsResponse.CareerPathSkillDto.builder()
                    .skillId(item.skillId())
                    .label(item.label())
                    .skillType(item.skillType())
                    .postingCount(item.postingCount())
                    .coveragePercent(toPercent(item.coverage(), "career-path-skills.coverage"))
                    .demandBand(item.demandBand())
                    .requiredLevel(item.requiredLevel())
                    .sampleTerms(item.sampleTerms() == null ? List.of() : item.sampleTerms())
                    .build());
        }

        return CareerPathSkillsResponse.builder()
                .careerPath(wire == null || wire.careerPath() == null ? careerPath : wire.careerPath())
                .sampleSize(wire == null ? null : wire.sampleSize())
                .derivedFrom(wire == null ? null : wire.derivedFrom())
                .capturedAt(wire == null ? null : wire.capturedAt())
                .taxonomyVersion(wire == null ? null : wire.taxonomyVersion())
                .total(skills.size())
                .bandTotals(wire == null || wire.bandTotals() == null ? Map.of() : wire.bandTotals())
                .skills(skills)
                .build();
    }

    // ── M4 recommendations ────────────────────────────────────────────────

    /** {@code POST /api/v1/recommendations}. */
    @Override
    public List<RecommendedCourseDto> recommendCourses(CourseRecommendationRequest request) {
        AiWire.RecommendationRequest body = new AiWire.RecommendationRequest(
                toWireCourses(request.getCourses()),
                toWireQuizScores(request.getQuizScores()),
                false,
                requireCareerPath(request.getCareerPathName()),
                false,
                request.getLimit(),
                request.getSkillId(),
                "en");

        AiWire.RecommendationResponse wire = call(
                "course-recommendations",
                aiServiceWebClient.post().uri("/api/v1/recommendations").bodyValue(body),
                AiWire.RecommendationResponse.class,
                aiServiceProperties.getTimeouts().getRecommendationsSeconds());

        List<RecommendedCourseDto> recommendations = new ArrayList<>();
        for (AiWire.RecommendationItem item : safe(wire == null ? null : wire.items())) {
            AiWire.RecommendedCourse course = item.course();
            // The contract guarantees a working link on every item. A row without one would be
            // persisted as an un-clickable card, so treat it as a broken response, not a gap.
            if (course == null || !StringUtils.hasText(course.url()) || !StringUtils.hasText(course.title())) {
                throw new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID",
                        "The AI service returned a recommended course without a title or link.");
            }
            recommendations.add(RecommendedCourseDto.builder()
                    .courseName(course.title())
                    .sourceLink(course.url())
                    .platform(course.platform())
                    .targetedSkillId(item.skillId())
                    .targetedSkillName(item.skillLabel())
                    .explanation(item.explanation())
                    .relevancePercent(toPercent(item.relevance(), "recommendations.relevance"))
                    .build());
        }

        if (wire != null && !safe(wire.skillsWithoutCourses()).isEmpty()) {
            // Not an error: the honest answer to "why is there nothing here for X". Logged so it
            // is visible when catalog coverage, rather than the student, is the limiting factor.
            log.info("AI service reported {} gap(s) the course catalog cannot currently serve",
                    wire.skillsWithoutCourses().size());
        }
        return recommendations;
    }

    // ── M5 quizzes ────────────────────────────────────────────────────────

    /** {@code POST /api/v1/quizzes}. */
    @Override
    public QuizGenerationResponse generateQuiz(QuizGenerationRequest request) {
        if (!StringUtils.hasText(request.getSkillId())) {
            throw new IllegalArgumentException("A canonical skill id is required to generate a quiz.");
        }

        AiWire.QuizRequest body = new AiWire.QuizRequest(
                request.getSkillId(), request.getQuestionCount(), true);

        AiWire.QuizResponse wire = call(
                "quiz-generate",
                aiServiceWebClient.post().uri("/api/v1/quizzes").bodyValue(body),
                AiWire.QuizResponse.class,
                aiServiceProperties.getTimeouts().getQuizSeconds());

        Map<String, AiWire.QuizAnswer> answerKey = wire == null || wire.answerKey() == null
                ? Map.of()
                : wire.answerKey();

        List<QuizGenerationResponse.GeneratedQuizQuestionDto> questions = new ArrayList<>();
        for (AiWire.QuizQuestion question : safe(wire == null ? null : wire.questions())) {
            List<String> options = safe(question.options());
            AiWire.QuizAnswer answer = answerKey.get(question.questionId());

            // Drop rather than guess. A question whose key is missing or out of range cannot be
            // graded correctly, and storing it would silently mark students wrong forever.
            if (options.size() != REQUIRED_OPTION_COUNT || answer == null || answer.correctIndex() == null) {
                log.warn("Dropping quiz question '{}': expected {} options with a resolvable answer key",
                        question.questionId(), REQUIRED_OPTION_COUNT);
                continue;
            }
            int index = answer.correctIndex();
            if (index < 0 || index >= REQUIRED_OPTION_COUNT) {
                log.warn("Dropping quiz question '{}': correct_index {} is outside the options array",
                        question.questionId(), index);
                continue;
            }

            questions.add(QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                    .questionText(question.question())
                    .optionA(options.get(0))
                    .optionB(options.get(1))
                    .optionC(options.get(2))
                    .optionD(options.get(3))
                    // Zero-based index to letter. The one place this conversion happens.
                    .correctOption(OPTION_LETTERS.get(index))
                    .explanation(answer.explanation())
                    .build());
        }

        return QuizGenerationResponse.builder()
                .skillId(wire == null ? request.getSkillId() : wire.skillId())
                .skillLabel(wire == null ? null : wire.skillLabel())
                .questions(questions)
                .build();
    }

    // ── M8 syllabus extraction and approved course maps ─────────────────

    @Override
    public SyllabusExtractionResponse submitSyllabusExtraction(SyllabusExtractionRequest request) {
        if (request == null || request.getFileContent() == null || request.getFileContent().length == 0) {
            throw new IllegalArgumentException("Syllabus file content is required.");
        }

        String filename = StringUtils.hasText(request.getOriginalFilename())
                ? request.getOriginalFilename()
                : "syllabus.pdf";

        MultipartBodyBuilder multipart = new MultipartBodyBuilder();
        multipart.part("file", new NamedByteArrayResource(request.getFileContent(), filename))
                .contentType(resolveContentType(request.getContentType()));
        multipart.part("use_llm", Boolean.toString(request.isUseLlm()));
        multipart.part("force", Boolean.toString(request.isForce()));
        // Content-manager extraction is a proposal. `false` must write neither the production
        // JSON course map nor PostgreSQL course_skills.
        multipart.part("store", Boolean.toString(request.isStoreResults()));

        AiWire.SyllabusExtractionResponse wire = call(
                "syllabus-submit",
                aiServiceWebClient.post()
                        .uri("/api/v1/extractions")
                        .contentType(MediaType.MULTIPART_FORM_DATA)
                        .body(BodyInserters.fromMultipartData(multipart.build())),
                AiWire.SyllabusExtractionResponse.class,
                aiServiceProperties.getTimeouts().getSyllabusSeconds());
        return toSyllabusExtraction(wire);
    }

    @Override
    public SyllabusPreviewResponse previewSyllabusPdf(String filename, String contentType, byte[] content) {
        if (content == null || content.length == 0) {
            throw new IllegalArgumentException("Syllabus file content is required.");
        }

        String safeName = StringUtils.hasText(filename) ? filename : "syllabus.pdf";
        MultipartBodyBuilder multipart = new MultipartBodyBuilder();
        multipart.part("file", new NamedByteArrayResource(content, safeName))
                .contentType(resolveContentType(contentType));

        // The preview runs no model and persists nothing, so the default service
        // deadline is generous enough; no dedicated timeout knob is warranted.
        AiWire.PreviewResponse wire = call(
                "syllabus-preview",
                aiServiceWebClient.post()
                        .uri("/api/v1/syllabi/preview")
                        .contentType(MediaType.MULTIPART_FORM_DATA)
                        .body(BodyInserters.fromMultipartData(multipart.build())),
                AiWire.PreviewResponse.class,
                aiServiceProperties.getTimeoutSeconds());
        if (wire == null) {
            throw new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID",
                    "The AI service returned no syllabus preview.");
        }
        return SyllabusPreviewResponse.builder()
                .courseCode(wire.courseCode())
                .courseTitle(wire.courseTitle())
                .description(wire.description())
                .contentSha256(wire.contentSha256())
                .totalTerms(wire.totalTerms())
                .warnings(wire.warnings() == null ? List.of() : wire.warnings())
                .build();
    }

    @Override
    public SyllabusExtractionResponse getSyllabusExtraction(String extractionId) {
        requireExtractionId(extractionId);
        AiWire.SyllabusExtractionResponse wire = call(
                "syllabus-poll",
                aiServiceWebClient.get().uri("/api/v1/extractions/{id}", extractionId),
                AiWire.SyllabusExtractionResponse.class,
                aiServiceProperties.getTimeouts().getSyllabusSeconds());
        return toSyllabusExtraction(wire);
    }

    @Override
    public SyllabusExtractionResponse cancelSyllabusExtraction(String extractionId) {
        requireExtractionId(extractionId);
        AiWire.SyllabusExtractionResponse wire = call(
                "syllabus-cancel",
                aiServiceWebClient.delete().uri("/api/v1/extractions/{id}", extractionId),
                AiWire.SyllabusExtractionResponse.class,
                aiServiceProperties.getTimeouts().getSyllabusSeconds());
        return toSyllabusExtraction(wire);
    }

    @Override
    public List<TaxonomySkillSuggestion> searchTaxonomySkills(String query, int limit) {
        if (!StringUtils.hasText(query)) {
            return List.of();
        }
        int bounded = Math.max(1, Math.min(50, limit));
        AiWire.TaxonomySearchResponse wire = call(
                "taxonomy-search",
                aiServiceWebClient.get().uri(builder -> builder
                        .path("/api/v1/taxonomy/skills")
                        .queryParam("q", query.trim())
                        .queryParam("limit", bounded)
                        .build()),
                AiWire.TaxonomySearchResponse.class,
                aiServiceProperties.getTimeouts().getTaxonomySeconds());

        return safe(wire == null ? null : wire.items()).stream()
                .map(item -> TaxonomySkillSuggestion.builder()
                        .skillId(item.skillId())
                        .label(item.label())
                        .skillType(item.skillType())
                        .source(item.source())
                        .description(item.description())
                        .taxonomyVersion(item.taxonomyVersion())
                        .build())
                .toList();
    }

    @Override
    public PublishCourseMapResponse publishCourseMap(PublishCourseMapRequest request) {
        if (request == null || !StringUtils.hasText(request.getCourseMapVersion())) {
            throw new IllegalArgumentException("A course map version is required.");
        }

        List<AiWire.ApprovedCourseSkill> skills = safe(request.getSkills()).stream()
                .map(skill -> new AiWire.ApprovedCourseSkill(
                        skill.getSkillId(), skill.getSkillLabel(), skill.getTerm(), skill.getLevel(),
                        skill.getWeight() == null ? null : skill.getWeight().doubleValue(),
                        skill.getEvidenceCount(), safe(skill.getSources()), safe(skill.getEvidence())))
                .toList();

        AiWire.PublishCourseMapRequest body = new AiWire.PublishCourseMapRequest(
                request.getInstitutionCode(), request.getCatalogVersion(), request.getCourseCode(),
                request.getSourceOutcomeId(), request.getTaxonomyVersion(), skills);

        AiWire.PublishCourseMapResponse wire = call(
                "course-map-publish",
                aiServiceWebClient.put()
                        .uri("/api/v1/course-maps/{version}", request.getCourseMapVersion())
                        .bodyValue(body),
                AiWire.PublishCourseMapResponse.class,
                aiServiceProperties.getTimeouts().getPublicationSeconds());

        if (wire == null) {
            throw new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID",
                    "The AI service returned no course-map publication confirmation.");
        }
        return PublishCourseMapResponse.builder()
                .courseMapVersion(wire.courseMapVersion())
                .courseKey(wire.courseKey())
                .courseCode(wire.courseCode())
                .taxonomyVersion(wire.taxonomyVersion())
                .totalSkills(wire.totalSkills())
                .contentSha256(wire.contentSha256())
                .publishedAt(wire.publishedAt())
                .idempotent(wire.idempotent())
                .build();
    }

    // ── M6/M7 job matching — deliberately not in v1 ───────────────────────

    /**
     * Job matching is <b>descoped for this release</b> by owner decision (24 August 2026), so the
     * v1 contract has no job-match operation.
     *
     * <p>This fails loudly rather than calling a path that does not exist. A 404 from the AI
     * service would read as an outage and send somebody debugging connectivity; "not part of
     * this release" is the accurate answer.
     */
    @Override
    public JobMatchResponse scoreJobMatch(JobMatchRequest request) {
        throw new AiServiceException(HttpStatus.NOT_IMPLEMENTED, "AI_CAPABILITY_NOT_IN_SCOPE",
                "AI job matching is not part of the current release. "
                        + "Run with careercompass.ai-service.use-mock=true to demonstrate this flow.");
    }

    @Override
    public MentorMatchResponse matchMentors(MentorMatchRequest request) {
        AiWire.MentorMatchRequest body = new AiWire.MentorMatchRequest(
                request.getCareerPathName(),
                toWireCourses(request.getCourses()),
                toWireQuizScores(request.getQuizScores()),
                request.isIncludeSoft(),
                request.isNarrative(),
                request.getMentors().stream()
                        .map(m -> new AiWire.MentorDto(
                                m.getMentorId(),
                                m.getStudyField(),
                                m.getFieldStartingYear(),
                                m.getExpertiseTerms()))
                        .toList(),
                request.getLimit());

        AiWire.MentorMatchResponse wire = call(
                "mentor-matches",
                aiServiceWebClient.post().uri("/api/v1/mentor-matches").bodyValue(body),
                AiWire.MentorMatchResponse.class,
                aiServiceProperties.getTimeouts().getSkillVectorSeconds());

        if (wire == null) {
            return MentorMatchResponse.builder().build();
        }

        List<MentorMatchResponse.MentorMatchItem> items = new ArrayList<>();
        for (AiWire.MentorMatchItem item : safe(wire.items())) {
            List<MentorMatchResponse.AlignedSkill> alignedSkills = new ArrayList<>();
            for (AiWire.AlignedSkill as : safe(item.alignedSkills())) {
                alignedSkills.add(MentorMatchResponse.AlignedSkill.builder()
                        .skillId(as.skillId())
                        .skillLabel(as.skillLabel())
                        .build());
            }

            items.add(MentorMatchResponse.MentorMatchItem.builder()
                    .mentorId(item.mentorId())
                    .score(toPercent(item.score(), "mentor-match.score"))
                    .signal(item.signal())
                    .alignedSkills(alignedSkills)
                    .gapsAddressed(item.gapsAddressed() != null ? item.gapsAddressed() : 0)
                    .yearsExperience(item.yearsExperience() != null ? item.yearsExperience() : 0)
                    .explanation(item.explanation())
                    .build());
        }

        return MentorMatchResponse.builder()
                .careerPath(wire.careerPath())
                .taxonomyVersion(wire.taxonomyVersion())
                .total(wire.total() != null ? wire.total() : 0)
                .gapsConsidered(wire.gapsConsidered() != null ? wire.gapsConsidered() : 0)
                .items(items)
                .build();
    }

    // ── Transport ─────────────────────────────────────────────────────────

    /**
     * Performs one call with its own deadline and turns every failure mode into an
     * {@link AiServiceException} carrying a status this backend can answer with.
     *
     * <p>The distinction matters operationally: a validation rejection means <em>this backend</em>
     * built a bad request (502 — the student's input was fine), an unreachable service is a 503,
     * and a blown deadline is a 504.
     */
    private <T> T call(String operation, WebClient.RequestHeadersSpec<?> spec, Class<T> responseType,
                       long timeoutSeconds) {
        long deadline = timeoutSeconds > 0 ? timeoutSeconds : aiServiceProperties.getTimeoutSeconds();
        return guard(operation, () -> spec
                .retrieve()
                .onStatus(HttpStatusCode::isError, response -> response
                        .bodyToMono(AiWire.ProblemDetails.class)
                        // A non-conforming or empty error body must still produce a controlled
                        // failure rather than a decoding exception.
                        .onErrorReturn(emptyProblem(response.statusCode()))
                        .defaultIfEmpty(emptyProblem(response.statusCode()))
                        .map(problem -> translate(operation, response.statusCode(), problem)))
                .bodyToMono(responseType)
                .timeout(Duration.ofSeconds(deadline))
                .block());
    }

    private <T> T guard(String operation, Supplier<T> action) {
        try {
            return action.get();
        } catch (AiServiceException ex) {
            throw ex;
        } catch (RuntimeException ex) {
            if (hasCause(ex, TimeoutException.class)) {
                throw new AiServiceException(HttpStatus.GATEWAY_TIMEOUT, "AI_SERVICE_TIMEOUT",
                        "The AI service did not respond in time. Please try again.", ex);
            }
            if (ex instanceof WebClientRequestException || hasCause(ex, java.net.ConnectException.class)) {
                throw new AiServiceException(HttpStatus.SERVICE_UNAVAILABLE, "AI_SERVICE_UNAVAILABLE",
                        "The AI service is not reachable. Please try again shortly.", ex);
            }
            log.error("Unexpected failure calling AI operation '{}'", operation, ex);
            throw new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID",
                    "The AI service returned a response this application could not process.", ex);
        }
    }

    private AiServiceException translate(String operation, HttpStatusCode status, AiWire.ProblemDetails problem) {
        String detail = problem != null && StringUtils.hasText(problem.detail())
                ? problem.detail()
                : "The AI service rejected the request.";

        log.warn("AI operation '{}' failed: status={} type={} detail={}",
                operation, status.value(), problem == null ? null : problem.type(), detail);

        if (status.value() == HttpStatus.NOT_FOUND.value()) {
            String known = problem != null && problem.known() != null && !problem.known().isEmpty()
                    ? " Known values: " + String.join(", ", problem.known()) + "."
                    : "";
            return new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_UNKNOWN_REFERENCE",
                    detail + known);
        }
        if (status.value() == HttpStatus.SERVICE_UNAVAILABLE.value()) {
            return new AiServiceException(HttpStatus.SERVICE_UNAVAILABLE, "AI_SERVICE_UNAVAILABLE", detail);
        }
        if (status.value() == HttpStatus.UNAUTHORIZED.value() || status.value() == HttpStatus.FORBIDDEN.value()) {
            return new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_NOT_AUTHENTICATED",
                    "This backend is not authorised to call the AI service.");
        }
        // 400/413/422 and anything else: this backend sent something the contract rejects. That
        // is our bug, not the student's, so it is a 502 rather than a 400 passed through.
        return new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_REQUEST_REJECTED", detail);
    }

    private static AiWire.ProblemDetails emptyProblem(HttpStatusCode status) {
        return new AiWire.ProblemDetails(null, null, status.value(), null, null);
    }

    private static boolean hasCause(Throwable throwable, Class<? extends Throwable> type) {
        for (Throwable current = throwable; current != null; current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
        }
        return false;
    }

    // ── Mapping helpers ───────────────────────────────────────────────────

    private static List<AiWire.TranscriptCourse> toWireCourses(List<CourseGradeDto> courses) {
        List<AiWire.TranscriptCourse> wire = new ArrayList<>();
        for (CourseGradeDto course : safe(courses)) {
            // course_code is the deterministic join key. Without it the AI service cannot match
            // the row to a syllabus at all, so sending it would quietly shrink the vector.
            if (!StringUtils.hasText(course.getCourseCode())) {
                log.warn("Skipping course '{}' with no course code — it cannot be joined to a skill map",
                        course.getCourseName());
                continue;
            }
            wire.add(new AiWire.TranscriptCourse(
                    course.getCourseCode(), course.getCourseName(), course.getGrade()));
        }
        if (wire.isEmpty()) {
            throw new AiServiceException(HttpStatus.UNPROCESSABLE_ENTITY, "NO_USABLE_COURSES",
                    "None of the stored courses carry a course code, so a skill profile cannot be built. "
                            + "Re-upload the transcript so course codes are captured.");
        }
        return wire;
    }

    /** Java holds quiz scores as percentages; the contract wants fractions. */
    private static Map<String, Double> toWireQuizScores(Map<String, BigDecimal> quizScores) {
        Map<String, Double> wire = new LinkedHashMap<>();
        if (quizScores != null) {
            quizScores.forEach((skillId, score) -> {
                if (StringUtils.hasText(skillId) && score != null) {
                    double fraction = score.doubleValue() / 100.0d;
                    // The contract rejects out-of-range values rather than clamping, because a
                    // clamp would turn a failing score into a perfect one with no signal.
                    wire.put(skillId, Math.max(0.0d, Math.min(1.0d, fraction)));
                }
            });
        }
        return wire;
    }

    /** Contract {@code 0.0..1.0} to Java's {@code 0..100}. */
    private static BigDecimal toPercent(Double fraction, String field) {
        if (fraction == null) {
            return BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
        }
        if (fraction < 0.0d || fraction > 1.0d) {
            throw new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID",
                    "The AI service returned " + field + "=" + fraction
                            + ", which is outside the agreed 0.0-1.0 range.");
        }
        return BigDecimal.valueOf(fraction)
                .multiply(BigDecimal.valueOf(100))
                .setScale(2, RoundingMode.HALF_UP);
    }

    /** Wire {@code weak} to FR-JS-13's {@code Weak}. */
    private static String toDisplayClassification(String wireValue) {
        if (!StringUtils.hasText(wireValue)) {
            return null;
        }
        String lower = wireValue.trim().toLowerCase(Locale.ROOT);
        return Character.toUpperCase(lower.charAt(0)) + lower.substring(1);
    }

    /**
     * Readiness is not a contract field — it is {@code requirements_met / total_requirements}.
     * Computing it here keeps the definition in one place instead of each caller inventing one.
     */
    private static Integer readinessPercent(AiWire.SkillGapResponse wire) {
        if (wire == null || wire.totalRequirements() == null || wire.totalRequirements() <= 0) {
            return 0;
        }
        int met = wire.requirementsMet() == null ? 0 : wire.requirementsMet();
        return BigDecimal.valueOf(met)
                .multiply(BigDecimal.valueOf(100))
                .divide(BigDecimal.valueOf(wire.totalRequirements()), 0, RoundingMode.HALF_UP)
                .intValue();
    }

    private static String requireCareerPath(String careerPathName) {
        if (!StringUtils.hasText(careerPathName)) {
            throw new IllegalArgumentException(
                    "A career path name is required before the AI service can analyse a skill gap.");
        }
        return careerPathName;
    }

    private static void requireExtractionId(String extractionId) {
        if (!StringUtils.hasText(extractionId)) {
            throw new IllegalArgumentException("An extraction id is required.");
        }
    }

    private static SyllabusExtractionResponse toSyllabusExtraction(
            AiWire.SyllabusExtractionResponse wire) {
        if (wire == null) {
            throw new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID",
                    "The AI service returned no syllabus extraction state.");
        }

        SyllabusExtractionResponse.Progress progress = wire.progress() == null ? null
                : SyllabusExtractionResponse.Progress.builder()
                .stage(wire.progress().stage())
                .termsTotal(wire.progress().termsTotal())
                .termsResolved(wire.progress().termsResolved())
                .elapsedSeconds(decimal(wire.progress().elapsedSeconds()))
                .build();

        SyllabusExtractionResponse.Result result = null;
        if (wire.result() != null) {
            List<SyllabusExtractionResponse.ExtractedSkill> skills = safe(wire.result().skills()).stream()
                    .map(HttpDataAnalysisClient::toExtractedSkill)
                    .toList();
            result = SyllabusExtractionResponse.Result.builder()
                    .courseCode(wire.result().courseCode())
                    .totalSkills(wire.result().totalSkills())
                    .taxonomyVersion(wire.result().taxonomyVersion())
                    .skills(skills)
                    .build();
        }

        return SyllabusExtractionResponse.builder()
                .extractionId(wire.extractionId())
                .status(wire.status())
                .courseCode(wire.courseCode())
                .contentSha256(wire.contentSha256())
                .degraded(wire.degraded())
                .progress(progress)
                .result(result)
                .warnings(safe(wire.warnings()))
                .error(wire.error())
                .createdAt(wire.createdAt())
                .finishedAt(wire.finishedAt())
                .build();
    }

    private static SyllabusExtractionResponse.ExtractedSkill toExtractedSkill(
            AiWire.ExtractedSkill wire) {
        SyllabusExtractionResponse.CanonicalSkill canonical = wire.canonical() == null ? null
                : SyllabusExtractionResponse.CanonicalSkill.builder()
                .id(wire.canonical().id())
                .label(wire.canonical().label())
                .taxonomy(wire.canonical().taxonomy())
                .build();

        SyllabusExtractionResponse.Match match = wire.match() == null ? null
                : SyllabusExtractionResponse.Match.builder()
                .originalTerm(wire.match().originalTerm())
                .canonicalId(wire.match().canonicalId())
                .canonicalLabel(wire.match().canonicalLabel())
                .taxonomy(wire.match().taxonomy())
                .taxonomyVersion(wire.match().taxonomyVersion())
                .matchMethod(wire.match().matchMethod())
                .matchScore(decimal(wire.match().matchScore()))
                .reviewStatus(wire.match().reviewStatus())
                .reason(wire.match().reason())
                .candidates(safe(wire.match().candidates()).stream()
                        .map(candidate -> SyllabusExtractionResponse.Candidate.builder()
                                .id(candidate.id())
                                .label(candidate.label())
                                .score(decimal(candidate.score()))
                                .build())
                        .toList())
                .build();

        return SyllabusExtractionResponse.ExtractedSkill.builder()
                .term(wire.term())
                .canonical(canonical)
                .level(wire.level())
                .weight(decimal(wire.weight()))
                .evidenceCount(wire.evidenceCount())
                .sources(safe(wire.sources()))
                .evidence(safe(wire.evidence()))
                .match(match)
                .build();
    }

    private static BigDecimal decimal(Double value) {
        return value == null ? null : BigDecimal.valueOf(value);
    }

    private static <T> List<T> safe(List<T> list) {
        return list == null ? List.of() : list;
    }

    private MediaType resolveContentType(String contentType) {
        if (!StringUtils.hasText(contentType)) {
            return MediaType.APPLICATION_PDF;
        }
        try {
            return MediaType.parseMediaType(contentType);
        } catch (IllegalArgumentException ignored) {
            return MediaType.APPLICATION_PDF;
        }
    }

    /** Gives Spring's multipart writer a filename for an in-memory byte array. */
    private static final class NamedByteArrayResource extends ByteArrayResource {
        private final String filename;

        private NamedByteArrayResource(byte[] bytes, String filename) {
            super(bytes);
            this.filename = filename;
        }

        @Override
        public String getFilename() {
            return filename;
        }
    }
}
