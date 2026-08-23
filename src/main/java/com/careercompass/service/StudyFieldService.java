package com.careercompass.service;

import com.careercompass.dto.request.CreateStudyFieldRequest;
import com.careercompass.dto.response.StudyFieldResponse;
import com.careercompass.entity.StudyField;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.mapper.StudyFieldMapper;
import com.careercompass.repository.StudyFieldRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * FR-SA-07 (add a study field to the system).
 */
@Service
@RequiredArgsConstructor
public class StudyFieldService {

    private final StudyFieldRepository studyFieldRepository;
    private final StudyFieldMapper studyFieldMapper;

    @Transactional
    public StudyFieldResponse createStudyField(CreateStudyFieldRequest request) {
        if (studyFieldRepository.existsByFieldName(request.getFieldName())) {
            throw new DuplicateResourceException(
                    "A study field named '" + request.getFieldName() + "' already exists.");
        }

        StudyField studyField = StudyField.builder()
                .fieldName(request.getFieldName())
                .build();

        return studyFieldMapper.toResponse(studyFieldRepository.save(studyField));
    }

    @Transactional(readOnly = true)
    public List<StudyFieldResponse> listStudyFields() {
        return studyFieldRepository.findAll().stream()
                .map(studyFieldMapper::toResponse)
                .toList();
    }
}
