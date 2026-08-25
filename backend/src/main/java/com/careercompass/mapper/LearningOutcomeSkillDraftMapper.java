package com.careercompass.mapper;

import com.careercompass.dto.response.DraftSkillResponse;
import com.careercompass.entity.LearningOutcomeSkillDraft;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

/** Maps TEXT JSON audit fields into typed lists without exposing persistence representation. */
@Mapper(componentModel = "spring", uses = JsonColumnMapper.class)
public interface LearningOutcomeSkillDraftMapper {

    @Mapping(target = "outcomeId", source = "outcome.outcomeId")
    @Mapping(target = "canonicalSkillLabel", source = "canonicalLabel")
    @Mapping(target = "originalCanonicalSkillLabel", source = "originalCanonicalLabel")
    @Mapping(target = "sources", source = "sourcesJson", qualifiedByName = "jsonStringList")
    @Mapping(target = "evidence", source = "evidenceJson", qualifiedByName = "jsonEvidenceList")
    @Mapping(target = "candidates", source = "candidatesJson", qualifiedByName = "jsonCandidateList")
    DraftSkillResponse toResponse(LearningOutcomeSkillDraft entity);
}
