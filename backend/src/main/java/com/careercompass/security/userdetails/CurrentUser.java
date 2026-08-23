package com.careercompass.security.userdetails;

import org.springframework.security.core.annotation.AuthenticationPrincipal;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Convenience alias for {@code @AuthenticationPrincipal UserPrincipal}, so controller methods
 * can read {@code @CurrentUser UserPrincipal principal} instead of the longer Spring form.
 *
 * Using the authenticated principal's own id (rather than accepting a jobseekerId/employerId
 * path variable from the client) is a deliberate NFR-SEC-04 enforcement: a job seeker calling
 * "my profile" endpoints can only ever act on THEIR OWN record, because the id comes from the
 * verified JWT, never from client-supplied input.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@AuthenticationPrincipal
public @interface CurrentUser {
}
