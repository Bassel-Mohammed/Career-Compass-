package com.careercompass.repository;

import com.careercompass.entity.Level;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `levels`.
 */
public interface LevelRepository extends JpaRepository<Level, Integer> {

    Optional<Level> findByLevelName(String levelName);
}
