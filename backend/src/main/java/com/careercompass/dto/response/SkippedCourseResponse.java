package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * A transcript course that could not contribute to the skill dashboard, and why.
 *
 * <p>Surfaced rather than swallowed. "You have not studied this" and "we could not read your
 * courses" produce the same empty bar on screen and mean opposite things, and only the second
 * is the system's fault.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkippedCourseResponse {

    private String courseCode;

    /** "no skill map" — no syllabus extracted yet — or "not passed". */
    private String reason;

    /** The transcript status, when the reason was that the course was not passed. */
    private String status;
}
