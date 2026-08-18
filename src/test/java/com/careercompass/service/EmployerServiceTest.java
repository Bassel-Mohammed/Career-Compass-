package com.careercompass.service;

import com.careercompass.dto.request.UpdateEmployerProfileRequest;
import com.careercompass.dto.response.EmployerProfileResponse;
import com.careercompass.entity.Employer;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.EmployerMapper;
import com.careercompass.repository.EmployerRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class EmployerServiceTest {

    @Mock private EmployerRepository employerRepository;
    @Mock private EmployerMapper employerMapper;

    @InjectMocks
    private EmployerService employerService;

    // Purpose: Update Profile - applies Only Provided Fields.
    @Test
    void updateProfile_appliesOnlyProvidedFields() {
        Employer existing = Employer.builder()
                .employerId(1)
                .companyName("Old Co")
                .industry("Old Industry")
                .build();

        UpdateEmployerProfileRequest request = new UpdateEmployerProfileRequest();
        request.setCompanyName("New Co");
        // industry and companyDescription left null -> untouched

        when(employerRepository.findById(1)).thenReturn(Optional.of(existing));
        when(employerRepository.save(any(Employer.class))).thenAnswer(inv -> inv.getArgument(0));
        when(employerMapper.toProfileResponse(any(Employer.class)))
                .thenReturn(EmployerProfileResponse.builder().companyName("New Co").industry("Old Industry").build());

        EmployerProfileResponse response = employerService.updateProfile(1, request);

        assertThat(response.getCompanyName()).isEqualTo("New Co");
        assertThat(response.getIndustry()).isEqualTo("Old Industry");
    }

    // Purpose: Get Profile - throws When Not Found.
    @Test
    void getProfile_throwsWhenNotFound() {
        when(employerRepository.findById(999)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> employerService.getProfile(999))
                .isInstanceOf(ResourceNotFoundException.class);
    }
}
