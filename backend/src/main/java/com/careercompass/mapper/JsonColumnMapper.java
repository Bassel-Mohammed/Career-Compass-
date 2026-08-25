package com.careercompass.mapper;

import com.careercompass.dto.response.DraftSkillCandidateResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.mapstruct.Named;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/** Converts private TEXT-backed JSON audit columns into stable typed response values. */
@Component
@RequiredArgsConstructor
public class JsonColumnMapper {

    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() { };
    private static final TypeReference<List<Map<String, Object>>> EVIDENCE_LIST =
            new TypeReference<>() { };
    private static final TypeReference<List<DraftSkillCandidateResponse>> CANDIDATE_LIST =
            new TypeReference<>() { };

    private final ObjectMapper objectMapper;

    @Named("jsonStringList")
    public List<String> toStringList(String json) {
        return read(json, STRING_LIST);
    }

    @Named("jsonEvidenceList")
    public List<Map<String, Object>> toEvidenceList(String json) {
        return read(json, EVIDENCE_LIST);
    }

    @Named("jsonCandidateList")
    public List<DraftSkillCandidateResponse> toCandidateList(String json) {
        return read(json, CANDIDATE_LIST);
    }

    private <T> List<T> read(String json, TypeReference<List<T>> type) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, type);
        } catch (JsonProcessingException ignored) {
            // Old or manually repaired rows must not make the review page itself unavailable.
            return List.of();
        }
    }
}
