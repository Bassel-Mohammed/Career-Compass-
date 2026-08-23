package com.careercompass.repository;

import com.careercompass.entity.Administrator;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `administrators`.
 * findByEmail supports FR-SA-01 (admin login) / FR-SA-11 (authenticate admin).
 */
public interface AdministratorRepository extends JpaRepository<Administrator, Integer> {

    Optional<Administrator> findByEmail(String email);

    boolean existsByEmail(String email);
}
