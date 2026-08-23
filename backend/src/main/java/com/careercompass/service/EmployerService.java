package com.careercompass.service;

import com.careercompass.dto.request.UpdateEmployerProfileRequest;
import com.careercompass.dto.response.EmployerProfileResponse;
import com.careercompass.entity.Employer;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.EmployerMapper;
import com.careercompass.repository.EmployerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Business Layer for an Employer's OWN company-profile actions (FR-EMP-05/06).
 *
 * FR-EMP-05 ("create a company profile") is satisfied by registration itself
 * (see {@link AuthService#registerEmployer}) — same reasoning as JobSeekerService's FR-JS-05
 * note. No separate "create" method exists here for that.
 */
@Service
@RequiredArgsConstructor
public class EmployerService {

    private final EmployerRepository employerRepository;
    private final EmployerMapper employerMapper;

    @Transactional(readOnly = true)
    public EmployerProfileResponse getProfile(Integer employerId) {
        return employerMapper.toProfileResponse(getOrThrow(employerId));
    }

    @Transactional
    public EmployerProfileResponse updateProfile(Integer employerId, UpdateEmployerProfileRequest request) {
        Employer employer = getOrThrow(employerId);

        if (request.getCompanyName() != null) {
            employer.setCompanyName(request.getCompanyName());
        }
        if (request.getIndustry() != null) {
            employer.setIndustry(request.getIndustry());
        }
        if (request.getCompanyDescription() != null) {
            employer.setCompanyDescription(request.getCompanyDescription());
        }

        return employerMapper.toProfileResponse(employerRepository.save(employer));
    }

    private Employer getOrThrow(Integer employerId) {
        return employerRepository.findById(employerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Employer with id " + employerId + " not found."));
    }
}
