package com.careercompass.entity;

/** Lifecycle of a syllabus from durable upload through reviewed publication. */
public enum LearningOutcomeExtractionStatus {
    UPLOADED,
    QUEUED,
    EXTRACTING,
    READY_FOR_REVIEW,
    PUBLISHING,
    PUBLISHED,
    FAILED,
    CANCELLED
}
