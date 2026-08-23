package com.careercompass.repository;

import com.careercompass.entity.JobseekerSkill;
import com.careercompass.entity.JobseekerSkillId;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `jobseeker_skills` — the persisted Student Skill Vector
 * (Section 5.3.1). Supports FR-JS-14/20/21 (skill dashboard, quiz-based updates).
 */
public interface JobseekerSkillRepository extends JpaRepository<JobseekerSkill, JobseekerSkillId> {

    List<JobseekerSkill> findByJobSeeker_JobseekerId(Integer jobseekerId);

    List<JobseekerSkill> findByJobSeeker_JobseekerIdOrderByScoreAsc(Integer jobseekerId);

    void deleteByJobSeeker_JobseekerId(Integer jobseekerId);
}
