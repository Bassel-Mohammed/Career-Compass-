package com.careercompass.service;

import com.careercompass.dto.request.CreateCareerPathRequest;
import com.careercompass.dto.request.UpdateCareerPathRequest;
import com.careercompass.dto.response.CareerPathResponse;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.StudyField;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.CareerPathMapper;
import com.careercompass.repository.CareerPathRepository;
import com.careercompass.repository.StudyFieldRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/**
 * FR-SA-08/09/10 (create/update/delete career path titles, scoped to study field(s)).
 */
@Service
@RequiredArgsConstructor
public class CareerPathService {

    private final CareerPathRepository careerPathRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final CareerPathMapper careerPathMapper;

    @Transactional
    public CareerPathResponse createCareerPath(CreateCareerPathRequest request) {
        Set<StudyField> studyFields = resolveStudyFields(request.getStudyFieldIds());
        String careerPathCode = request.getCareerPathCode() == null
                || request.getCareerPathCode().isBlank()
                ? "cp:" + UUID.randomUUID()
                : request.getCareerPathCode().trim();

        if (careerPathRepository.findByCareerPathCode(careerPathCode).isPresent()) {
            throw new DuplicateResourceException(
                    "A career path with code '" + careerPathCode + "' already exists.");
        }

        CareerPath careerPath = CareerPath.builder()
                .title(request.getTitle())
                .careerPathCode(careerPathCode)
                .ontologyVersion(request.getOntologyVersion())
                .description(request.getDescription())
                .studyFields(studyFields)
                .build();

        return careerPathMapper.toResponse(careerPathRepository.save(careerPath));
    }

    @Transactional
    public CareerPathResponse updateCareerPath(Integer careerPathId, UpdateCareerPathRequest request) {
        CareerPath careerPath = careerPathRepository.findById(careerPathId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Career path with id " + careerPathId + " not found."));

        if (request.getTitle() != null) {
            careerPath.setTitle(request.getTitle());
        }
        if (request.getDescription() != null) {
            careerPath.setDescription(request.getDescription());
        }
        if (request.getOntologyVersion() != null) {
            careerPath.setOntologyVersion(request.getOntologyVersion());
        }
        if (request.getStudyFieldIds() != null) {
            careerPath.setStudyFields(resolveStudyFields(request.getStudyFieldIds()));
        }

        return careerPathMapper.toResponse(careerPathRepository.save(careerPath));
    }

    @Transactional
    public void deleteCareerPath(Integer careerPathId) {
        if (!careerPathRepository.existsById(careerPathId)) {
            throw new ResourceNotFoundException("Career path with id " + careerPathId + " not found.");
        }
        careerPathRepository.deleteById(careerPathId);
    }

    @Transactional(readOnly = true)
    public List<CareerPathResponse> listCareerPaths() {
        return careerPathRepository.findAll().stream()
                .map(careerPathMapper::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public CareerPathResponse getCareerPath(Integer careerPathId) {
        CareerPath careerPath = careerPathRepository.findById(careerPathId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Career path with id " + careerPathId + " not found."));
        return careerPathMapper.toResponse(careerPath);
    }

    private Set<StudyField> resolveStudyFields(List<Integer> studyFieldIds) {
        Set<StudyField> studyFields = new HashSet<>();
        for (Integer id : studyFieldIds) {
            StudyField studyField = studyFieldRepository.findById(id)
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "Study field with id " + id + " not found."));
            studyFields.add(studyField);
        }
        return studyFields;
    }
}
