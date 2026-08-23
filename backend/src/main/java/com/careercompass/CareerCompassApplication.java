package com.careercompass;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the CareerCompass backend.
 *
 * CareerCompass = "AI-powered Skills Enhancement and Job Matching System"
 * MEU Graduation Project — Basil Mohammad & Mohammed Al-Madhoun.
 *
 * This Spring Boot application implements the Container-level "Backend"
 * component from the project report (Section 5.1), internally organised
 * into the Component-level layers (Section 5.1, Figure 5.1.3):
 *   Security Layer -> Business Layer -> Integration Layer -> Data Access Layer
 *
 * The Data Analyses Layer (NLP / embeddings / skill-vector computation) is
 * NOT part of this application. It is a separate Python/FastAPI service
 * developed independently and consumed over REST via the Integration Layer
 * (see integration.ai.DataAnalysisClient).
 */
@SpringBootApplication
public class CareerCompassApplication {

    public static void main(String[] args) {
        SpringApplication.run(CareerCompassApplication.class, args);
    }

}
