package com.careercompass.service;

import com.careercompass.dto.request.CreateCareerPathRequest;
import com.careercompass.dto.request.UpdateCareerPathRequest;
import com.careercompass.dto.response.CareerPathResponse;
import com.careercompass.dto.response.StudyFieldResponse;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.StudyField;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.CareerPathMapper;
import com.careercompass.repository.CareerPathRepository;
import com.careercompass.repository.StudyFieldRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for CareerPathService (FR-SA-08/09/10). Repositories are mocked (NFR-MNT-07);
 * the mapper is a small hand-written stub rather than the real MapStruct-generated
 * implementation, since instantiating a Spring-composed MapStruct mapper outside a Spring
 * context requires poking at generated internals — not worth the fragility for a unit test
 * that only cares about CareerPathService's own branching logic, not the mapper's correctness
 * (which is covered separately, following the JobSeekerMapperTest pattern from Increment 4).
 */
@ExtendWith(MockitoExtension.class)
class CareerPathServiceTest {

    @Mock
    private CareerPathRepository careerPathRepository;

    @Mock
    private StudyFieldRepository studyFieldRepository;

    private CareerPathService careerPathService;

    @BeforeEach
    void setUp() {
        CareerPathMapper stubMapper = careerPath -> CareerPathResponse.builder()
                .careerPathId(careerPath.getCareerPathId())
                .title(careerPath.getTitle())
                .description(careerPath.getDescription())
                .studyFields(careerPath.getStudyFields() == null ? List.of() :
                        careerPath.getStudyFields().stream()
                                .map(sf -> StudyFieldResponse.builder()
                                        .studyFieldId(sf.getStudyFieldId())
                                        .fieldName(sf.getFieldName())
                                        .build())
                                .toList())
                .createdAt(careerPath.getCreatedAt())
                .build();

        careerPathService = new CareerPathService(careerPathRepository, studyFieldRepository, stubMapper);
    }

    // Purpose: Create Career Path - links Resolved Study Fields.
    @Test
    void createCareerPath_linksResolvedStudyFields() {
        CreateCareerPathRequest request = new CreateCareerPathRequest();
        request.setTitle("Software Engineer");
        request.setDescription("Build and ship reliable software.");
        request.setStudyFieldIds(List.of(1, 2));

        StudyField field1 = StudyField.builder().studyFieldId(1).fieldName("Computer Science").build();
        StudyField field2 = StudyField.builder().studyFieldId(2).fieldName("Software Engineering").build();

        when(studyFieldRepository.findById(1)).thenReturn(Optional.of(field1));
        when(studyFieldRepository.findById(2)).thenReturn(Optional.of(field2));
        when(careerPathRepository.save(any(CareerPath.class))).thenAnswer(inv -> {
            CareerPath cp = inv.getArgument(0);
            cp.setCareerPathId(100);
            return cp;
        });

        CareerPathResponse response = careerPathService.createCareerPath(request);

        assertThat(response.getCareerPathId()).isEqualTo(100);
        assertThat(response.getTitle()).isEqualTo("Software Engineer");
        assertThat(response.getStudyFields()).hasSize(2);
    }

    // Purpose: Create Career Path - throws When Study Field Does Not Exist.
    @Test
    void createCareerPath_throwsWhenStudyFieldDoesNotExist() {
        CreateCareerPathRequest request = new CreateCareerPathRequest();
        request.setTitle("Data Scientist");
        request.setStudyFieldIds(List.of(99));

        when(studyFieldRepository.findById(99)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> careerPathService.createCareerPath(request))
                .isInstanceOf(ResourceNotFoundException.class);

        verify(careerPathRepository, never()).save(any());
    }

    // Purpose: Update Career Path - applies Only Provided Fields.
    @Test
    void updateCareerPath_appliesOnlyProvidedFields() {
        CareerPath existing = CareerPath.builder()
                .careerPathId(5)
                .title("Old Title")
                .description("Old description")
                .build();

        when(careerPathRepository.findById(5)).thenReturn(Optional.of(existing));
        when(careerPathRepository.save(any(CareerPath.class))).thenAnswer(inv -> inv.getArgument(0));

        UpdateCareerPathRequest request = new UpdateCareerPathRequest();
        request.setTitle("New Title");
        // description and studyFieldIds intentionally left null -> should stay unchanged

        CareerPathResponse response = careerPathService.updateCareerPath(5, request);

        assertThat(response.getTitle()).isEqualTo("New Title");
        assertThat(response.getDescription()).isEqualTo("Old description");
        verify(studyFieldRepository, never()).findById(any());
    }

    // Purpose: Delete Career Path - throws When Not Found.
    @Test
    void deleteCareerPath_throwsWhenNotFound() {
        when(careerPathRepository.existsById(404)).thenReturn(false);

        assertThatThrownBy(() -> careerPathService.deleteCareerPath(404))
                .isInstanceOf(ResourceNotFoundException.class);

        verify(careerPathRepository, never()).deleteById(any());
    }
}
