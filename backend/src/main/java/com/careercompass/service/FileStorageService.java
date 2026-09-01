package com.careercompass.service;

import com.careercompass.config.FileStorageProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.UUID;

/**
 * Local-filesystem storage for uploaded learning-outcome PDFs (FR-CM-04). Kept as its own
 * small service so LearningOutcomeService's business logic doesn't mix with raw file I/O —
 * if this project later moves to cloud object storage (see FileStorageProperties' comment on
 * NFR-SCAL-02 statelessness), only this class needs to change.
 */
@Service
@RequiredArgsConstructor
public class FileStorageService {

    private final FileStorageProperties properties;

    /** Saves the file under a generated unique name; returns the path it was written to. */
    public String store(MultipartFile file) {
        try {
            Path directory = Paths.get(properties.getLearningOutcomesDir());
            Files.createDirectories(directory);

            String extension = ".pdf";
            String storedFilename = UUID.randomUUID() + extension;
            Path destination = directory.resolve(storedFilename);

            file.transferTo(destination);

            return destination.toString();
        } catch (IOException e) {
            throw new IllegalStateException("Could not store the uploaded file.", e);
        }
    }

    /**
     * Reads a stored file back, or returns {@code null} when it is gone. Extraction retries
     * need the original bytes; a missing file is the caller's cue to ask for a re-upload
     * rather than a server error.
     */
    public byte[] readIfExists(String filePath) {
        try {
            Path path = Paths.get(filePath);
            if (!Files.exists(path)) {
                return null;
            }
            return Files.readAllBytes(path);
        } catch (IOException e) {
            throw new IllegalStateException("Could not read the stored file at " + filePath, e);
        }
    }

    /** Deletes the file at the given path, if it exists. Safe to call even if already gone. */
    public void deleteIfExists(String filePath) {
        try {
            Files.deleteIfExists(Paths.get(filePath));
        } catch (IOException e) {
            throw new IllegalStateException("Could not delete the file at " + filePath, e);
        }
    }
}
