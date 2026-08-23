package com.careercompass.security.userdetails;

import com.careercompass.security.Role;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Lightweight representation of the currently authenticated user, built directly from
 * validated JWT claims (id, email, role) rather than from a Spring {@code UserDetails}
 * database lookup on every request.
 *
 * Rationale: CareerCompass has 5 separate actor tables (job_seekers, content_managers,
 * employers, administrators, experts) with no shared "users" table. Re-querying the correct
 * table on every authenticated request based on a role claim would work, but is unnecessary
 * extra DB load for a stateless JWT design — the token itself, once verified, is a trustworthy
 * source of identity for the duration of its validity. Endpoints/services that need the full
 * entity (not just id/email/role) look it up explicitly via the relevant repository.
 */
@Getter
@AllArgsConstructor
public class UserPrincipal {

    private final Integer userId;
    private final String email;
    private final Role role;
}
