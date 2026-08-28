package com.careercompass.config;

import com.careercompass.entity.Administrator;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.ContentManager;
import com.careercompass.entity.Expert;
import com.careercompass.entity.ExpertAvailability;
import com.careercompass.entity.ExpertStatus;
import com.careercompass.entity.StudyField;
import com.careercompass.entity.University;
import com.careercompass.repository.AdministratorRepository;
import com.careercompass.repository.CareerPathRepository;
import com.careercompass.repository.ContentManagerRepository;
import com.careercompass.repository.ExpertRepository;
import com.careercompass.repository.ExpertAvailabilityRepository;
import com.careercompass.repository.ExpertStatusRepository;
import com.careercompass.repository.StudyFieldRepository;
import com.careercompass.repository.UniversityRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalTime;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Seeds the reference data a fresh {@code dev} database needs in order to be usable at all.
 *
 * <p><b>Why this exists.</b> Nothing in the application can create the first Administrator —
 * {@code AuthController} deliberately exposes no {@code /api/auth/admins/register}, because an
 * open "create an admin" route is a privilege-escalation hole. Administrators are expected to
 * be seeded outside the app. But universities, study fields and career paths can <i>only</i> be
 * created by an Administrator, and a job seeker cannot select a career path (FR-JS-09) until
 * one exists. Career path in turn gates confirming a transcript, the skill dashboard, course
 * recommendations and job matches. So on a fresh database with no admin, the entire student
 * journey is unreachable — not because of a bug, but because the bootstrap chain has no first
 * link.
 *
 * <p>The {@code dev} profile uses an in-memory H2 database that is discarded on every restart,
 * so without this the chain would have to be re-established by hand on every single run.
 *
 * <p><b>Scope.</b> Real {@code dev} runs only. The {@code test}, {@code prod} and
 * {@code integration} profiles never load this class, so seeded data cannot interfere with test
 * fixtures or reach a real deployment. It is also idempotent — it checks for an existing
 * administrator and does nothing if one is present.
 *
 * <p><b>Career path names are not arbitrary.</b> They match the nine paths in the AI service's
 * ontology exactly ({@code ai-service/data/extracted/jobs/career_path_skills.json}, 771 skill
 * requirements). A path seeded under any other name would be accepted by Java and then fail to
 * match anything on the Python side, producing an empty skill gap that looks like a bug.
 * Likewise the study field names match the keys of
 * {@code ai-service/data/mapping/study_field_career_paths.json}, which is what mentor matching
 * falls back to when an expert has no stated expertise terms.
 */
@Slf4j
@Component
@Profile("dev & !test")
@RequiredArgsConstructor
public class DevDataSeeder implements CommandLineRunner {

    private static final String ADMIN_EMAIL = "admin@careercompass.local";
    private static final String ADMIN_PASSWORD = "admin12345";
    private static final String SEEDED_PASSWORD = "mentor12345";
    private static final String CONTENT_MANAGER_EMAIL = "nadia.saleh@content.local";

    /**
     * Career path to the study fields it is offered to, inverted from the AI service's
     * study-field mapping. A job seeker sees the paths whose set contains their own field.
     */
    private static final Map<String, List<String>> CAREER_PATHS = new LinkedHashMap<>();
    private static final Map<String, String> CAREER_PATH_CODES = Map.of(
            "Backend Development", "career:backend-development",
            "Full Stack Development", "career:full-stack-development",
            "Data Science & Analytics", "career:data-science-analytics",
            "AI & Machine Learning", "career:ai-machine-learning",
            "DevOps & Cloud", "career:devops-cloud",
            "Cybersecurity", "career:cybersecurity",
            "QA & Testing", "career:qa-testing",
            "Mobile Development", "career:mobile-development",
            "UI/UX Design", "career:ui-ux-design");

    static {
        CAREER_PATHS.put("Backend Development", List.of("Computer Science", "Software Engineering"));
        CAREER_PATHS.put("Full Stack Development",
                List.of("Computer Science", "Software Engineering", "Information Systems"));
        CAREER_PATHS.put("Data Science & Analytics",
                List.of("Computer Science", "Information Systems", "Data Science"));
        CAREER_PATHS.put("AI & Machine Learning", List.of("Data Science", "Computer Science"));
        CAREER_PATHS.put("DevOps & Cloud", List.of("Information Technology", "Computer Science"));
        CAREER_PATHS.put("Cybersecurity", List.of("Cybersecurity", "Information Technology"));
        CAREER_PATHS.put("QA & Testing", List.of("Software Engineering", "Computer Science"));
        CAREER_PATHS.put("Mobile Development", List.of("Mobile Development", "Software Engineering"));
        CAREER_PATHS.put("UI/UX Design", List.of("Multimedia", "Information Systems"));
    }

    private static final Map<String, String> PATH_DESCRIPTIONS = Map.of(
            "Backend Development", "Server-side services, APIs and the data stores behind them.",
            "Full Stack Development", "Both the browser interface and the services powering it.",
            "Data Science & Analytics", "Turning raw data into models, dashboards and decisions.",
            "AI & Machine Learning", "Training, evaluating and deploying machine-learning systems.",
            "DevOps & Cloud", "Build pipelines, infrastructure and running systems in production.",
            "Cybersecurity", "Protecting systems and data from compromise.",
            "QA & Testing", "Automated and exploratory testing, and the quality of a release.",
            "Mobile Development", "Native and cross-platform applications for phones and tablets.",
            "UI/UX Design", "Interface design, interaction and usability research.");

    private final AdministratorRepository administratorRepository;
    private final UniversityRepository universityRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final CareerPathRepository careerPathRepository;
    private final ExpertRepository expertRepository;
    private final ExpertStatusRepository expertStatusRepository;
    private final ExpertAvailabilityRepository expertAvailabilityRepository;
    private final ContentManagerRepository contentManagerRepository;
    private final PasswordEncoder passwordEncoder;

    @Override
    @Transactional
    public void run(String... args) {
        if (administratorRepository.count() > 0) {
            log.info("Dev seed skipped — an administrator already exists.");
            return;
        }

        Administrator admin = administratorRepository.save(Administrator.builder()
                .firstName("Platform")
                .lastName("Administrator")
                .email(ADMIN_EMAIL)
                .passwordHash(passwordEncoder.encode(ADMIN_PASSWORD))
                .build());

        List<University> universities = List.of("An-Najah National University", "Birzeit University")
                .stream()
                .map(name -> universityRepository.save(University.builder()
                        .universityName(name)
                        .createdByAdmin(admin)
                        .build()))
                .toList();

        // The distinct study fields named across every career path, in first-seen order.
        Map<String, StudyField> fields = CAREER_PATHS.values().stream()
                .flatMap(List::stream)
                .distinct()
                .collect(Collectors.toMap(
                        name -> name,
                        name -> studyFieldRepository.save(StudyField.builder()
                                .fieldName(name)
                                .createdByAdmin(admin)
                                .build()),
                        (a, b) -> a,
                        LinkedHashMap::new));

        CAREER_PATHS.forEach((title, fieldNames) -> {
            Set<StudyField> linked = fieldNames.stream()
                    .map(fields::get)
                    .collect(Collectors.toCollection(LinkedHashSet::new));

            careerPathRepository.save(CareerPath.builder()
                    .title(title)
                    // Reviewed stable IDs aligned to this seed catalogue, never inferred at run time.
                    .careerPathCode(CAREER_PATH_CODES.get(title))
                    .description(PATH_DESCRIPTIONS.get(title))
                    .createdByAdmin(admin)
                    .studyFields(linked)
                    .build());
        });

        seedMentors(fields);
        seedContentManager(universities.get(0));

        log.info("Dev seed complete: {} universities, {} study fields, {} career paths, {} mentors, "
                        + "1 content manager. Admin account: {}",
                universityRepository.count(), fields.size(), CAREER_PATHS.size(),
                expertRepository.count(), ADMIN_EMAIL);
    }

    /**
     * One content manager, deliberately with <b>no study field</b>.
     *
     * <p>A university is required — the column is NOT NULL and only an administrator can set it —
     * but the study field is what FR-CM-05 asks them to choose themselves, and uploading is
     * blocked until they do. Seeding that choice already made would hide the first-run path
     * behind a state nobody could reach again without editing the database.
     */
    private void seedContentManager(University university) {
        contentManagerRepository.save(ContentManager.builder()
                .firstName("Nadia")
                .lastName("Saleh")
                .email(CONTENT_MANAGER_EMAIL)
                .passwordHash(passwordEncoder.encode(SEEDED_PASSWORD))
                .university(university)
                .isActive(true)
                .build());
    }

    /**
     * A handful of mentors, seeded <b>Active</b> rather than the "Inactive" default that
     * {@code ExpertAdminService} applies. Only Active experts in the student's own study field
     * appear in {@code GET /api/job-seekers/me/mentors}, so seeding them Inactive would leave
     * the mentor screen empty and indistinguishable from a broken query. The mentor catalogue
     * is empty in every other environment — see STATUS.md — so this is the only place the
     * mentor and consultation flows have anything to render against.
     */
    private void seedMentors(Map<String, StudyField> fields) {
        ExpertStatus active = expertStatusRepository.findByStatusName("Active")
                .orElseGet(() -> expertStatusRepository.save(
                        ExpertStatus.builder().statusName("Active").build()));

        record Mentor(String first, String last, String field, short since) {}

        Arrays.asList(
                        new Mentor("Layla", "Haddad", "Computer Science", (short) 2012),
                        new Mentor("Omar", "Nasser", "Software Engineering", (short) 2008),
                        new Mentor("Rana", "Khalil", "Cybersecurity", (short) 2015),
                        new Mentor("Yousef", "Darwish", "Data Science", (short) 2017),
                        new Mentor("Huda", "Mansour", "Information Systems", (short) 2010))
                .forEach(m -> {
                    Expert expert = expertRepository.save(Expert.builder()
                            .firstName(m.first())
                            .lastName(m.last())
                            .email((m.first() + "." + m.last() + "@mentors.local").toLowerCase())
                            .passwordHash(passwordEncoder.encode(SEEDED_PASSWORD))
                            .studyField(fields.get(m.field()))
                            .fieldStartingYear(m.since())
                            .status(active)
                            .build());
                    seedAvailability(expert);
                });
    }

    /**
     * Give every seeded mentor a weekly schedule.
     *
     * <p>Booking now refuses any time outside a mentor's published availability, and a mentor
     * with no slots is not bookable at all. Seeding mentors without slots would therefore hand
     * the demo a mentor list where every request is rejected — the mentor screen would look
     * fine and the booking would never work, which is a worse failure than an empty list.
     *
     * <p>Monday/Wednesday/Sunday, 1=Monday..7=Sunday, matching the availability editor and the
     * frontend's day names.
     */
    private void seedAvailability(Expert expert) {
        record Slot(byte day, LocalTime from, LocalTime to) {}

        Arrays.asList(
                        new Slot((byte) 1, LocalTime.of(9, 0), LocalTime.of(12, 0)),
                        new Slot((byte) 3, LocalTime.of(13, 0), LocalTime.of(17, 0)),
                        new Slot((byte) 7, LocalTime.of(10, 0), LocalTime.of(14, 0)))
                .forEach(s -> expertAvailabilityRepository.save(ExpertAvailability.builder()
                        .expert(expert)
                        .dayOfWeek(s.day())
                        .startTime(s.from())
                        .endTime(s.to())
                        .build()));
    }
}
