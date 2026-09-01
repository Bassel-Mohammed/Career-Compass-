package com.careercompass.repository;

import com.careercompass.entity.LearningOutcomeSkillDraft;
import com.careercompass.entity.SkillDraftDecision;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

/** Persistence access for review drafts; mutation lookups are always scoped to their owner. */
public interface LearningOutcomeSkillDraftRepository
        extends JpaRepository<LearningOutcomeSkillDraft, Long> {

    List<LearningOutcomeSkillDraft> findByOutcome_OutcomeIdOrderByDraftSkillIdAsc(Integer outcomeId);

    @EntityGraph(attributePaths = "outcome")
    List<LearningOutcomeSkillDraft>
            findByOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerIdOrderByDraftSkillIdAsc(
                    Integer outcomeId, Integer contentManagerId);

    @EntityGraph(attributePaths = "outcome")
    Optional<LearningOutcomeSkillDraft>
            findByDraftSkillIdAndOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerId(
                    Long draftSkillId, Integer outcomeId, Integer contentManagerId);

    Optional<LearningOutcomeSkillDraft> findByOutcome_OutcomeIdAndTermIgnoreCase(
            Integer outcomeId, String term);

    long countByOutcome_OutcomeId(Integer outcomeId);

    long countByOutcome_OutcomeIdAndDecision(Integer outcomeId, SkillDraftDecision decision);

    boolean existsByOutcome_OutcomeIdAndCanonicalSkillIdAndDecisionIn(
            Integer outcomeId, String canonicalSkillId, Collection<SkillDraftDecision> decisions);

    long deleteByOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerId(
            Integer outcomeId, Integer contentManagerId);
}
