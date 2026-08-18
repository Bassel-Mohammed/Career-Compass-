package com.careercompass.service;

import com.careercompass.dto.request.UpdateJobSeekerProfileRequest;
import com.careercompass.dto.response.JobSeekerProfileResponse;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.JobSeeker;
import com.careercompass.entity.StudyField;
import com.careercompass.entity.University;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.JobSeekerMapper;
import com.careercompass.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Business Layer for a Job Seeker's OWN profile actions (FR-JS-05..09).
 *
 * FR-JS-05 ("create a personal profile") is satisfied by registration itself
 * (see {@link AuthService#registerJobSeeker}) — a JobSeeker row is the profile; there's no
 * separate "create profile after registering" step in the FRs, so no extra method exists here
 * for that.
 *
 * Every method takes the caller's OWN jobseekerId, resolved server-side from the validated JWT
 * (via {@link com.careercompass.security.userdetails.CurrentUser}) — never from a client-
 * supplied path variable — enforcing NFR-SEC-04 (users only access their own data).
 */
@Service
@RequiredArgsConstructor
public class JobSeekerService {

    private final JobSeekerRepository jobSeekerRepository;
    private final UniversityRepository universityRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final CareerPathRepository careerPathRepository;
    private final AcademicRecordRepository academicRecordRepository;
    private final CourseRecommendationRepository courseRecommendationRepository;
    private final JobseekerSkillRepository jobseekerSkillRepository;
    private final QuizRepository quizRepository;
    private final QuizQuestionRepository quizQuestionRepository;
    private final QuizResponseRepository quizResponseRepository;
    private final JobMatchRepository jobMatchRepository;
    private final AppointmentRepository appointmentRepository;
    private final JobSeekerMapper jobSeekerMapper;

    @Transactional(readOnly = true)
    public JobSeekerProfileResponse getProfile(Integer jobseekerId) {
        return jobSeekerMapper.toProfileResponse(getOrThrow(jobseekerId));
    }

    @Transactional
    public JobSeekerProfileResponse updateProfile(Integer jobseekerId, UpdateJobSeekerProfileRequest request) {
        JobSeeker jobSeeker = getOrThrow(jobseekerId);

        if (request.getFirstName() != null) {
            jobSeeker.setFirstName(request.getFirstName());
        }
        if (request.getLastName() != null) {
            jobSeeker.setLastName(request.getLastName());
        }
        if (request.getUniversityId() != null) {
            University university = universityRepository.findById(request.getUniversityId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "University with id " + request.getUniversityId() + " not found."));
            jobSeeker.setUniversity(university);
        }
        if (request.getStudyFieldId() != null) {
            StudyField studyField = studyFieldRepository.findById(request.getStudyFieldId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "Study field with id " + request.getStudyFieldId() + " not found."));
            jobSeeker.setStudyField(studyField);
        }
        if (request.getCareerPathId() != null) {
            // FR-JS-09: select desired career path.
            CareerPath careerPath = careerPathRepository.findById(request.getCareerPathId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "Career path with id " + request.getCareerPathId() + " not found."));
            jobSeeker.setCareerPath(careerPath);
        }

        return jobSeekerMapper.toProfileResponse(jobSeekerRepository.save(jobSeeker));
    }

    /**
     * FR-JS-08 (delete personal profile), implementing the "right to erasure" (NFR-PRIV-02)
     * thoroughly: all data that only exists in relation to this job seeker is removed, not
     * just the job_seekers row itself, since leaving orphaned academic/skill/quiz/match data
     * behind would violate the spirit of the erasure requirement even if the FK is nullable.
     *
     * Quiz responses and questions are deleted explicitly, BEFORE their parent quizzes,
     * because a bulk JPQL delete (deleteByJobSeeker_JobseekerId) does not trigger the
     * entity-level CascadeType.ALL declared on Quiz -&gt; QuizQuestion (that cascade only
     * applies to entities removed through the persistence context, not to bulk delete
     * queries) — deleting quizzes first would otherwise risk an FK constraint violation.
     * This gap was found and fixed while building the quiz feature in Increment 12; it
     * existed silently since Increment 7 because no quiz data existed yet to expose it.
     */
    @Transactional
    public void deleteProfile(Integer jobseekerId) {
        if (!jobSeekerRepository.existsById(jobseekerId)) {
            throw new ResourceNotFoundException("Job seeker with id " + jobseekerId + " not found.");
        }

        appointmentRepository.deleteByJobSeeker_JobseekerId(jobseekerId);
        jobMatchRepository.deleteByJobSeeker_JobseekerId(jobseekerId);
        quizResponseRepository.deleteByQuestion_Quiz_JobSeeker_JobseekerId(jobseekerId);
        quizQuestionRepository.deleteByQuiz_JobSeeker_JobseekerId(jobseekerId);
        quizRepository.deleteByJobSeeker_JobseekerId(jobseekerId);
        jobseekerSkillRepository.deleteByJobSeeker_JobseekerId(jobseekerId);
        courseRecommendationRepository.deleteByJobSeeker_JobseekerId(jobseekerId);
        academicRecordRepository.deleteByJobSeeker_JobseekerId(jobseekerId);

        jobSeekerRepository.deleteById(jobseekerId);
    }

    private JobSeeker getOrThrow(Integer jobseekerId) {
        return jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Job seeker with id " + jobseekerId + " not found."));
    }
}
