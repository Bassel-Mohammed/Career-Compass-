package com.careercompass.controller;

import com.careercompass.dto.request.*;
import com.careercompass.dto.response.CareerPathResponse;
import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.dto.response.ExpertResponse;
import com.careercompass.dto.response.StudyFieldResponse;
import com.careercompass.dto.response.UniversityResponse;
import com.careercompass.service.CareerPathService;
import com.careercompass.service.ContentManagerAdminService;
import com.careercompass.service.ExpertAdminService;
import com.careercompass.service.StudyFieldService;
import com.careercompass.service.UniversityService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Administrator endpoints (Section 4.1.4 — FR-SA-xx). Access restricted to ROLE_ADMIN via
 * the `/api/admin/**` path rule in SecurityConfig.
 */
@RestController
@RequestMapping("/api/admin")
@RequiredArgsConstructor
public class AdminController {

    private final ContentManagerAdminService contentManagerAdminService;
    private final ExpertAdminService expertAdminService;
    private final StudyFieldService studyFieldService;
    private final CareerPathService careerPathService;
    private final UniversityService universityService;

    // --- Content Managers (FR-SA-02/03/04/05/06) ---------------------------------------

    @PostMapping("/content-managers")
    public ResponseEntity<ContentManagerResponse> createContentManager(
            @Valid @RequestBody CreateContentManagerRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(contentManagerAdminService.createContentManager(request));
    }

    @PutMapping("/content-managers/{id}")
    public ResponseEntity<ContentManagerResponse> updateContentManager(
            @PathVariable("id") Integer contentManagerId,
            @Valid @RequestBody UpdateContentManagerRequest request) {
        return ResponseEntity.ok(contentManagerAdminService.updateContentManager(contentManagerId, request));
    }

    @PatchMapping("/content-managers/{id}/activate")
    public ResponseEntity<ContentManagerResponse> activateContentManager(
            @PathVariable("id") Integer contentManagerId) {
        return ResponseEntity.ok(contentManagerAdminService.setActive(contentManagerId, true));
    }

    @PatchMapping("/content-managers/{id}/deactivate")
    public ResponseEntity<ContentManagerResponse> deactivateContentManager(
            @PathVariable("id") Integer contentManagerId) {
        return ResponseEntity.ok(contentManagerAdminService.setActive(contentManagerId, false));
    }

    @GetMapping("/content-managers")
    public ResponseEntity<List<ContentManagerResponse>> listContentManagers() {
        return ResponseEntity.ok(contentManagerAdminService.listContentManagers());
    }

    // --- Experts (FR-EX-01 account creation, by admin) ----------------------------------

    @PostMapping("/experts")
    public ResponseEntity<ExpertResponse> createExpert(@Valid @RequestBody CreateExpertRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(expertAdminService.createExpert(request));
    }

    @GetMapping("/experts")
    public ResponseEntity<List<ExpertResponse>> listExperts() {
        return ResponseEntity.ok(expertAdminService.listExperts());
    }

    // --- Study Fields (FR-SA-07) --------------------------------------------------------

    @PostMapping("/study-fields")
    public ResponseEntity<StudyFieldResponse> createStudyField(
            @Valid @RequestBody CreateStudyFieldRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(studyFieldService.createStudyField(request));
    }

    @GetMapping("/study-fields")
    public ResponseEntity<List<StudyFieldResponse>> listStudyFields() {
        return ResponseEntity.ok(studyFieldService.listStudyFields());
    }

    // --- Career Paths (FR-SA-08/09/10) --------------------------------------------------

    @PostMapping("/career-paths")
    public ResponseEntity<CareerPathResponse> createCareerPath(
            @Valid @RequestBody CreateCareerPathRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(careerPathService.createCareerPath(request));
    }

    @PutMapping("/career-paths/{id}")
    public ResponseEntity<CareerPathResponse> updateCareerPath(
            @PathVariable("id") Integer careerPathId,
            @Valid @RequestBody UpdateCareerPathRequest request) {
        return ResponseEntity.ok(careerPathService.updateCareerPath(careerPathId, request));
    }

    @DeleteMapping("/career-paths/{id}")
    public ResponseEntity<Void> deleteCareerPath(@PathVariable("id") Integer careerPathId) {
        careerPathService.deleteCareerPath(careerPathId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/career-paths")
    public ResponseEntity<List<CareerPathResponse>> listCareerPaths() {
        return ResponseEntity.ok(careerPathService.listCareerPaths());
    }

    // --- Universities (prerequisite for FR-SA-03) ---------------------------------------

    @PostMapping("/universities")
    public ResponseEntity<UniversityResponse> createUniversity(
            @Valid @RequestBody CreateUniversityRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(universityService.createUniversity(request));
    }

    @GetMapping("/universities")
    public ResponseEntity<List<UniversityResponse>> listUniversities() {
        return ResponseEntity.ok(universityService.listUniversities());
    }
}
