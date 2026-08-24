package com.careercompass.controller;

import com.careercompass.dto.response.CareerPathResponse;
import com.careercompass.dto.response.StudyFieldResponse;
import com.careercompass.dto.response.UniversityResponse;
import com.careercompass.service.CareerPathService;
import com.careercompass.service.StudyFieldService;
import com.careercompass.service.UniversityService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Read-only lookup lists that every actor needs in order to fill in a form.
 *
 * <p>These same lists are already exposed under {@code /api/admin/**}, but that path is
 * restricted to ROLE_ADMIN — which left the people who actually need the values unable to
 * read them. A job seeker cannot satisfy FR-JS-07/09 without knowing the study field and
 * career path ids to send to {@code PUT /api/job-seekers/me}, and a content manager cannot
 * satisfy FR-CM-05 without the study field ids. Career path in particular is a hard
 * precondition for confirming a transcript, the skill dashboard, course recommendations and
 * job matches, so an unreadable list blocked the entire student journey.
 *
 * <p>Reading the catalogue of universities, study fields and career paths discloses nothing
 * about any user, so this is {@code authenticated()} rather than role-scoped — see the
 * {@code /api/reference/**} rule in SecurityConfig, which is declared before the role rules
 * because the first matching rule wins.
 *
 * <p>Deliberately read-only. Creating, updating and deleting these rows remains FR-SA-07/08/09/10
 * and stays on {@link AdminController} behind ROLE_ADMIN.
 */
@RestController
@RequestMapping("/api/reference")
@RequiredArgsConstructor
public class ReferenceDataController {

    private final StudyFieldService studyFieldService;
    private final CareerPathService careerPathService;
    private final UniversityService universityService;

    /** Feeds the study-field selector for FR-JS-07 and FR-CM-05. */
    @GetMapping("/study-fields")
    public ResponseEntity<List<StudyFieldResponse>> listStudyFields() {
        return ResponseEntity.ok(studyFieldService.listStudyFields());
    }

    /**
     * Feeds the career-path selector for FR-JS-09.
     *
     * <p>Every {@link CareerPathResponse} already carries the study fields it belongs to, so a
     * client showing "paths related to my field" filters this list itself rather than asking
     * for a second, narrower endpoint.
     */
    @GetMapping("/career-paths")
    public ResponseEntity<List<CareerPathResponse>> listCareerPaths() {
        return ResponseEntity.ok(careerPathService.listCareerPaths());
    }

    /** Feeds the university selector on the job seeker profile. */
    @GetMapping("/universities")
    public ResponseEntity<List<UniversityResponse>> listUniversities() {
        return ResponseEntity.ok(universityService.listUniversities());
    }
}
