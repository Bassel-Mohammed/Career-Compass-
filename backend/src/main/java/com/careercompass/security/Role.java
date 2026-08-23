package com.careercompass.security;

/**
 * The five actor roles from the report (Section 1.6 / Chapter 4), used for
 * role-based access control (NFR-SEC-04) and embedded as a claim in the JWT.
 */
public enum Role {
    JOB_SEEKER,
    CONTENT_MANAGER,
    EMPLOYER,
    ADMIN,
    EXPERT
}
