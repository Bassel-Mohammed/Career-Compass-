package com.careercompass.system;

import com.careercompass.entity.*;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.*;
import com.careercompass.repository.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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

import java.math.BigDecimal;
import java.time.LocalDateTime;
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
@ActiveProfiles("dev")
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

    private static String expertToken;
    private static Integer expertId;

    private static String secondExpertToken;

    private static String adminToken;

    private static Integer quizId;
    private static Integer quizQuestion1Id;
    private static Integer quizQuestion2Id;

    private static Integer appointmentId;

    // =====================================================================================
    // SHARED AI STUBS - the Data Analyses Layer's canonical responses for this journey
    // =====================================================================================

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

        // Module 2: grade-based skill vector. Operating Systems = 55 here is what the quiz
        // write-back in Phase 6 later replaces with the quiz-derived 50 (FR-JS-20).
        when(dataAnalysisClient.buildSkillVector(any(BuildSkillVectorRequest.class)))
                .thenReturn(SkillVectorResponse.builder()
                        .skills(List.of(
                                SkillScoreDto.builder().skillName("Data Structures").score(BigDecimal.valueOf(90)).build(),
                                SkillScoreDto.builder().skillName("Operating Systems").score(BigDecimal.valueOf(55)).build()
                        ))
                        .build());

        // Module 3: skill-gap analysis. "Operating Systems" is the one Weak skill, which is
        // what Phase 5's course recommendations are generated against.
        when(dataAnalysisClient.analyzeSkillGap(any(SkillGapAnalysisRequest.class)))
                .thenReturn(SkillGapAnalysisResponse.builder()
                        .overallReadinessPercent(72)
                        .skillGaps(List.of(
                                SkillGapAnalysisResponse.SkillGapItemDto.builder()
                                        .skillName("Data Structures").currentScore(BigDecimal.valueOf(90))
                                        .targetScore(BigDecimal.valueOf(75)).classification("Strong")
                                        .explanation("Well above target.").build(),
                                SkillGapAnalysisResponse.SkillGapItemDto.builder()
                                        .skillName("Operating Systems").currentScore(BigDecimal.valueOf(55))
                                        .targetScore(BigDecimal.valueOf(75)).classification("Weak")
                                        .explanation("Below target level.").build()
                        ))
                        .build());

        // Module 4: one course recommendation, targeting the Weak skill above.
        when(dataAnalysisClient.recommendCourses(any(CourseRecommendationRequest.class)))
                .thenReturn(List.of(RecommendedCourseDto.builder()
                        .courseName("Operating Systems Fundamentals")
                        .sourceLink("https://example.com/os-fundamentals")
                        .targetedSkillName("Operating Systems")
                        .explanation("Directly targets your weakest skill.")
                        .build()));

        // Module 5: a 2-question quiz whose correct answers are A and B - Phase 6 answers
        // A and A, so exactly one is correct and the score must come out as 50%.
        when(dataAnalysisClient.generateQuiz(any(QuizGenerationRequest.class)))
                .thenReturn(QuizGenerationResponse.builder()
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

    // Purpose: FR-CM-04 - the Content Manager uploads a course learning-outcome PDF.
    @Test
    @Order(38)
    void phase3_contentManagerCanUploadLearningOutcomePdf() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "cs201-outcomes.pdf", "application/pdf", "fake pdf content".getBytes());

        mockMvc.perform(multipart("/api/content-managers/me/learning-outcomes")
                        .file(file)
                        .param("courseName", "Data Structures")
                        .param("description", "Covers arrays, lists, trees, graphs.")
                        .header("Authorization", "Bearer " + contentManagerToken))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.courseName", is("Data Structures")));
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

    // Purpose: viewing the stored recommendations afterward still returns them, though the
    // per-course explanation is null on this path (a documented schema limitation - the
    // courses_recommendations table has no explanation column).
    @Test
    @Order(51)
    void phase5_jobSeekerCanViewStoredRecommendations_explanationIsNullOnReRead() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me/course-recommendations")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].courseName", is("Operating Systems Fundamentals")))
                .andExpect(jsonPath("$[0].explanation").doesNotExist());
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

        String body = "{\"courseName\":\"Operating Systems\",\"questionCount\":2}";

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
        String futureDate = LocalDateTime.now().plusDays(3).toString();
        String body = String.format("{\"expertId\":%d,\"appointmentDate\":\"%s\"}", expertId, futureDate);

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

    // --- helpers -------------------------------------------------------------------------

    private String readToken(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("token").asText();
    }
}
