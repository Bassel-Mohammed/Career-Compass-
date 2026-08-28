package com.careercompass.system;

import com.careercompass.entity.*;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.*;
import com.careercompass.repository.*;
import com.careercompass.security.Role;
import com.careercompass.security.jwt.JwtProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import javax.crypto.SecretKey;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.Date;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Master end-to-end system test for CareerCompass.
 *
 * This is a single, ordered, stateful journey through every actor and every core
 * functionality described in the project report, run against a real Spring Boot application
 * context and a real H2 database (not mocked repositories) - only DataAnalysisClient (the
 * Data Analyses Layer, which Mohammed's Python service will eventually provide) is mocked,
 * exactly as requested, since that service does not exist yet.
 *
 * Why one file, in order: the tests build on each other the same way a real user's session
 * would - a job seeker must register before they can update their profile; a transcript must
 * be confirmed before a skill dashboard exists; a quiz must be generated before it can be
 * submitted. TestMethodOrder + TestInstance(PER_CLASS) lets each @Test method be its own
 * clearly-commented, independently-readable test case while sharing state (tokens, ids) with
 * the ones before it, rather than repeating setup in every method or collapsing everything
 * into one giant untestable method.
 *
 * Registration rules verified here, matching the report exactly:
 * - Job Seeker and Employer: self-register via a public endpoint (FR-JS-01, FR-EMP-01)
 * - Administrator: no registration endpoint exists at all; provisioned directly in the
 *   database (see AuthService's Javadoc) - verified by seeding one directly here and by
 *   confirming no /api/auth/admins/register route exists
 * - Content Manager and Expert: created BY an Administrator (FR-SA-02, FR-EX-01), never
 *   self-registered - verified by confirming no register route exists for either, and by
 *   having the seeded Admin create both before they can log in
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles({"dev", "test"})
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class CareerCompassSystemTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private ObjectMapper objectMapper;

    @Autowired private AdministratorRepository administratorRepository;
    @Autowired private UniversityRepository universityRepository;
    @Autowired private StudyFieldRepository studyFieldRepository;
    @Autowired private CareerPathRepository careerPathRepository;
    @Autowired private AcademicRecordRepository academicRecordRepository;
    @Autowired private JobseekerSkillRepository jobseekerSkillRepository;
    @Autowired private SkillRepository skillRepository;
    @Autowired private QuizRepository quizRepository;
    @Autowired private JobSeekerRepository jobSeekerRepository;
    @Autowired private PasswordEncoder passwordEncoder;
    @Autowired private JwtProperties jwtProperties;

    /** The one and only mock in this test - everything else is the real application. */
    @MockBean
    private DataAnalysisClient dataAnalysisClient;

    // Shared state carried across the ordered steps, exactly like a real user session would.
    private static Integer universityId;
    private static Integer studyFieldId;
    private static Integer careerPathId;

    private static String jobSeekerToken;
    private static Integer jobSeekerId;

    private static String employerToken;
    private static Integer employerId;
    private static Integer jobId;

    private static String secondEmployerToken;

    private static String contentManagerToken;
    private static Integer contentManagerId;
    private static Integer contentManagerOutcomeId;
    private static Long contentManagerDraftSkillId;
    private static Long contentManagerDraftRowVersion;
    private static Long contentManagerDraftRevision;

    private static String expertToken;
    private static Integer expertId;

    private static String secondExpertToken;

    private static String adminToken;

    private static Integer quizId;
    private static Integer quizQuestion1Id;
    private static Integer quizQuestion2Id;

    private static Integer appointmentId;

    // State used only by the requirement-coverage tests added below. The "disposable"
    // reference data exists so that FR-SA-09/10 (update and delete a career path) can be
    // exercised without touching the seeded "Software Engineer" path the whole journey
    // depends on.
    private static Integer disposableStudyFieldId;
    private static Integer disposableCareerPathId;
    private static Integer disposableJobId;
    private static Integer rejectedAppointmentId;

    // =====================================================================================
    // SHARED AI STUBS - the Data Analyses Layer's canonical responses for this journey
    // =====================================================================================

    /**
     * Canonical skill ids, as the AI service's taxonomy would supply them. Quizzes and the
     * FR-JS-20/21 write-back join on these, never on the display label.
     */
    private static final String DATA_STRUCTURES_SKILL_ID = "custom:data-structures";
    private static final String OPERATING_SYSTEMS_SKILL_ID = "custom:operating-systems";

    /** A graded quiz replaces the grade-inferred score for that skill; others keep theirs. */
    private static BigDecimal effectiveScore(java.util.Map<String, BigDecimal> quizScores,
                                             String skillId, int gradeBasedScore) {
        if (quizScores != null && quizScores.containsKey(skillId)) {
            return quizScores.get(skillId);
        }
        return BigDecimal.valueOf(gradeBasedScore);
    }

    /**
     * Re-applies every DataAnalysisClient stub before EVERY test method.
     *
     * This is required, not merely tidy: Spring Boot resets {@code @MockBean} mocks after each
     * test method ({@code MockReset.AFTER} is the default), so a stub declared inside one
     * @Test is already gone by the time the next @Test in the @Order sequence runs. Because
     * this journey deliberately shares state across methods, several later steps re-enter the
     * same AI-backed code paths as earlier ones - a dashboard re-fetch, a quiz submission
     * (which recomputes the dashboard), an expert viewing that dashboard, an employer scoring
     * candidates - and would otherwise receive `null` from an un-stubbed mock and fail with a
     * NullPointerException / HTTP 500 that says nothing about the feature under test.
     *
     * Keeping the stubs here rather than duplicating them per method also means the mocked
     * Data Analyses Layer has exactly one definition: "Data Structures 90 (Strong),
     * Operating Systems 55 (Weak), 72% ready" is the single scenario the whole journey is
     * written against, and each test's assertions are read against these values.
     */
    @BeforeEach
    void stubDataAnalysisLayer() {
        // Module 1 (Section 5.3.3): transcript extraction - 2 courses, 1 flagged low-confidence.
        when(dataAnalysisClient.extractTranscript(any(TranscriptExtractionRequest.class)))
                .thenReturn(TranscriptExtractionResponse.builder()
                        .courses(List.of(
                                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                                        .courseCode("CS201").courseName("Data Structures")
                                        .grade("A").lowConfidence(false).build(),
                                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                                        .courseCode("CS310").courseName("Operating Systems")
                                        .grade("C").lowConfidence(true).build()
                        ))
                        .build());

        // Module 2: grade-based skill vector, with graded quiz evidence folded in exactly as
        // the real service does. Operating Systems = 55 from grades is what Phase 6's quiz
        // write-back later replaces with the quiz-derived 50 (FR-JS-20), so this stub has to
        // honour `quizScores` rather than return a constant — otherwise the single most
        // important behaviour in the quiz feature would be asserted against a fixture that
        // could never change.
        when(dataAnalysisClient.buildSkillVector(any(BuildSkillVectorRequest.class)))
                .thenAnswer(inv -> {
                    BuildSkillVectorRequest req = inv.getArgument(0);
                    return SkillVectorResponse.builder()
                            .skills(List.of(
                                    SkillScoreDto.builder()
                                            .skillId(DATA_STRUCTURES_SKILL_ID).skillName("Data Structures")
                                            .score(effectiveScore(req.getQuizScores(), DATA_STRUCTURES_SKILL_ID, 90))
                                            .build(),
                                    SkillScoreDto.builder()
                                            .skillId(OPERATING_SYSTEMS_SKILL_ID).skillName("Operating Systems")
                                            .score(effectiveScore(req.getQuizScores(), OPERATING_SYSTEMS_SKILL_ID, 55))
                                            .build()))
                            .build();
                });

        // Module 3: skill-gap analysis. "Operating Systems" is the one Weak skill, which is
        // what Phase 5's course recommendations are generated against.
        when(dataAnalysisClient.analyzeSkillGap(any(SkillGapAnalysisRequest.class)))
                .thenAnswer(inv -> {
                    SkillGapAnalysisRequest req = inv.getArgument(0);
                    BigDecimal osScore = effectiveScore(req.getQuizScores(), OPERATING_SYSTEMS_SKILL_ID, 55);
                    return SkillGapAnalysisResponse.builder()
                            .overallReadinessPercent(72)
                            .skillGaps(List.of(
                                    SkillGapAnalysisResponse.SkillGapItemDto.builder()
                                            .skillId(DATA_STRUCTURES_SKILL_ID)
                                            .skillName("Data Structures").currentScore(BigDecimal.valueOf(90))
                                            .targetScore(BigDecimal.valueOf(75)).classification("Strong")
                                            .explanation("Well above target.").build(),
                                    SkillGapAnalysisResponse.SkillGapItemDto.builder()
                                            .skillId(OPERATING_SYSTEMS_SKILL_ID)
                                            .skillName("Operating Systems").currentScore(osScore)
                                            .targetScore(BigDecimal.valueOf(75)).classification("Weak")
                                            .explanation("Below target level.").build()))
                            .build();
                });

        // Module 4: one course recommendation, targeting the Weak skill above.
        when(dataAnalysisClient.recommendCourses(any(CourseRecommendationRequest.class)))
                .thenReturn(List.of(RecommendedCourseDto.builder()
                        .courseName("Operating Systems Fundamentals")
                        .sourceLink("https://example.com/os-fundamentals")
                        .targetedSkillId(OPERATING_SYSTEMS_SKILL_ID)
                        .targetedSkillName("Operating Systems")
                        .explanation("Directly targets your weakest skill.")
                        .build()));

        // Module 5: a 2-question quiz whose correct answers are A and B - Phase 6 answers
        // A and A, so exactly one is correct and the score must come out as 50%.
        when(dataAnalysisClient.generateQuiz(any(QuizGenerationRequest.class)))
                .thenReturn(QuizGenerationResponse.builder()
                        .skillId(OPERATING_SYSTEMS_SKILL_ID)
                        .skillLabel("Operating Systems")
                        .questions(List.of(
                                QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                                        .questionText("What does a process control block store?")
                                        .optionA("Process state").optionB("Only the PID")
                                        .optionC("Nothing").optionD("Source code")
                                        .correctOption("A").build(),
                                QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                                        .questionText("What is a deadlock?")
                                        .optionA("A fast lock").optionB("Circular resource wait")
                                        .optionC("A crashed process").optionD("A file lock")
                                        .correctOption("B").build()
                        ))
                        .build());

        // Module 6: job matching, used from BOTH directions in Phase 8 (job seeker's matches
        // and the employer's candidate list). The .0 keeps this a decimal in the serialized
        // JSON, matching the is(82.0) assertion rather than an integer 82.
        when(dataAnalysisClient.scoreJobMatch(any(JobMatchRequest.class)))
                .thenReturn(JobMatchResponse.builder()
                        .matchScore(BigDecimal.valueOf(82.0))
                        .explanation("Strong overlap in required skills.")
                        .build());

        // Module 8: proposal-only syllabus extraction for the content-manager review
        // workflow. The submission completes synchronously with two matched skills, so the
        // upload lands in READY_FOR_REVIEW immediately and the review phases below can drive
        // accept → publish against deterministic ids.
        when(dataAnalysisClient.submitSyllabusExtraction(any(SyllabusExtractionRequest.class)))
                .thenAnswer(inv -> SyllabusExtractionResponse.builder()
                        .extractionId("ext-sys-test-1")
                        .status("succeeded")
                        .contentSha256("a".repeat(64))
                        .warnings(java.util.Collections.emptyList())
                        .result(SyllabusExtractionResponse.Result.builder()
                                .courseCode("CS201")
                                .totalSkills(2)
                                .taxonomyVersion("taxonomy-2026.08")
                                .skills(List.of(
                                        extractedSyllabusSkill("object-oriented programming",
                                                "skill:oop", "Object-oriented programming",
                                                "intermediate", "0.9000"),
                                        extractedSyllabusSkill("unit testing",
                                                "skill:unit-testing", "Unit testing",
                                                "beginner", "0.7000")))
                                .build())
                        .build());
        when(dataAnalysisClient.getSyllabusExtraction(any()))
                .thenAnswer(inv -> SyllabusExtractionResponse.builder()
                        .extractionId(inv.getArgument(0))
                        .status("succeeded")
                        .warnings(java.util.Collections.emptyList())
                        .build());
        when(dataAnalysisClient.cancelSyllabusExtraction(any()))
                .thenAnswer(inv -> SyllabusExtractionResponse.builder()
                        .extractionId(inv.getArgument(0))
                        .status("cancelled")
                        .warnings(java.util.Collections.emptyList())
                        .build());
        when(dataAnalysisClient.searchTaxonomySkills(any(), any(int.class)))
                .thenReturn(List.of(
                        TaxonomySkillSuggestion.builder()
                                .skillId("skill:docker").label("Docker").skillType("tool")
                                .source("taxonomy-2026.08").taxonomyVersion("taxonomy-2026.08")
                                .build(),
                        TaxonomySkillSuggestion.builder()
                                .skillId("skill:oop").label("Object-oriented programming")
                                .skillType("skill").source("taxonomy-2026.08")
                                .taxonomyVersion("taxonomy-2026.08")
                                .build()));
        when(dataAnalysisClient.publishCourseMap(any(PublishCourseMapRequest.class)))
                .thenAnswer(inv -> {
                    PublishCourseMapRequest req = inv.getArgument(0);
                    return PublishCourseMapResponse.builder()
                            .courseMapVersion(req.getCourseMapVersion())
                            .courseKey(req.getInstitutionCode() + "|" + req.getCatalogVersion()
                                    + "|" + req.getCourseCode())
                            .courseCode(req.getCourseCode())
                            .taxonomyVersion(req.getTaxonomyVersion())
                            .totalSkills(req.getSkills() == null ? 0 : req.getSkills().size())
                            .contentSha256("b".repeat(64))
                            .publishedAt("2026-08-25T00:00:00Z")
                            .idempotent(false)
                            .build();
                });

        // Mentor matching stub
        when(dataAnalysisClient.matchMentors(any(MentorMatchRequest.class)))
                .thenAnswer(inv -> {
                    MentorMatchRequest req = inv.getArgument(0);
                    if (req.getMentors() == null || req.getMentors().isEmpty()) {
                        return MentorMatchResponse.builder().build();
                    }
                    List<MentorMatchResponse.MentorMatchItem> items = req.getMentors().stream()
                            .limit(req.getLimit())
                            .map(m -> MentorMatchResponse.MentorMatchItem.builder()
                                    .mentorId(m.getMentorId())
                                    .score(new java.math.BigDecimal("85.0"))
                                    .gapsAddressed(2)
                                    .explanation("Mock explanation")
                                    .build())
                            .toList();
                    return MentorMatchResponse.builder()
                            .careerPath(req.getCareerPathName())
                            .taxonomyVersion("mock-v1")
                            .total(items.size())
                            .gapsConsidered(3)
                            .items(items)
                            .build();
                });
    }

    /** One matched skill inside the Module 8 stub proposal above. */
    private static SyllabusExtractionResponse.ExtractedSkill extractedSyllabusSkill(
            String term, String skillId, String label, String level, String weight) {
        return SyllabusExtractionResponse.ExtractedSkill.builder()
                .term(term)
                .canonical(SyllabusExtractionResponse.CanonicalSkill.builder()
                        .id(skillId).label(label).taxonomy("taxonomy-2026.08").build())
                .level(level)
                .weight(new BigDecimal(weight))
                .evidenceCount(2)
                .sources(List.of("clo"))
                .evidence(List.of(java.util.Map.of("source", "clo", "text", "Students can " + term)))
                .match(SyllabusExtractionResponse.Match.builder()
                        .originalTerm(term)
                        .canonicalId(skillId)
                        .canonicalLabel(label)
                        .matchMethod("lexical")
                        .matchScore(new BigDecimal("0.9500"))
                        .reviewStatus("accepted")
                        .reason("Exact alias match")
                        .candidates(java.util.Collections.emptyList())
                        .build())
                .build();
    }

    // =====================================================================================
    // PHASE 0 - Reference data & Administrator provisioning
    // =====================================================================================

    // Purpose: seed a University, StudyField, and CareerPath directly via repositories,
    // simulating admin-managed reference data (FR-SA-07/08) already existing in the system
    // before any user interacts with it.
    @Test
    @Order(1)
    void phase0_referenceDataCanBeSeeded() {
        University university = universityRepository.save(
                University.builder().universityName("Middle East University").build());
        StudyField studyField = studyFieldRepository.save(
                StudyField.builder().fieldName("Computer Science").build());
        CareerPath careerPath = careerPathRepository.save(CareerPath.builder()
                .title("Software Engineer")
                .description("Build and ship reliable software.")
                .studyFields(java.util.Set.of(studyField))
                .build());

        universityId = university.getUniversityId();
        studyFieldId = studyField.getStudyFieldId();
        careerPathId = careerPath.getCareerPathId();

        assertThat(universityId).isNotNull();
        assertThat(studyFieldId).isNotNull();
        assertThat(careerPathId).isNotNull();
    }

    // Purpose: Administrator accounts have NO self-registration flow anywhere in the system
    // (a deliberate design decision - see AuthService's Javadoc) - confirmed here by seeding
    // one directly via the repository, exactly as a real deployment's migration/seed script
    // would, rather than through any API endpoint.
    @Test
    @Order(2)
    void phase0_administratorIsProvisionedDirectlyNotViaApi() {
        Administrator admin = administratorRepository.save(Administrator.builder()
                .firstName("Basil")
                .lastName("Admin")
                .email("admin@careercompass.local")
                .passwordHash(passwordEncoder.encode("adminPass123"))
                .build());

        assertThat(admin.getAdminId()).isNotNull();
        assertThat(administratorRepository.existsByEmail("admin@careercompass.local")).isTrue();
    }

    // Purpose: there is no public "/api/auth/admins/register" endpoint - confirms the
    // no-self-registration design decision is actually enforced by routing, not just by
    // convention/documentation.
    @Test
    @Order(3)
    void phase0_noRegistrationEndpointExistsForAdministrators() throws Exception {
        mockMvc.perform(post("/api/auth/admins/register")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isNotFound());
    }

    // Purpose: the seeded Administrator CAN log in through the normal /api/auth/admins/login
    // endpoint - login works even though registration deliberately does not exist.
    @Test
    @Order(4)
    void phase0_administratorCanLoginAfterBeingSeeded() throws Exception {
        String body = "{\"email\":\"admin@careercompass.local\",\"password\":\"adminPass123\"}";

        MvcResult result = mockMvc.perform(post("/api/auth/admins/login")
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role", is("ADMIN")))
                .andReturn();

        adminToken = readToken(result);
        assertThat(adminToken).isNotBlank();
    }

    // Purpose: FR-SA-07 - the Administrator adds a study field through the administrative API.
    // ST-01 seeded reference data straight through the repositories because later phases need
    // the ids before any actor exists; this test exercises the endpoint the requirement
    // actually describes. A separate, disposable field is created so nothing the journey
    // depends on is disturbed.
    @Test
    @Order(5)
    void phase0_adminCanCreateStudyFieldThroughTheApi() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/admin/study-fields")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType("application/json")
                        .content("{\"fieldName\":\"Information Systems\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.fieldName", is("Information Systems")))
                .andReturn();

        disposableStudyFieldId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("studyFieldId").asInt();
        assertThat(disposableStudyFieldId).isNotNull();
    }

    // Purpose: FR-SA-08 - the Administrator creates a career path title within a study field.
    @Test
    @Order(6)
    void phase0_adminCanCreateCareerPathThroughTheApi() throws Exception {
        String body = String.format(
                "{\"title\":\"Data Engineer\",\"description\":\"Build and operate data pipelines.\"," +
                "\"studyFieldIds\":[%d]}", disposableStudyFieldId);

        MvcResult result = mockMvc.perform(post("/api/admin/career-paths")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title", is("Data Engineer")))
                .andExpect(jsonPath("$.studyFields[0].studyFieldId", is(disposableStudyFieldId)))
                .andReturn();

        disposableCareerPathId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("careerPathId").asInt();
    }

    // Purpose: FR-SA-09 - the Administrator updates an existing career path title.
    @Test
    @Order(7)
    void phase0_adminCanUpdateCareerPathTitle() throws Exception {
        mockMvc.perform(put("/api/admin/career-paths/" + disposableCareerPathId)
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType("application/json")
                        .content("{\"title\":\"Senior Data Engineer\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.careerPathId", is(disposableCareerPathId)))
                .andExpect(jsonPath("$.title", is("Senior Data Engineer")))
                // the description was not sent, so it must survive the partial update untouched
                .andExpect(jsonPath("$.description", is("Build and operate data pipelines.")));
    }

    // Purpose: FR-SA-10 - the Administrator deletes a career path. The listing is checked
    // afterwards to confirm the correct path was removed and the seeded "Software Engineer"
    // path - which the Job Seeker selects in ST-10 - was left alone.
    @Test
    @Order(8)
    void phase0_adminCanDeleteCareerPath() throws Exception {
        mockMvc.perform(delete("/api/admin/career-paths/" + disposableCareerPathId)
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/admin/career-paths")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.careerPathId == " + disposableCareerPathId + ")]", hasSize(0)))
                .andExpect(jsonPath("$[?(@.careerPathId == " + careerPathId + ")]", hasSize(1)));
    }

    // =====================================================================================
    // PHASE 1 - Job Seeker: self-registration, login, profile
    // =====================================================================================

    // Purpose: FR-JS-01 - a Job Seeker CAN self-register via a public endpoint (unlike Admin/
    // Content Manager/Expert), receiving a JWT immediately on success.
    @Test
    @Order(10)
    void phase1_jobSeekerCanRegisterThemselves() throws Exception {
        String body = "{\"firstName\":\"Sara\",\"lastName\":\"Ahmad\",\"email\":\"sara@example.com\",\"password\":\"password123\"}";

        MvcResult result = mockMvc.perform(post("/api/auth/job-seekers/register")
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.role", is("JOB_SEEKER")))
                .andReturn();

        JsonNode json = objectMapper.readTree(result.getResponse().getContentAsString());
        jobSeekerToken = json.get("token").asText();
        jobSeekerId = json.get("userId").asInt();

        assertThat(jobSeekerToken).isNotBlank();
        assertThat(jobSeekerId).isNotNull();
    }

    // Purpose: FR-JS-01 uniqueness - registering a SECOND time with the same email is
    // rejected with 409 CONFLICT, not silently creating a duplicate account.
    @Test
    @Order(11)
    void phase1_jobSeekerRegistration_rejectsDuplicateEmail() throws Exception {
        String body = "{\"firstName\":\"Sara\",\"lastName\":\"Ahmad\",\"email\":\"sara@example.com\",\"password\":\"password123\"}";

        mockMvc.perform(post("/api/auth/job-seekers/register")
                        .contentType("application/json").content(body))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error", is("EMAIL_ALREADY_EXISTS")));
    }

    // Purpose: FR-JS-02 - the same Job Seeker can log in with the credentials they registered.
    @Test
    @Order(12)
    void phase1_jobSeekerCanLogin() throws Exception {
        String body = "{\"email\":\"sara@example.com\",\"password\":\"password123\"}";

        mockMvc.perform(post("/api/auth/job-seekers/login")
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").exists());
    }

    // Purpose: a wrong password is rejected with 401 and a generic message (no hint about
    // whether the email exists), never leaking account-enumeration information.
    @Test
    @Order(13)
    void phase1_jobSeekerLogin_rejectsWrongPassword() throws Exception {
        String body = "{\"email\":\"sara@example.com\",\"password\":\"wrongPassword\"}";

        mockMvc.perform(post("/api/auth/job-seekers/login")
                        .contentType("application/json").content(body))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error", is("INVALID_CREDENTIALS")));
    }

    // Purpose: FR-JS-06 - a freshly registered Job Seeker can view their own profile.
    @Test
    @Order(14)
    void phase1_jobSeekerCanViewOwnProfile() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email", is("sara@example.com")));
    }

    // Purpose: FR-JS-07/09 - the Job Seeker can update their profile, selecting their
    // university, study field, and desired career path in one request.
    @Test
    @Order(15)
    void phase1_jobSeekerCanUpdateProfile_selectingUniversityStudyFieldAndCareerPath() throws Exception {
        String body = String.format(
                "{\"universityId\":%d,\"studyFieldId\":%d,\"careerPathId\":%d}",
                universityId, studyFieldId, careerPathId);

        mockMvc.perform(put("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.careerPathTitle", is("Software Engineer")))
                .andExpect(jsonPath("$.studyFieldId", is(studyFieldId)));
    }

    // Purpose: NFR-SEC-04 - profile update is rejected outright with no Authorization header;
    // there is no way to update ANY profile without a valid token.
    @Test
    @Order(16)
    void phase1_profileUpdate_rejectedWithoutToken() throws Exception {
        mockMvc.perform(put("/api/job-seekers/me")
                        .contentType("application/json").content("{}"))
                .andExpect(status().isUnauthorized());
    }

    // Purpose: FR-JS-04 / FR-CM-03 / FR-EMP-04 - the 30-minute inactivity window. The window
    // is expressed as the expiry claim inside the JWT rather than as server-side session
    // state, so the requirement has two halves and both are checked here: the configured
    // policy is 30 minutes, and a token whose expiry has passed is genuinely refused.
    //
    // The expired tokens are minted here rather than waiting 30 minutes, using the same
    // signing key and claim structure JwtTokenProvider uses, with the expiry set in the past.
    // One is built per actor so this is real evidence for all three requirements, not an
    // argument by analogy from a single role.
    //
    // Logout itself (FR-JS-03 / FR-CM-02 / FR-EMP-03) is covered in Phase 4B, which is the
    // first point in the journey where all five actor types exist to log out.
    @Test
    @Order(18)
    void phase1_expiredTokenIsRejected_enforcingTheInactivityWindow() throws Exception {
        assertThat(jwtProperties.getExpirationMinutes()).isEqualTo(30);

        record ActorEndpoint(Role role, String email, String protectedPath) {}

        List<ActorEndpoint> actors = List.of(
                new ActorEndpoint(Role.JOB_SEEKER, "sara@example.com", "/api/job-seekers/me"),
                new ActorEndpoint(Role.EMPLOYER, "hr@atlas.example.com", "/api/employers/me"),
                new ActorEndpoint(Role.CONTENT_MANAGER, "nour@meu.edu.jo", "/api/content-managers/me/learning-outcomes")
        );

        for (ActorEndpoint actor : actors) {
            String expiredToken = mintExpiredToken(actor.role(), actor.email());

            mockMvc.perform(get(actor.protectedPath())
                            .header("Authorization", "Bearer " + expiredToken))
                    .andExpect(status().isUnauthorized());
        }
    }

    // =====================================================================================
    // PHASE 2 - Employer: self-registration, login, job posting
    // =====================================================================================

    // Purpose: FR-EMP-01 - an Employer CAN self-register, same as a Job Seeker.
    @Test
    @Order(20)
    void phase2_employerCanRegisterThemselves() throws Exception {
        String body = "{\"companyName\":\"Atlas Systems\",\"industry\":\"Software\",\"email\":\"hr@atlas.example.com\"," +
                "\"password\":\"password123\",\"companyDescription\":\"We build distributed systems.\"}";

        MvcResult result = mockMvc.perform(post("/api/auth/employers/register")
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.role", is("EMPLOYER")))
                .andReturn();

        JsonNode json = objectMapper.readTree(result.getResponse().getContentAsString());
        employerToken = json.get("token").asText();
        employerId = json.get("userId").asInt();
    }

    // Purpose: a second, separate Employer is registered here so later tests can prove
    // ownership enforcement (Employer A must never be able to act on Employer B's data).
    @Test
    @Order(21)
    void phase2_secondEmployerCanRegister_forOwnershipTestsLater() throws Exception {
        String body = "{\"companyName\":\"Northwind Labs\",\"industry\":\"Software\",\"email\":\"hr@northwind.example.com\"," +
                "\"password\":\"password123\"}";

        MvcResult result = mockMvc.perform(post("/api/auth/employers/register")
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andReturn();

        secondEmployerToken = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("token").asText();
    }

    // Purpose: FR-EMP-07/08 - the Employer can post a job with a title, description, and
    // required skills, scoped to a study field.
    @Test
    @Order(22)
    void phase2_employerCanPostAJob() throws Exception {
        String body = String.format(
                "{\"title\":\"Backend Engineer\",\"description\":\"Build and maintain our core APIs.\"," +
                "\"requiredSkills\":\"Java, SQL, Data Structures\",\"studyFieldId\":%d}", studyFieldId);

        MvcResult result = mockMvc.perform(post("/api/employers/me/jobs")
                        .header("Authorization", "Bearer " + employerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title", is("Backend Engineer")))
                .andReturn();

        jobId = objectMapper.readTree(result.getResponse().getContentAsString()).get("jobId").asInt();
        assertThat(jobId).isNotNull();
    }

    // Purpose: FR-EMP-09 - the owning Employer can update their own job posting.
    @Test
    @Order(23)
    void phase2_employerCanUpdateOwnJob() throws Exception {
        String body = "{\"title\":\"Senior Backend Engineer\",\"description\":\"Updated description.\",\"requiredSkills\":\"Java, SQL\"}";

        mockMvc.perform(put("/api/employers/me/jobs/" + jobId)
                        .header("Authorization", "Bearer " + employerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title", is("Senior Backend Engineer")));
    }

    // Purpose: NFR-SEC-04 ownership - a DIFFERENT employer (who did not post this job) is
    // rejected with 403 FORBIDDEN when trying to update it, even though they are a fully
    // authenticated, valid Employer.
    @Test
    @Order(24)
    void phase2_differentEmployerCannotUpdateAnotherEmployersJob() throws Exception {
        String body = "{\"title\":\"Hijacked\",\"description\":\"Attempted takeover.\"}";

        mockMvc.perform(put("/api/employers/me/jobs/" + jobId)
                        .header("Authorization", "Bearer " + secondEmployerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isForbidden());
    }

    // Purpose: NFR-SEC-04 role separation - a Job Seeker's token cannot be used to access any
    // Employer-only endpoint, confirming SecurityConfig's role rule is enforced both ways.
    @Test
    @Order(25)
    void phase2_jobSeekerTokenCannotAccessEmployerEndpoints() throws Exception {
        mockMvc.perform(get("/api/employers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isForbidden());
    }

    // Purpose: FR-EMP-02 / FR-EMP-14 - the Employer logs in through the dedicated login
    // endpoint. Every other Employer test in this suite uses the token issued at registration,
    // so without this case the login route itself is never called.
    @Test
    @Order(26)
    void phase2_employerCanLoginThroughTheDedicatedEndpoint() throws Exception {
        String body = "{\"email\":\"hr@atlas.example.com\",\"password\":\"password123\"}";

        MvcResult result = mockMvc.perform(post("/api/auth/employers/login")
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role", is("EMPLOYER")))
                .andExpect(jsonPath("$.userId", is(employerId)))
                .andReturn();

        // The token from login must be usable in place of the registration token.
        String loginToken = readToken(result);
        mockMvc.perform(get("/api/employers/me")
                        .header("Authorization", "Bearer " + loginToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.employerId", is(employerId)));
    }

    // Purpose: FR-EMP-06 - the Employer updates their company profile. Only the industry and
    // description are changed; the company name is left out of the request to confirm the
    // update is partial rather than overwriting unsent fields with null.
    @Test
    @Order(27)
    void phase2_employerCanUpdateCompanyProfile() throws Exception {
        String body = "{\"industry\":\"Cloud Infrastructure\"," +
                "\"companyDescription\":\"We build and operate distributed systems at scale.\"}";

        mockMvc.perform(put("/api/employers/me")
                        .header("Authorization", "Bearer " + employerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.industry", is("Cloud Infrastructure")))
                .andExpect(jsonPath("$.companyDescription", containsString("distributed systems")))
                .andExpect(jsonPath("$.companyName", is("Atlas Systems")));
    }

    // Purpose: FR-EMP-10 - the Employer deletes a job posting. A throwaway vacancy is posted
    // and removed rather than deleting the "Backend Engineer" job, because Phase 8 matches
    // the Job Seeker against that job; the listing afterwards proves the right one went.
    @Test
    @Order(28)
    void phase2_employerCanDeleteAJobPosting() throws Exception {
        String body = String.format(
                "{\"title\":\"Temporary Listing\",\"description\":\"Posted only to be deleted.\"," +
                "\"requiredSkills\":\"Java\",\"studyFieldId\":%d}", studyFieldId);

        MvcResult result = mockMvc.perform(post("/api/employers/me/jobs")
                        .header("Authorization", "Bearer " + employerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andReturn();

        disposableJobId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("jobId").asInt();

        mockMvc.perform(delete("/api/employers/me/jobs/" + disposableJobId)
                        .header("Authorization", "Bearer " + employerToken))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/employers/me/jobs")
                        .header("Authorization", "Bearer " + employerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].jobId", is(jobId)));
    }

    // =====================================================================================
    // PHASE 3 - Content Manager & Expert: admin-created only, never self-registered
    // =====================================================================================

    // Purpose: confirms no self-registration route exists for Content Managers either -
    // FR-CM-01 explicitly says their password is set "by the system administrator".
    @Test
    @Order(30)
    void phase3_noRegistrationEndpointExistsForContentManagers() throws Exception {
        mockMvc.perform(post("/api/auth/content-managers/register")
                        .contentType("application/json").content("{}"))
                .andExpect(status().isNotFound());
    }

    // Purpose: confirms no self-registration route exists for Experts either - FR-EX-01 says
    // their login is "assigned by the system administrator".
    @Test
    @Order(31)
    void phase3_noRegistrationEndpointExistsForExperts() throws Exception {
        mockMvc.perform(post("/api/auth/experts/register")
                        .contentType("application/json").content("{}"))
                .andExpect(status().isNotFound());
    }

    // Purpose: FR-SA-02/03 - the Administrator creates a Content Manager account, assigning
    // their university and setting their initial password directly.
    @Test
    @Order(32)
    void phase3_adminCreatesContentManager() throws Exception {
        String body = String.format(
                "{\"firstName\":\"Nour\",\"lastName\":\"Khaled\",\"email\":\"nour@meu.edu.jo\"," +
                "\"initialPassword\":\"cmPassword123\",\"universityId\":%d,\"studyFieldId\":%d}",
                universityId, studyFieldId);

        MvcResult result = mockMvc.perform(post("/api/admin/content-managers")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andReturn();

        contentManagerId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("contentManagerId").asInt();
    }

    // Purpose: the Content Manager created by the admin can now log in - they never needed
    // (and never had) a self-registration step.
    @Test
    @Order(33)
    void phase3_contentManagerCanLoginAfterAdminCreatesAccount() throws Exception {
        String body = "{\"email\":\"nour@meu.edu.jo\",\"password\":\"cmPassword123\"}";

        MvcResult result = mockMvc.perform(post("/api/auth/content-managers/login")
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andReturn();

        contentManagerToken = readToken(result);
        assertThat(contentManagerToken).isNotBlank();
    }

    // Purpose: FR-SA-01 - an Administrator creates an Expert account, this time also
    // assigning their study field up front so mentor-matching (FR-JS-24) works later.
    @Test
    @Order(34)
    void phase3_adminCreatesExpert() throws Exception {
        String body = String.format(
                "{\"firstName\":\"David\",\"lastName\":\"Okafor\",\"email\":\"david@example.com\"," +
                "\"initialPassword\":\"expertPass123\",\"studyFieldId\":%d,\"fieldStartingYear\":2010}",
                studyFieldId);

        MvcResult result = mockMvc.perform(post("/api/admin/experts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andReturn();

        expertId = objectMapper.readTree(result.getResponse().getContentAsString()).get("expertId").asInt();
    }

    // Purpose: a second Expert is created here purely so a later test can prove that experts
    // cannot view a job seeker's data without a genuine consultation relationship.
    @Test
    @Order(35)
    void phase3_secondExpertCreated_forAccessControlTestLater() throws Exception {
        String body = "{\"firstName\":\"Priya\",\"lastName\":\"Nair\",\"email\":\"priya@example.com\"," +
                "\"initialPassword\":\"expertPass123\",\"fieldStartingYear\":2015}";

        mockMvc.perform(post("/api/admin/experts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated());

        MvcResult loginResult = mockMvc.perform(post("/api/auth/experts/login")
                        .contentType("application/json")
                        .content("{\"email\":\"priya@example.com\",\"password\":\"expertPass123\"}"))
                .andExpect(status().isOk())
                .andReturn();

        secondExpertToken = readToken(loginResult);
    }

    // Purpose: the Expert created by the admin can log in and activate themselves for
    // consulting (FR-EX-02) - new experts default to Inactive until they opt in.
    @Test
    @Order(36)
    void phase3_expertCanLoginAndActivateForConsulting() throws Exception {
        MvcResult loginResult = mockMvc.perform(post("/api/auth/experts/login")
                        .contentType("application/json")
                        .content("{\"email\":\"david@example.com\",\"password\":\"expertPass123\"}"))
                .andExpect(status().isOk())
                .andReturn();

        expertToken = readToken(loginResult);

        mockMvc.perform(patch("/api/experts/me/status/activate")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusName", is("Active")));
    }

    // Purpose: FR-CM-05 - the Content Manager selects the study field they teach in.
    @Test
    @Order(37)
    void phase3_contentManagerCanSelectStudyField() throws Exception {
        String body = String.format("{\"studyFieldId\":%d}", studyFieldId);

        mockMvc.perform(put("/api/content-managers/me/study-field")
                        .header("Authorization", "Bearer " + contentManagerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk());
    }

    // Purpose: FR-CM-04 - the content manager uploads a syllabus PDF with its qualified course
    // identity; the (mocked) extraction completes synchronously, so the row is immediately
    // READY_FOR_REVIEW and never visible to students until published.
    @Test
    @Order(38)
    void phase3_contentManagerCanUploadLearningOutcomePdf() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "cs201-outcomes.pdf", "application/pdf", "fake pdf content".getBytes());

        MvcResult result = mockMvc.perform(multipart("/api/content-managers/me/learning-outcomes")
                        .file(file)
                        .param("courseCode", "CS201")
                        .param("catalogVersion", "2025-2026")
                        .param("courseName", "Data Structures")
                        .param("description", "Covers arrays, lists, trees, graphs.")
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.courseName", is("Data Structures")))
                .andExpect(jsonPath("$.courseCode", is("CS201")))
                .andExpect(jsonPath("$.catalogVersion", is("2025-2026")))
                .andExpect(jsonPath("$.extractionStatus", is("READY_FOR_REVIEW")))
                .andExpect(jsonPath("$.draftRevision", is(0)))
                .andReturn();

        contentManagerOutcomeId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("outcomeId").asInt();
    }

    // Purpose: FR-CM-04 review - the extraction proposal is pollable and reports the draft
    // revision the content manager must echo back on every mutation (optimistic locking).
    @Test
    @Order(381)
    void phase3_extractionStatusReportsReadyForReviewWithDraftRevision() throws Exception {
        mockMvc.perform(get("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/extraction")
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.extractionStatus", is("READY_FOR_REVIEW")))
                .andExpect(jsonPath("$.totalSkills", is(2)))
                .andExpect(jsonPath("$.pendingSkills", is(2)))
                .andExpect(jsonPath("$.taxonomyVersion", is("taxonomy-2026.08")));
    }

    // Purpose: FR-CM-04 review - every extracted term is listed with its canonical match,
    // evidence, and PENDING decision; nothing has been approved by anyone yet.
    @Test
    @Order(382)
    void phase3_draftSkillsListShowsPendingProposalWithEvidence() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/skills")
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].term", is("object-oriented programming")))
                .andExpect(jsonPath("$[0].canonicalSkillId", is("skill:oop")))
                .andExpect(jsonPath("$[0].decision", is("PENDING")))
                .andExpect(jsonPath("$[0].matchScore", is(0.95)))
                .andExpect(jsonPath("$[0].evidence", hasSize(1)))
                .andReturn();

        JsonNode skills = objectMapper.readTree(result.getResponse().getContentAsString());
        contentManagerDraftSkillId = skills.get(0).get("draftSkillId").asLong();
        contentManagerDraftRowVersion = skills.get(0).get("rowVersion").asLong();
    }

    // Purpose: review concurrency - a mutation carrying a stale draft revision is rejected
    // with 409 STALE_RESOURCE before anything is modified, so two browsers on the same review
    // can never silently overwrite each other.
    @Test
    @Order(383)
    void phase3_staleDraftRevisionIsRejectedWithConflict() throws Exception {
        mockMvc.perform(patch("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/skills/" + contentManagerDraftSkillId)
                        .header("Authorization", "Bearer " + contentManagerToken)
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(java.util.Map.of(
                                "expectedRowVersion", contentManagerDraftRowVersion,
                                "expectedDraftRevision", 999)))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error", is("STALE_RESOURCE")));
    }

    // Purpose: FR-CM-04 review - accepting a proposal advances the aggregate revision, and a
    // second mutation must then use the new revision value (the CAS really rotates).
    @Test
    @Order(384)
    void phase3_contentManagerAcceptsExtractedSkill() throws Exception {
        contentManagerDraftRevision = readCurrentDraftRevision();

        MvcResult result = mockMvc.perform(patch("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/skills/" + contentManagerDraftSkillId)
                        .header("Authorization", "Bearer " + contentManagerToken)
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(java.util.Map.of(
                                "decision", "ACCEPTED",
                                "expectedRowVersion", contentManagerDraftRowVersion,
                                "expectedDraftRevision", contentManagerDraftRevision)))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.decision", is("ACCEPTED")))
                .andExpect(jsonPath("$.rowVersion", is((int) (contentManagerDraftRowVersion + 1))))
                .andReturn();

        contentManagerDraftRowVersion = objectMapper.readTree(
                result.getResponse().getContentAsString()).get("rowVersion").asLong();

        mockMvc.perform(get("/api/content-managers/me/learning-outcomes/" + contentManagerOutcomeId)
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.pendingSkills", is(1)));
    }

    // Purpose: FR-CM-04 publication - with every skill resolved, the approved map is copied
    // into an immutable version 1, confirmed by the AI service, and only then becomes
    // PUBLISHED; the row's course_map_version records exactly which snapshot students see.
    @Test
    @Order(385)
    void phase3_contentManagerPublishesApprovedCourseMap() throws Exception {
        // Accept the remaining pending skill first.
        MvcResult skills = mockMvc.perform(get("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/skills")
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode rows = objectMapper.readTree(skills.getResponse().getContentAsString());
        Long pendingId = null;
        Long pendingRowVersion = null;
        for (JsonNode row : rows) {
            if ("PENDING".equals(row.get("decision").asText())) {
                pendingId = row.get("draftSkillId").asLong();
                pendingRowVersion = row.get("rowVersion").asLong();
            }
        }
        assertThat(pendingId).isNotNull();
        contentManagerDraftRevision = readCurrentDraftRevision();
        mockMvc.perform(patch("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/skills/" + pendingId)
                        .header("Authorization", "Bearer " + contentManagerToken)
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(java.util.Map.of(
                                "decision", "ACCEPTED",
                                "expectedRowVersion", pendingRowVersion,
                                "expectedDraftRevision", contentManagerDraftRevision)))
                )
                .andExpect(status().isOk());

        contentManagerDraftRevision = readCurrentDraftRevision();
        mockMvc.perform(post("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/publish")
                        .header("Authorization", "Bearer " + contentManagerToken)
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(java.util.Map.of(
                                "expectedDraftRevision", contentManagerDraftRevision)))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.extractionStatus", is("PUBLISHED")))
                .andExpect(jsonPath("$.courseMapVersion", is(1)))
                .andExpect(jsonPath("$.publishedAt", notNullValue()));
    }

    // Purpose: publication guardrails - after PUBLISHED the review is closed, so a further
    // edit is a 400 (not a silent mutation of a map students already see), and re-uploading
    // the same course identity is a 409 pointing at the existing review.
    @Test
    @Order(386)
    void phase3_publishedOutcomeIsImmutableAndDuplicateUploadRejected() throws Exception {
        mockMvc.perform(patch("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId + "/skills/" + contentManagerDraftSkillId)
                        .header("Authorization", "Bearer " + contentManagerToken)
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(java.util.Map.of(
                                "expectedRowVersion", contentManagerDraftRowVersion,
                                "expectedDraftRevision", contentManagerDraftRevision)))
                )
                .andExpect(status().isBadRequest());

        MockMultipartFile file = new MockMultipartFile(
                "file", "cs201-again.pdf", "application/pdf", "fake pdf content".getBytes());
        mockMvc.perform(multipart("/api/content-managers/me/learning-outcomes")
                        .file(file)
                        .param("courseCode", "CS201")
                        .param("catalogVersion", "2025-2026")
                        .param("courseName", "Data Structures")
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error", is("DUPLICATE_RESOURCE")));
    }

    // Purpose: FR-CM-04 - a non-PDF upload is rejected with 400, never silently accepted.
    @Test
    @Order(39)
    void phase3_contentManagerUpload_rejectsNonPdfFile() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "notes.txt", "text/plain", "not a pdf".getBytes());

        mockMvc.perform(multipart("/api/content-managers/me/learning-outcomes")
                        .file(file)
                        .param("courseName", "Data Structures")
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error", is("INVALID_REQUEST")));
    }

    // =====================================================================================
    // PHASE 4 - Transcript upload, confirmation, and skill dashboard (AI mocked from here on)
    // =====================================================================================

    // Purpose: FR-JS-10 - the Job Seeker uploads a transcript PDF and receives extracted rows
    // for review; the mock AI response simulates Module 1 (pdfplumber + LLM extraction).
    // Crucially, NOTHING is persisted to academic_records yet at this stage.
    @Test
    @Order(40)
    void phase4_jobSeekerCanUploadTranscript_receivingRowsWithoutPersistingYet() throws Exception {
        // Mocked Module 1 response: 2 courses, 1 low-confidence - see stubDataAnalysisLayer().

        MockMultipartFile file = new MockMultipartFile(
                "file", "transcript.pdf", "application/pdf", "fake transcript bytes".getBytes());

        mockMvc.perform(multipart("/api/job-seekers/me/transcript")
                        .file(file)
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.courses", hasSize(2)))
                .andExpect(jsonPath("$.lowConfidenceCount", is(1)));

        assertThat(academicRecordRepository.findByJobSeeker_JobseekerId(jobSeekerId)).isEmpty();
    }

    // Purpose: FR-JS-11/12/13/14 - confirming the transcript persists the academic records,
    // triggers the (mocked) skill-vector computation (Module 2) and skill-gap analysis
    // (Module 3), and returns a populated skill dashboard.
    @Test
    @Order(41)
    void phase4_jobSeekerCanConfirmTranscript_persistingDataAndComputingDashboard() throws Exception {
        // Mocked Module 2 + Module 3 responses: Data Structures 90 (Strong), Operating
        // Systems 55 (Weak), 72% overall readiness - see stubDataAnalysisLayer().

        String body = "{\"courses\":[" +
                "{\"courseName\":\"Data Structures\",\"grade\":\"A\"}," +
                "{\"courseName\":\"Operating Systems\",\"grade\":\"C\"}" +
                "]}";

        mockMvc.perform(post("/api/job-seekers/me/transcript/confirm")
                        .header("Authorization", "Bearer " + jobSeekerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.overallReadinessPercent", is(72)))
                .andExpect(jsonPath("$.skills", hasSize(2)))
                .andExpect(jsonPath("$.basedOnQuizResults", is(false)));

        assertThat(academicRecordRepository.findByJobSeeker_JobseekerId(jobSeekerId)).hasSize(2);
        assertThat(jobseekerSkillRepository.findByJobSeeker_JobseekerId(jobSeekerId)).hasSize(2);
    }

    // Purpose: FR-JS-14/21 - the skill dashboard can be re-fetched independently of
    // confirmation, always recomputed live from the persisted academic records.
    @Test
    @Order(42)
    void phase4_jobSeekerCanViewSkillDashboardAfterConfirmation() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me/skill-dashboard")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.skills[0].classification").exists());
    }

    // =====================================================================================
    // PHASE 4B - Logout and session termination (all five actors)
    //
    // Placed here rather than beside the login tests in Phase 1 because this is the first
    // point in the journey where all five actor types exist: the Content Manager and both
    // Experts are not created until Phase 3.
    // =====================================================================================

    // Purpose: FR-JS-03 / FR-CM-02 / FR-EMP-03, and the equivalent capability for
    // Administrators and Experts - every actor can log out, and logging out genuinely ends
    // the session rather than relying on the client to forget its token.
    //
    // Each actor logs in FRESH here to obtain a throwaway token, and it is that token which
    // is logged out. The journey's main tokens are deliberately left untouched, both so the
    // remaining phases still work and so ST-67 below can prove revocation is scoped to one
    // session rather than to the whole account.
    @Test
    @Order(43)
    void phase4b_everyActorCanLogOutAndTheSurrenderedTokenStopsWorking() throws Exception {
        record ActorSession(String loginPath, String credentials, String protectedPath) {}

        List<ActorSession> actors = List.of(
                new ActorSession("/api/auth/job-seekers/login",
                        "{\"email\":\"sara@example.com\",\"password\":\"password123\"}",
                        "/api/job-seekers/me"),
                new ActorSession("/api/auth/employers/login",
                        "{\"email\":\"hr@atlas.example.com\",\"password\":\"password123\"}",
                        "/api/employers/me"),
                new ActorSession("/api/auth/content-managers/login",
                        "{\"email\":\"nour@meu.edu.jo\",\"password\":\"cmPassword123\"}",
                        "/api/content-managers/me/learning-outcomes"),
                new ActorSession("/api/auth/experts/login",
                        "{\"email\":\"david@example.com\",\"password\":\"expertPass123\"}",
                        "/api/experts/me"),
                new ActorSession("/api/auth/admins/login",
                        "{\"email\":\"admin@careercompass.local\",\"password\":\"adminPass123\"}",
                        "/api/admin/content-managers")
        );

        for (ActorSession actor : actors) {
            MvcResult login = mockMvc.perform(post(actor.loginPath())
                            .contentType("application/json").content(actor.credentials()))
                    .andExpect(status().isOk())
                    .andReturn();

            String sessionToken = readToken(login);

            // The token works before logout...
            mockMvc.perform(get(actor.protectedPath())
                            .header("Authorization", "Bearer " + sessionToken))
                    .andExpect(status().isOk());

            mockMvc.perform(post("/api/auth/logout")
                            .header("Authorization", "Bearer " + sessionToken))
                    .andExpect(status().isNoContent());

            // ...and is refused afterwards, even though it is still correctly signed and
            // still well inside its 30-minute expiry window. Only revocation can explain this.
            mockMvc.perform(get(actor.protectedPath())
                            .header("Authorization", "Bearer " + sessionToken))
                    .andExpect(status().isUnauthorized());
        }
    }

    // Purpose: logging out is scoped to the session that was surrendered. Revocation is keyed
    // on the token's jti, so the Job Seeker's original token - issued back in ST-05 and used
    // by every phase of this journey - must still work after ST-66 logged out a different
    // session belonging to the same person. Had revocation been implemented per user instead
    // of per token, this assertion would fail and every later phase would collapse with it.
    @Test
    @Order(44)
    void phase4b_loggingOutOneSessionLeavesOtherSessionsOfTheSameUserWorking() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email", is("sara@example.com")));
    }

    // Purpose: logout is the one route under /api/auth/** that requires a token - a session
    // cannot be ended without saying which session. Verifies the ordering of the security
    // rules, since /api/auth/** is otherwise entirely public.
    @Test
    @Order(45)
    void phase4b_logoutRequiresAuthentication() throws Exception {
        mockMvc.perform(post("/api/auth/logout"))
                .andExpect(status().isUnauthorized());
    }

    // Purpose: a revoked token cannot be replayed against logout itself. The second attempt
    // is stopped by the filter before it reaches the controller, which confirms the denylist
    // is consulted for every authenticated route rather than only for business endpoints.
    @Test
    @Order(46)
    void phase4b_aRevokedTokenCannotBeUsedToLogOutAgain() throws Exception {
        MvcResult login = mockMvc.perform(post("/api/auth/job-seekers/login")
                        .contentType("application/json")
                        .content("{\"email\":\"sara@example.com\",\"password\":\"password123\"}"))
                .andExpect(status().isOk())
                .andReturn();

        String sessionToken = readToken(login);

        mockMvc.perform(post("/api/auth/logout")
                        .header("Authorization", "Bearer " + sessionToken))
                .andExpect(status().isNoContent());

        mockMvc.perform(post("/api/auth/logout")
                        .header("Authorization", "Bearer " + sessionToken))
                .andExpect(status().isUnauthorized());
    }

    // =====================================================================================
    // PHASE 5 - Course recommendations (Module 4)
    // =====================================================================================

    // Purpose: FR-JS-15/16 - recommendations are generated from the job seeker's CURRENT
    // weak skills ("Operating Systems", per the dashboard above) and persisted.
    @Test
    @Order(50)
    void phase5_jobSeekerCanGenerateCourseRecommendationsForWeakSkills() throws Exception {
        // Mocked Module 4 response: one course targeting "Operating Systems", the only skill
        // the Module 3 stub classifies as Weak - see stubDataAnalysisLayer().

        mockMvc.perform(post("/api/job-seekers/me/course-recommendations/generate")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].courseName", is("Operating Systems Fundamentals")))
                .andExpect(jsonPath("$[0].explanation").exists());
    }

    // Purpose: re-reading the stored recommendations returns the reasoning too, not just the
    // course links. V6 added targeted_skill_name and explanation precisely so a student coming
    // back to the page keeps the "why this course" text instead of being told to regenerate.
    @Test
    @Order(51)
    void phase5_jobSeekerCanViewStoredRecommendations_reasoningSurvivesReRead() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me/course-recommendations")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].courseName", is("Operating Systems Fundamentals")))
                .andExpect(jsonPath("$[0].explanation").exists())
                .andExpect(jsonPath("$[0].targetedSkillName").exists());
    }

    // =====================================================================================
    // PHASE 6 - Quizzes: generate, verify answers are hidden, submit, verify write-back
    // =====================================================================================

    // Purpose: FR-JS-17/18 - a quiz is generated for the weak course, and the response sent
    // to the job seeker MUST NOT contain the correct answer for any question (verified
    // directly against the raw JSON, not just assumed from the DTO's field list).
    @Test
    @Order(60)
    void phase6_jobSeekerCanGenerateQuiz_correctAnswersAreNeverSentToTheClient() throws Exception {
        // Mocked Module 5 response: 2 questions whose correct answers are A and B - see
        // stubDataAnalysisLayer(). The correct answers exist in the mock precisely so the
        // assertion below can prove they never reach the client.

        // Requested by canonical skill id, not by course name — a course teaches many skills.
        String body = "{\"skillId\":\"" + OPERATING_SYSTEMS_SKILL_ID + "\",\"questionCount\":2}";

        MvcResult result = mockMvc.perform(post("/api/job-seekers/me/quizzes")
                        .header("Authorization", "Bearer " + jobSeekerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.questions", hasSize(2)))
                .andReturn();

        String responseBody = result.getResponse().getContentAsString();
        assertThat(responseBody).doesNotContain("correctOption"); // the key assertion

        JsonNode json = objectMapper.readTree(responseBody);
        quizId = json.get("quizId").asInt();
        quizQuestion1Id = json.get("questions").get(0).get("questionId").asInt();
        quizQuestion2Id = json.get("questions").get(1).get("questionId").asInt();
    }

    // Purpose: FR-JS-19/20/21 - submitting answers (one correct, one wrong) computes a 50%
    // score, and the write-back replaces the grade-derived "Operating Systems" skill score
    // (55, from Phase 4) with the quiz-derived score (50) - verified directly against the
    // database, not just the HTTP response, since this is the most important behavioural
    // guarantee in the whole quiz feature (Section 5.3.1's "red dashed loop").
    @Test
    @Order(61)
    void phase6_jobSeekerCanSubmitQuiz_scoreIsCorrectAndSkillProfileIsRefined() throws Exception {
        String body = String.format(
                "{\"answers\":[" +
                "{\"questionId\":%d,\"selectedOption\":\"A\"}," +
                "{\"questionId\":%d,\"selectedOption\":\"A\"}" +
                "]}", quizQuestion1Id, quizQuestion2Id); // Q1 correct (A), Q2 wrong (correct is B)

        mockMvc.perform(post("/api/job-seekers/me/quizzes/" + quizId + "/submit")
                        .header("Authorization", "Bearer " + jobSeekerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.correctCount", is(1)))
                .andExpect(jsonPath("$.totalQuestions", is(2)))
                .andExpect(jsonPath("$.score", is(50.0)))
                .andExpect(jsonPath("$.updatedDashboard.basedOnQuizResults", is(true)));

        // Read the persisted row back by its composite primary key rather than by streaming
        // the job seeker's skills and navigating js.getSkill().getSkillName(): JobseekerSkill
        // maps `skill` as a LAZY @ManyToOne, and entities returned to this test thread are
        // already detached (nothing here runs inside a transaction), so touching that
        // association would raise LazyInitializationException before the assertion below ever
        // ran. Resolving the skill id first keeps the check on the field we actually care
        // about - the score - without depending on Hibernate session state.
        Skill operatingSystems = skillRepository.findBySkillName("Operating Systems").orElseThrow();

        JobseekerSkill refined = jobseekerSkillRepository
                .findById(new JobseekerSkillId(jobSeekerId, operatingSystems.getSkillId()))
                .orElseThrow();

        assertThat(refined.getScore()).isEqualByComparingTo(BigDecimal.valueOf(50.00)); // was 55 from grades
    }

    // Purpose: FR-JS-19 - a quiz cannot be submitted twice; the second attempt is rejected
    // with 400, protecting the integrity of the FR-JS-20 write-back (only one score per quiz).
    @Test
    @Order(62)
    void phase6_submittingTheSameQuizTwice_isRejected() throws Exception {
        String body = String.format(
                "{\"answers\":[{\"questionId\":%d,\"selectedOption\":\"B\"}]}", quizQuestion1Id);

        mockMvc.perform(post("/api/job-seekers/me/quizzes/" + quizId + "/submit")
                        .header("Authorization", "Bearer " + jobSeekerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error", is("PREREQUISITE_NOT_MET")));
    }

    // =====================================================================================
    // PHASE 7 - Mentors & consultation booking
    // =====================================================================================

    // Purpose: FR-JS-24 - the Job Seeker (study field = Computer Science) can now see the
    // Expert (also Computer Science, Active) in their mentor list.
    @Test
    @Order(70)
    void phase7_jobSeekerCanSeeActiveExpertInMentorList() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me/mentors")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].expertId", is(expertId)));
    }

    // Purpose: FR-JS-25 - the Job Seeker books a consultation session; it is always created
    // with "Requested" status (only the Expert can move it forward).
    @Test
    @Order(71)
    void phase7_jobSeekerCanBookConsultationSession() throws Exception {
        // Booking is only allowed inside a slot the mentor has published (FR-EX-06 gates
        // FR-JS-25), so the schedule has to exist before the request — exactly the order a
        // real mentor and student go through.
        LocalDateTime slot = LocalDateTime.now().plusDays(3).withHour(10).withMinute(0)
                .withSecond(0).withNano(0);
        publishAvailabilityCovering(slot);

        String body = String.format("{\"expertId\":%d,\"appointmentDate\":\"%s\"}", expertId, slot);

        MvcResult result = mockMvc.perform(post("/api/job-seekers/me/appointments")
                        .header("Authorization", "Bearer " + jobSeekerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.statusName", is("Requested")))
                .andReturn();

        appointmentId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("appointmentId").asInt();
    }

    // Purpose: FR-EX-05 - the Expert sees the newly booked session in their scheduled list.
    @Test
    @Order(72)
    void phase7_expertCanSeeScheduledSession() throws Exception {
        mockMvc.perform(get("/api/experts/me/sessions/scheduled")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].appointmentId", is(appointmentId)));
    }

    // Purpose: NFR-PRIV/SEC-04 - a DIFFERENT expert (no appointment with this job seeker) is
    // rejected with 403 when trying to view the job seeker's skill dashboard - proves FR-EX-07
    // is genuinely gated by a real consultation relationship, not just by being "an expert".
    @Test
    @Order(73)
    void phase7_unrelatedExpertCannotViewJobSeekerSkillProfile() throws Exception {
        mockMvc.perform(get("/api/experts/me/job-seekers/" + jobSeekerId + "/skill-dashboard")
                        .header("Authorization", "Bearer " + secondExpertToken))
                .andExpect(status().isForbidden());
    }

    // Purpose: FR-EX-03 - the Expert accepts the consultation request.
    @Test
    @Order(74)
    void phase7_expertCanAcceptConsultationRequest() throws Exception {
        mockMvc.perform(patch("/api/experts/me/appointments/" + appointmentId + "/accept")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusName", is("Accepted")));
    }

    // Purpose: FR-EX-07/08 - NOW that a genuine appointment exists, the SAME expert (not the
    // unrelated one from the earlier negative test) CAN view the job seeker's skill profile
    // and recommended courses.
    @Test
    @Order(75)
    void phase7_relatedExpertCanViewJobSeekerSkillProfileAndRecommendations() throws Exception {
        mockMvc.perform(get("/api/experts/me/job-seekers/" + jobSeekerId + "/skill-dashboard")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/experts/me/job-seekers/" + jobSeekerId + "/course-recommendations")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk());
    }

    // Purpose: FR-EX-09/10/11 - the Expert records session notes and feedback (which also
    // carries the FR-EX-10 readiness evaluation - see ExpertService's Javadoc on this
    // documented schema simplification) after the consultation.
    @Test
    @Order(76)
    void phase7_expertCanSubmitConsultationOutcome() throws Exception {
        String body = "{\"sessionNotes\":\"Discussed OS fundamentals gap.\"," +
                "\"feedback\":\"Solid overall readiness; recommend the OS course before applying.\"}";

        mockMvc.perform(patch("/api/experts/me/appointments/" + appointmentId + "/outcome")
                        .header("Authorization", "Bearer " + expertToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.feedback", containsString("readiness")));
    }

    // Purpose: FR-EX-12 - the completed session now appears in the Expert's consultation
    // history.
    @Test
    @Order(77)
    void phase7_expertCanViewConsultationHistory() throws Exception {
        mockMvc.perform(get("/api/experts/me/sessions/history")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].appointmentId", is(appointmentId)));
    }

    /**
     * Publish a mentor schedule wide enough to contain {@code slot}.
     *
     * <p>The suite books relative to "now", so the weekday moves with the calendar; the slot's
     * own day is derived rather than hard-coded, and the window is deliberately generous so
     * the assertion under test is about booking, not about clock arithmetic. The endpoint
     * replaces the whole schedule, which is why each caller republishes its own day.
     */
    private void publishAvailabilityCovering(LocalDateTime slot) throws Exception {
        String body = String.format(
                "{\"slots\":[{\"dayOfWeek\":%d,\"startTime\":\"00:00:00\",\"endTime\":\"23:59:00\"}]}",
                slot.getDayOfWeek().getValue());

        mockMvc.perform(put("/api/experts/me/availability")
                        .header("Authorization", "Bearer " + expertToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk());
    }

    // Purpose: FR-EX-06 - the Expert sets the weekly availability schedule for consultation
    // sessions. The endpoint replaces the whole schedule rather than appending to it, so the
    // test writes two slots, then rewrites with one, and confirms the first set is gone.
    @Test
    @Order(78)
    void phase7_expertCanUpdateAvailabilitySchedule() throws Exception {
        String twoSlots = "{\"slots\":[" +
                "{\"dayOfWeek\":1,\"startTime\":\"09:00:00\",\"endTime\":\"12:00:00\"}," +
                "{\"dayOfWeek\":3,\"startTime\":\"14:00:00\",\"endTime\":\"17:00:00\"}" +
                "]}";

        mockMvc.perform(put("/api/experts/me/availability")
                        .header("Authorization", "Bearer " + expertToken)
                        .contentType("application/json").content(twoSlots))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].dayOfWeek", is(1)));

        String oneSlot = "{\"slots\":[" +
                "{\"dayOfWeek\":5,\"startTime\":\"10:00:00\",\"endTime\":\"13:00:00\"}" +
                "]}";

        mockMvc.perform(put("/api/experts/me/availability")
                        .header("Authorization", "Bearer " + expertToken)
                        .contentType("application/json").content(oneSlot))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].dayOfWeek", is(5)));
    }

    // Purpose: FR-EX-04 - the Expert rejects a consultation request. The suite's original
    // appointment was accepted and completed in ST-40 to ST-42, so a second session is booked
    // here as the arrangement for this test; rejecting is the branch under test.
    @Test
    @Order(79)
    void phase7_expertCanRejectAConsultationRequest() throws Exception {
        LocalDateTime slot = LocalDateTime.now().plusDays(10).withHour(10).withMinute(0)
                .withSecond(0).withNano(0);
        publishAvailabilityCovering(slot);

        String body = String.format("{\"expertId\":%d,\"appointmentDate\":\"%s\"}", expertId, slot);

        MvcResult booking = mockMvc.perform(post("/api/job-seekers/me/appointments")
                        .header("Authorization", "Bearer " + jobSeekerToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.statusName", is("Requested")))
                .andReturn();

        rejectedAppointmentId = objectMapper.readTree(booking.getResponse().getContentAsString())
                .get("appointmentId").asInt();

        mockMvc.perform(patch("/api/experts/me/appointments/" + rejectedAppointmentId + "/reject")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.appointmentId", is(rejectedAppointmentId)))
                .andExpect(jsonPath("$.statusName", is("Rejected")));

        // The earlier, accepted appointment must be unaffected by the rejection.
        mockMvc.perform(get("/api/job-seekers/me/appointments")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.appointmentId == " + appointmentId + ")].statusName",
                        not(hasItem("Rejected"))));
    }

    // =====================================================================================
    // PHASE 8 - Job matching (Module 6, both directions)
    // =====================================================================================

    // Purpose: FR-JS-23 - the Job Seeker's skill profile is matched against the Employer's
    // active job posting.
    @Test
    @Order(80)
    void phase8_jobSeekerCanViewJobMatches() throws Exception {
        // Mocked Module 6 response: a match score of 82.0 - see stubDataAnalysisLayer().

        mockMvc.perform(get("/api/job-seekers/me/job-matches")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].jobId", is(jobId)))
                .andExpect(jsonPath("$[0].matchScore", is(82.0)));
    }

    // Purpose: FR-EMP-11/12/13 - the owning Employer sees the matched candidate along with
    // their skill insights and email (needed for FR-EMP-13, contacting the candidate).
    @Test
    @Order(81)
    void phase8_employerCanViewMatchedCandidatesForOwnJob() throws Exception {
        mockMvc.perform(get("/api/employers/me/jobs/" + jobId + "/candidates")
                        .header("Authorization", "Bearer " + employerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].jobseekerId", is(jobSeekerId)))
                .andExpect(jsonPath("$[0].email", is("sara@example.com")))
                .andExpect(jsonPath("$[0].skillInsights").isArray());
    }

    // Purpose: NFR-SEC-04 ownership - a DIFFERENT employer cannot view candidates for a job
    // they do not own, even though the job/candidates genuinely exist in the system.
    @Test
    @Order(82)
    void phase8_differentEmployerCannotViewAnotherEmployersCandidates() throws Exception {
        mockMvc.perform(get("/api/employers/me/jobs/" + jobId + "/candidates")
                        .header("Authorization", "Bearer " + secondEmployerToken))
                .andExpect(status().isForbidden());
    }

    // =====================================================================================
    // PHASE 9 - Admin account-lifecycle management & Job Seeker erasure
    // =====================================================================================

    // Purpose: FR-SA-04 - the Administrator updates Content Manager account information.
    // Only the name is changed; the email is deliberately left untouched so that ST-48's
    // login-by-email check further down still refers to the same account.
    @Test
    @Order(89)
    void phase9_adminCanUpdateContentManagerInformation() throws Exception {
        String body = "{\"firstName\":\"Nour\",\"lastName\":\"Al-Khaled\"}";

        mockMvc.perform(put("/api/admin/content-managers/" + contentManagerId)
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.contentManagerId", is(contentManagerId)))
                .andExpect(jsonPath("$.lastName", is("Al-Khaled")))
                .andExpect(jsonPath("$.email", is("nour@meu.edu.jo")))
                // the university was not sent, so the partial update must leave it in place
                .andExpect(jsonPath("$.universityId", is(universityId)));
    }

    // Purpose: FR-SA-05 - the Administrator deactivates the Content Manager account.
    @Test
    @Order(90)
    void phase9_adminCanDeactivateContentManager() throws Exception {
        mockMvc.perform(patch("/api/admin/content-managers/" + contentManagerId + "/deactivate")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isActive", is(false)));
    }

    // Purpose: a deactivated Content Manager can no longer log in, even with the correct
    // password - confirms deactivation actually blocks access, not just a cosmetic flag.
    @Test
    @Order(91)
    void phase9_deactivatedContentManagerCannotLogin() throws Exception {
        String body = "{\"email\":\"nour@meu.edu.jo\",\"password\":\"cmPassword123\"}";

        mockMvc.perform(post("/api/auth/content-managers/login")
                        .contentType("application/json").content(body))
                .andExpect(status().isUnauthorized());
    }

    // Purpose: FR-JS-08 / NFR-PRIV-02 - the Job Seeker deletes their own profile, which must
    // erase ALL associated data (academic records, skills, quizzes), not just the profile row
    // itself - verified directly against the database.
    @Test
    @Order(92)
    void phase9_jobSeekerCanDeleteOwnProfile_erasingAllAssociatedData() throws Exception {
        mockMvc.perform(delete("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isNoContent());

        assertThat(jobSeekerRepository.existsById(jobSeekerId)).isFalse();
        assertThat(academicRecordRepository.findByJobSeeker_JobseekerId(jobSeekerId)).isEmpty();
        assertThat(jobseekerSkillRepository.findByJobSeeker_JobseekerId(jobSeekerId)).isEmpty();
        assertThat(quizRepository.findByJobSeeker_JobseekerIdOrderByGeneratedAtDesc(jobSeekerId)).isEmpty();
    }

    // Purpose: after deletion, the old token is still cryptographically valid (JWTs are
    // stateless and not revoked server-side) but any attempt to use it now fails at the
    // service layer since the underlying job seeker no longer exists - confirms deletion is
    // real, not just a soft flag the token can bypass.
    @Test
    @Order(93)
    void phase9_deletedJobSeekersOldTokenCanNoLongerFetchAProfile() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isNotFound());
    }

    // Purpose: FR-SA-06 - the Administrator reactivates a deactivated Content Manager account.
    // Placed after the erasure tests because @Order values 92 and 93 were already taken; the
    // Content Manager thread is independent of the Job Seeker deletion above, so the sequence
    // is unaffected.
    @Test
    @Order(94)
    void phase9_adminCanReactivateContentManager() throws Exception {
        mockMvc.perform(patch("/api/admin/content-managers/" + contentManagerId + "/activate")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.isActive", is(true)));
    }

    // Purpose: FR-SA-06 - reactivation must actually restore access. ST-48 proved the account
    // was genuinely locked out while deactivated; this proves the lock is lifted, which is
    // what makes the pair of tests meaningful rather than a check on a display flag.
    @Test
    @Order(95)
    void phase9_reactivatedContentManagerCanLogInAgain() throws Exception {
        String body = "{\"email\":\"nour@meu.edu.jo\",\"password\":\"cmPassword123\"}";

        mockMvc.perform(post("/api/auth/content-managers/login")
                        .contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").exists());
    }

    // Purpose: FR-EX-02 - the other half of the consulting-status toggle. ST-24 activated the
    // Expert; this deactivates them, so both directions of the requirement are exercised
    // rather than only the opt-in.
    @Test
    @Order(96)
    void phase9_expertCanDeactivateForConsulting() throws Exception {
        mockMvc.perform(patch("/api/experts/me/status/deactivate")
                        .header("Authorization", "Bearer " + expertToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusName", is("Inactive")));
    }

    // --- helpers -------------------------------------------------------------------------

    private String readToken(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("token").asText();
    }

    /**
     * Reads the aggregate's current draft revision straight from the API, mirroring what a
     * real second browser would do after receiving 409 STALE_RESOURCE.
     */
    private long readCurrentDraftRevision() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/content-managers/me/learning-outcomes/"
                        + contentManagerOutcomeId)
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString())
                .get("draftRevision").asLong();
    }

    /**
     * Builds a structurally valid, correctly signed JWT whose expiry has already passed,
     * mirroring the claims JwtTokenProvider issues (subject, email, role).
     *
     * Signing with the application's real key matters: it makes the token fail ONLY on
     * expiry, so a 401 proves the inactivity window is enforced rather than merely proving
     * that a garbage string is rejected.
     */
    private String mintExpiredToken(Role role, String email) {
        SecretKey key = Keys.hmacShaKeyFor(jwtProperties.getSecret().getBytes(StandardCharsets.UTF_8));
        Instant issuedAt = Instant.now().minusSeconds(jwtProperties.getExpirationMinutes() * 60 + 60);
        Instant expiredAt = issuedAt.plusSeconds(jwtProperties.getExpirationMinutes() * 60);

        return Jwts.builder()
                .subject("1")
                .claim("email", email)
                .claim("role", role.name())
                .issuedAt(Date.from(issuedAt))
                .expiration(Date.from(expiredAt))
                .signWith(key)
                .compact();
    }
}
