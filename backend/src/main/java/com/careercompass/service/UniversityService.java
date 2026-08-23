package com.careercompass.service;

import com.careercompass.dto.request.CreateUniversityRequest;
import com.careercompass.dto.response.UniversityResponse;
import com.careercompass.entity.University;
import com.careercompass.mapper.UniversityMapper;
import com.careercompass.repository.UniversityRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Prerequisite admin capability for FR-SA-03 (assign a university to a Content Manager) —
 * see CreateUniversityRequest's Javadoc for why this exists without its own explicit FR-SA-xx.
 */
@Service
@RequiredArgsConstructor
public class UniversityService {

    private final UniversityRepository universityRepository;
    private final UniversityMapper universityMapper;

    @Transactional
    public UniversityResponse createUniversity(CreateUniversityRequest request) {
        University university = University.builder()
                .universityName(request.getUniversityName())
                .build();
        return universityMapper.toResponse(universityRepository.save(university));
    }

    @Transactional(readOnly = true)
    public List<UniversityResponse> listUniversities() {
        return universityRepository.findAll().stream()
                .map(universityMapper::toResponse)
                .toList();
    }
}
