package com.careercompass.service;

import com.careercompass.dto.request.CreateExpertRequest;
import com.careercompass.dto.response.ExpertResponse;
import com.careercompass.entity.Expert;
import com.careercompass.entity.ExpertStatus;
import com.careercompass.entity.StudyField;
import com.careercompass.exception.EmailAlreadyExistsException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.ExpertMapper;
import com.careercompass.repository.ExpertRepository;
import com.careercompass.repository.ExpertStatusRepository;
import com.careercompass.repository.StudyFieldRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Administrator-side Expert account creation (FR-EX-01: "assigned by the system
 * administrator"). Named/scoped the same way as ContentManagerAdminService (Increment 6) —
 * "admin managing another actor's account" kept separate from that actor's own self-service
 * (see ExpertService for the Expert's own actions).
 */
@Service
@RequiredArgsConstructor
public class ExpertAdminService {

    private final ExpertRepository expertRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final ExpertStatusRepository expertStatusRepository;
    private final PasswordEncoder passwordEncoder;
    private final ExpertMapper expertMapper;

    @Transactional
    public ExpertResponse createExpert(CreateExpertRequest request) {
        if (expertRepository.existsByEmail(request.getEmail())) {
            throw new EmailAlreadyExistsException(request.getEmail());
        }

        StudyField studyField = null;
        if (request.getStudyFieldId() != null) {
            studyField = studyFieldRepository.findById(request.getStudyFieldId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "Study field with id " + request.getStudyFieldId() + " not found."));
        }

        // New experts default to "Inactive" for consulting until they opt in (FR-EX-02).
        ExpertStatus inactiveStatus = expertStatusRepository.findByStatusName("Inactive")
                .orElseGet(() -> expertStatusRepository.save(
                        ExpertStatus.builder().statusName("Inactive").build()));

        Expert expert = Expert.builder()
                .firstName(request.getFirstName())
                .lastName(request.getLastName())
                .email(request.getEmail())
                .passwordHash(passwordEncoder.encode(request.getInitialPassword()))
                .studyField(studyField)
                .fieldStartingYear(request.getFieldStartingYear())
                .status(inactiveStatus)
                .build();

        return expertMapper.toResponse(expertRepository.save(expert));
    }
    @Transactional(readOnly = true)
    public List<ExpertResponse> listExperts() {
        return expertRepository.findAll().stream()
                .map(expertMapper::toResponse)
                .toList();
    }
}
