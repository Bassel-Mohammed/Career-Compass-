package com.careercompass.service;

import com.careercompass.dto.request.CreateContentManagerRequest;
import com.careercompass.dto.request.UpdateContentManagerRequest;
import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.entity.ContentManager;
import com.careercompass.entity.StudyField;
import com.careercompass.entity.University;
import com.careercompass.exception.EmailAlreadyExistsException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.ContentManagerMapper;
import com.careercompass.repository.ContentManagerRepository;
import com.careercompass.repository.StudyFieldRepository;
import com.careercompass.repository.UniversityRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * FR-SA-02/03/04/05/06 — Administrator manages Content Manager accounts.
 * Named distinctly from a hypothetical "ContentManagerService" (which would hold the Content
 * Manager's OWN self-service actions, e.g. uploading learning outcomes, FR-CM-04/05) to keep
 * "admin acting on behalf of / managing another actor" separate from "actor acting on
 * themselves" — the same split will apply later for Experts (Admin creates them; Experts
 * manage their own availability/sessions).
 */
@Service
@RequiredArgsConstructor
public class ContentManagerAdminService {

    private final ContentManagerRepository contentManagerRepository;
    private final UniversityRepository universityRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final PasswordEncoder passwordEncoder;
    private final ContentManagerMapper contentManagerMapper;

    @Transactional
    public ContentManagerResponse createContentManager(CreateContentManagerRequest request) {
        if (contentManagerRepository.existsByEmail(request.getEmail())) {
            throw new EmailAlreadyExistsException(request.getEmail());
        }

        University university = universityRepository.findById(request.getUniversityId())
                .orElseThrow(() -> new ResourceNotFoundException(
                        "University with id " + request.getUniversityId() + " not found."));

        StudyField studyField = null;
        if (request.getStudyFieldId() != null) {
            studyField = studyFieldRepository.findById(request.getStudyFieldId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "Study field with id " + request.getStudyFieldId() + " not found."));
        }

        ContentManager contentManager = ContentManager.builder()
                .firstName(request.getFirstName())
                .lastName(request.getLastName())
                .email(request.getEmail())
                .passwordHash(passwordEncoder.encode(request.getInitialPassword()))
                .university(university)
                .studyField(studyField)
                .isActive(true)
                .build();

        return contentManagerMapper.toResponse(contentManagerRepository.save(contentManager));
    }

    @Transactional
    public ContentManagerResponse updateContentManager(Integer contentManagerId,
                                                          UpdateContentManagerRequest request) {
        ContentManager contentManager = getOrThrow(contentManagerId);

        if (request.getFirstName() != null) {
            contentManager.setFirstName(request.getFirstName());
        }
        if (request.getLastName() != null) {
            contentManager.setLastName(request.getLastName());
        }
        if (request.getUniversityId() != null) {
            University university = universityRepository.findById(request.getUniversityId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "University with id " + request.getUniversityId() + " not found."));
            contentManager.setUniversity(university);
        }
        if (request.getStudyFieldId() != null) {
            StudyField studyField = studyFieldRepository.findById(request.getStudyFieldId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "Study field with id " + request.getStudyFieldId() + " not found."));
            contentManager.setStudyField(studyField);
        }

        return contentManagerMapper.toResponse(contentManagerRepository.save(contentManager));
    }

    @Transactional
    public ContentManagerResponse setActive(Integer contentManagerId, boolean active) {
        ContentManager contentManager = getOrThrow(contentManagerId);
        contentManager.setIsActive(active);
        return contentManagerMapper.toResponse(contentManagerRepository.save(contentManager));
    }

    @Transactional(readOnly = true)
    public List<ContentManagerResponse> listContentManagers() {
        return contentManagerRepository.findAll().stream()
                .map(contentManagerMapper::toResponse)
                .toList();
    }

    private ContentManager getOrThrow(Integer contentManagerId) {
        return contentManagerRepository.findById(contentManagerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Content manager with id " + contentManagerId + " not found."));
    }
}
