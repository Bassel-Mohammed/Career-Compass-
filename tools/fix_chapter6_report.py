#!/usr/bin/env python3
"""Correct Chapter 6 of the CareerCompass graduation report.

The document is edited at the WordprocessingML level because Chapter 6 is
stored inside structured document tags that high-level DOCX libraries do not
enumerate reliably. Paragraph, run, table, and style XML is otherwise kept
unchanged.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "CareerCompass_Graduation_Project_Report.docx"
OUTPUT = ROOT / "CareerCompass_Graduation_Project_Report_Chapter6_Corrected.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

# Preserve the prefixes referenced by mc:Ignorable and by drawing parts. The
# source generator occasionally reuses wp14 locally, but ElementTree resolves
# those nodes by URI; registering the canonical prefixes produces valid XML.
NAMESPACES = {
    "w": W_NS,
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(W + "t")).strip()


def set_paragraph_text(paragraph: ET.Element, value: str) -> None:
    text_nodes = list(paragraph.iter(W + "t"))
    if not text_nodes:
        run = paragraph.find(W + "r")
        if run is None:
            run = ET.SubElement(paragraph, W + "r")
        text = ET.SubElement(run, W + "t")
        text_nodes = [text]

    text_nodes[0].text = value
    if value.startswith(" ") or value.endswith(" "):
        text_nodes[0].set(XML_SPACE, "preserve")
    else:
        text_nodes[0].attrib.pop(XML_SPACE, None)
    for node in text_nodes[1:]:
        node.text = ""


def cell_text(cell: ET.Element) -> str:
    return "".join(node.text or "" for node in cell.iter(W + "t")).strip()


def set_cell_text(cell: ET.Element, value: str) -> None:
    paragraphs = list(cell.iter(W + "p"))
    if not paragraphs:
        paragraphs = [ET.SubElement(cell, W + "p")]
    set_paragraph_text(paragraphs[0], value)
    for paragraph in paragraphs[1:]:
        set_paragraph_text(paragraph, "")


def row_values(row: ET.Element) -> list[str]:
    return [cell_text(cell) for cell in row.findall(W + "tc")]


def find_table(root: ET.Element, required: set[str]) -> ET.Element:
    for table in root.iter(W + "tbl"):
        values = {cell_text(cell) for cell in table.iter(W + "tc")}
        if required <= values:
            return table
    raise RuntimeError(f"Could not find table containing: {sorted(required)}")


def replace_once(paragraphs: list[ET.Element], old: str, new: str) -> None:
    matches = [paragraph for paragraph in paragraphs if paragraph_text(paragraph) == old]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one Chapter 6 paragraph {old!r}; found {len(matches)}")
    set_paragraph_text(matches[0], new)


def chapter_paragraphs(root: ET.Element) -> list[ET.Element]:
    paragraphs = list(root.iter(W + "p"))
    start = next(
        index for index, paragraph in enumerate(paragraphs)
        if paragraph_text(paragraph) == "Implementation"
    )
    end = next(
        index for index in range(start + 1, len(paragraphs))
        if paragraph_text(paragraphs[index]) == "References"
    )
    return paragraphs[start:end]


def apply_text_corrections(paragraphs: list[ET.Element]) -> None:
    replacements = [
        (
            "The system now consists of three cooperating parts: a Java backend, a Python AI service, and a React frontend developed as separate codebases and integrated through versioned contracts. Source code is referenced by file and line and reproduced in the appendices rather than pasted into the chapter body. No architecture diagrams are included; structure is instead described in the tables and paragraphs below.",
            "The system consists of three cooperating parts: a Java backend, a Python AI service, and a React frontend developed as separate codebases and integrated through versioned contracts. Source code is referenced by repository path and reproduced in the appendices rather than pasted into the chapter body. Structure is described in the tables and paragraphs below.",
        ),
        (
            "The browser client. Every actor role  Job Seeker, Employer, Content Manager, Expert, Administrator has its own set of pages, calling the backend exclusively.",
            "The browser client. Every actor role (Job Seeker, Employer, Content Manager, Expert, and Administrator) has its own pages, and all browser API calls go through the backend.",
        ),
        (
            "Java owns identity, authorisation, users, transcripts, jobs, consultations and quiz attempts; Python owns models, taxonomies, indexes and derived results. Python ia not the authoritative store for a student’s transcript or a quiz attempt, and the browser never calls Python directly every AI-derived value the frontend displays has passed through the backend first.",
            "Java owns identity, authorisation, users, transcripts, jobs, consultations, and quiz attempts; Python owns model integrations, taxonomies, indexes, and derived analyses. Python is not the authoritative store for a student’s transcript or quiz attempt. The browser never calls Python directly; every AI-derived value displayed by the frontend passes through the backend first.",
        ),
        (
            "The three tables below list every directory in each service and what it holds.",
            "The following tables summarise the principal source directories in each service and what they hold.",
        ),
        (
            "All Java packages sit under src/main/java/com/careercompass/, mirrored by the test tree under src/test/java/com/careercompass/.",
            "Most Java packages sit under src/main/java/com/careercompass/, mirrored by the test tree under src/test/java/com/careercompass/. The two Java Flyway migration classes sit separately under src/main/java/db/migration/.",
        ),
        (
            "REST controllers — 12 classes, 77 HTTP endpoints. Validation, status codes and nothing else; no business logic lives here.",
            "REST controllers: 12 classes with 80 HTTP mapping methods. They handle validation and status codes; business logic remains in services.",
        ),
        (
            "Outgoing response shapes (55 DTOs in total). Entities are never serialised directly, so the database schema cannot leak into the public API.",
            "Outgoing response shapes (30 response DTOs; 57 request and response DTO files in total). Entities are never serialised directly, so the database schema cannot leak into the public API.",
        ),
        (
            "The 33 JPA-mapped classes, one per database table, holding relationships and constraints.",
            "The entity directory contains 33 Java files: 28 table-mapped entities plus identifier, enumeration, and support types. The backend schema currently contains 30 tables.",
        ),
        (
            "util/",
            "util/ and validation/",
        ),
        (
            "Shared helpers with no domain meaning of their own.",
            "Shared helpers plus custom validation annotations and validators.",
        ),
        (
            "SQL and Java Flyway migrations (Section 6.1.6) — the schema’s single source of truth.",
            "SQL and Java Flyway migrations (Section 6.1.7); these are the schema’s single source of truth.",
        ),
        (
            "The FastAPI layer — 23 endpoints across 7 modules, including service-to-service authentication (Section 6.4.2) and the async job envelope for long extractions.",
            "The FastAPI layer declares 23 routes, including 22 versioned API routes and one root redirect. Its seven modules include service-to-service authentication (Section 6.3.2) and the asynchronous job envelope for long extractions.",
        ),
        (
            "Thirteen command-line entry points for the offline pipelines: build the taxonomy, extract skills, build the course catalogue, run migrations, and so on.",
            "Twelve CLI modules support the offline pipelines. Eleven expose a main function, and six are registered as installed console commands for tasks such as taxonomy construction, parsing, extraction, matching, and database migration.",
        ),
        (
            "19 test modules, 216 test functions, covering the parsers, matcher, and modules M2 through M6.",
            "19 test modules with 227 test functions, covering the parsers, matcher, API, database layer, and modules M2 through M6.",
        ),
        (
            "Built with Vite, TypeScript and React 19. 66 source files, roughly 10,500 lines.",
            "Built with Vite 8.2.2, TypeScript 6.0.2, and React 19.2.8. Excluding tests, the frontend contains 73 source files and approximately 14,300 lines. Six Vitest files contain 19 automated tests.",
        ),
        (
            "Nine pages: dashboard, transcript upload, courses, quizzes, mentors, jobs, profile, setup.",
            "Eight pages: dashboard, transcript upload, courses, quizzes, mentors, jobs, profile, and setup.",
        ),
        (
            "Ollama / Anthropic SDK",
            "Ollama / Anthropic / Gemini / OpenRouter",
        ),
        (
            "— / 0.40+",
            "Built-in REST / SDK 0.40+ / REST / REST",
        ),
        (
            "Two interchangeable providers for the constrained LLM decision step.",
            "Four interchangeable providers for constrained LLM decisions and generation. Production is configured to use Google Gemini; Ollama remains available for local execution.",
        ),
        (
            "Note : All three parts are containerised (a Dockerfile exists for backend, ai-service and frontend individually), and helper scripts under scripts/ verify the database migration layout for both the MySQL (backend) and PostgreSQL (AI service) schemas before deployment.",
            "Note: All three parts are containerised (a Dockerfile exists for the backend, AI service, and frontend), and helper scripts under scripts/ verify the migration layout for both the MySQL backend schema and PostgreSQL AI schema before deployment.",
        ),
        (
            "Measured from the repository at the time of writing. Line counts include comments and blank lines",
            "Measured from the current repository. Line counts include comments and blank lines.",
        ),
        (
            "Both databases moved from a single hand-maintained schema file to versioned, checksummed migrations .",
            "Both databases moved from a single hand-maintained schema file to versioned, checksummed migrations.",
        ),
        (
            "Five migrations, V1 through V5. Most are plain SQL; two (V2, V3) are written in Java because MySQL has no portable \"ADD COLUMN IF NOT EXISTS,\" and H2 (used in tests) does — a Java migration using JDBC metadata inspection is the one implementation that behaves identically on both databases without failing a database that already received an earlier hand-run patch.",
            "Six migrations, V1 through V6. Most are plain SQL; V2 and V3 are Java migrations because MySQL and H2 differ in portable support for conditional column changes. JDBC metadata inspection lets those migrations behave consistently without failing a database that already received an earlier hand-run patch. V6 persists recommendation reasoning.",
        ),
        (
            "Six migrations, 001 through 006, tracked with SHA-256 checksums of each applied script. Migrations 004 and 005 have been rehearsed against a restored backup — applied, checksummed, repeat-run as a verified no-op, and confirmed not to disturb existing row counts — but not yet run against the live database, which requires a separate operator-approved change window.",
            "Six migrations, 001 through 006, are tracked with SHA-256 checksums by a custom runner. The runner validates contiguous versions and applied checksums. Production Compose disables automatic AI-database migration, so these scripts must be applied explicitly before deployment.",
        ),
        (
            "Java. Standard Oracle conventions apply  PascalCase types, camelCase members, UPPER_SNAKE constants  with several project-specific rules:",
            "Java. Standard Oracle conventions apply: PascalCase types, camelCase members, and UPPER_SNAKE constants, together with several project-specific rules:",
        ),
        (
            "Javadoc on every non-trivial class and method cites the requirement it implements, for example \"FR-JS-20: quiz results replace the grade-derived score.\"",
            "Javadoc is used on non-trivial classes and methods and often cites the implemented requirement, for example, \"FR-JS-20: quiz results replace the grade-derived score.\"",
        ),
        (
            "Named constants for every threshold and weight, defined at module top with the reasoning attached.",
            "Named module-level constants are used for scoring thresholds and weights, with nearby comments explaining their purpose.",
        ),
        (
            "Cross-cutting. Significant decisions are recorded as Architecture Decision Records under docs/adr/. Each states context, decision and consequences, and is referenced from the code it governs. Two ADRs were revised during this iteration: ADR-005 (mentor-matching scope) was formally superseded by ADR-008 once the product owner asked for AI-ranked mentor matching explicitly, and ADR-007 (migration framework) replaced the single-schema-file approach. The wire contract between backend and AI service is a versioned OpenAPI document rather than prose, so both sides can be validated against it.",
            "Cross-cutting. Significant decisions are recorded as Architecture Decision Records under docs/adr/. Each states context, decision, and consequences and is referenced from the code it governs. ADR-005 (mentor-matching scope) was superseded by ADR-008 when AI-ranked mentor matching was brought into scope, while ADR-007 formalised the migration framework. The backend-to-AI wire contract is the authoritative OpenAPI v1.2.0 document rather than a prose description.",
        ),
        (
            "Processor and memory. 11th Generation Intel Core i7-1165G7 at 2.80 GHz, with 16 GB RAM (15.8 GB usable).",
            "Processor and memory. The current host uses a 12th Generation Intel Core i7-12650H with 10 cores, 16 threads, and a maximum frequency of 4.7 GHz, together with approximately 16 GB RAM.",
        ),
        (
            "Graphics. NVIDIA GeForce MX450 with 2 GB dedicated memory and Intel Iris Xe integrated graphics. The limited GPU memory is insufficient for running the project’s recommended larger language model locally. Therefore, the deployed system uses the hosted Google Gemini 3.5 Flash Lite API for quiz generation and other language-model operations, while deterministic processing and database operations continue to run locally on the server.",
            "Graphics. The current host exposes an NVIDIA GeForce RTX 4060 Max-Q and Intel integrated graphics. The production configuration uses the hosted Google Gemini 3.5 Flash Lite API for quiz generation and other language-model operations, while deterministic processing and database operations continue to run locally.",
        ),
        (
            "Storage. The laptop provides 1 TB of total storage.",
            "Storage. The current host provides a 476.9 GB Samsung NVMe drive.",
        ),
        (
            "A corpus of 2,238 job postings spanning nine career paths is collected and normalised. Terms are extracted and matched against the taxonomy, and request frequency across a path becomes that path’s demand signal. The result is 771 requirements, 82 to 105 per career path, now additionally carrying a skill_type classification distinguishing technical from soft skills, added as part of this iteration’s work on ranking quality.",
            "A corpus of 2,238 job postings spanning nine career paths is collected and normalised. Terms are extracted and matched against the taxonomy, and request frequency across a path becomes that path’s demand signal. The result is 771 requirements, ranging from 43 to 105 per career path, with a skill_type classification that distinguishes technical and soft skills for ranking.",
        ),
        (
            "Each syllabus PDF is parsed into course details, description, learning outcomes, weekly topics, labs and assessments, and candidate skill terms are extracted with a base weight per section: a learning outcome scores highest, since it states directly what a student should be able to do, down to the course description, which is useful but broad. Extracted terms are resolved against the taxonomy by the matching cascade (Section 6.4.1), and each result is stored with its status: accepted, needs review, or no match. Real syllabi have been processed for 20 of 114 courses; this remains the project’s largest data-collection task, unchanged by this iteration.",
            "Each syllabus PDF is parsed into course details, description, learning outcomes, weekly topics, labs, and assessments. Candidate skill terms receive a base weight by section: a learning outcome scores highest because it states what a student should be able to do, while a course description is useful but broader. Extracted terms are resolved against the taxonomy by the matching cascade (Section 6.3.1), and each result is stored as accepted, needs review, or no match. Eighteen of the 114 required courses currently have an extracted real syllabus. Twenty real extracted syllabi exist overall, but two are outside the required course set; collecting the remainder is still the largest data task.",
        ),
        (
            "New in this iteration. The student’s frontend mentors page requests a ranked mentor list; the backend gathers the student’s unmet skill gaps and the pool of active experts, and sends both to the AI service’s mentor-matching endpoint. Each mentor is scored and returned with an explanation and an evidence signal (Section 6.3.5) rather than a bare rank, so the frontend can show the student why a mentor was suggested and how confident that suggestion is.",
            "New in this iteration. The student’s frontend mentors page requests a ranked mentor list; the backend gathers the student’s unmet skill gaps and the pool of active experts and sends both to the AI service’s mentor-matching endpoint. Each mentor is returned with a deterministic score, an explanation, and an evidence signal, as described by Algorithm 6 in Section 6.3.1, so the frontend can explain the suggestion and the evidence behind it.",
        ),
        (
            "LLM generation, programmatic validation, programmatic grading",
            "LLM generation and optional self-check; programmatic validation and grading",
        ),
        (
            "Not started",
            "AI scoring descoped",
        ),
        (
            "Descoped by owner decision; backend flow complete against a mock client",
            "Owner-descoped from v1; the backend and frontend demonstration flow uses mock scoring, while the real HTTP client returns 501.",
        ),
        (
            "One rule holds across every module: a language model may produce prose, never a number. M2 and M3 contain no model call; M3’s only model-generated field is narrative explanation of numbers already computed. M5’s model writes questions but grading is arithmetic. M6’s mentor scoring is entirely deterministic; no model is involved at all, by design, so the same request always produces the same ranking (Section 6.3.5).",
            "One rule holds across the student-facing analysis modules: a language model does not produce proficiency, gap, recommendation, quiz-grade, or mentor-ranking scores. M2 contains no model call. M3 may use a model only for narrative explanation after all numbers are final. M5 uses a model to generate questions, a constrained answer index, and an optional self-check, but grading is arithmetic. M6 mentor scoring is entirely deterministic, so the same request produces the same ranking (Algorithm 6 in Section 6.3.1).",
        ),
        (
            "The backend and AI service were developed separately, making the interface between them a significant integration risk. Four mechanisms control it.",
            "The backend and AI service were developed separately, making their interface a significant integration risk. Four mechanisms control it.",
        ),
        (
            "A versioned contract. The interface is an OpenAPI document rather than a prose description, now at v1.1.0 following the additive mentor-matching endpoint. It defines the operations listed in the table below; the AI service exposes 23 endpoints in total, the remainder serving the offline pipelines and not called by the backend.",
            "A versioned contract. The authoritative interface is OpenAPI v1.2.0. The table below lists the versioned operations used by the Java backend, including the M8 proposal, review, and publication workflow. The FastAPI application declares 23 routes in total; routes outside the contract support health, local, legacy, or offline workflows.",
        ),
        (
            "Per-operation deadlines. Each AI-backed operation carries its own timeout: 30 seconds for transcript extraction, 10 for the skill vector and gap, 15 for quiz generation, 5 for recommendations and the timeout is enforced by cancelling a call that overruns and surfacing a 504, rather than sharing one timeout across operations of very different cost.",
            "Per-operation deadlines. Production uses 30 seconds for transcript extraction, syllabus work, and publication; 10 seconds for skill vectors, gaps, taxonomy lookups, and mentor matching; 5 seconds for recommendations; and 90 seconds for quiz generation. A call that overruns its deadline is cancelled and surfaced as a 504.",
        ),
        (
            "Service-to-service authentication. New in this iteration. Every call from the backend to the AI service now carries a bearer token that the AI service validates before processing any request; previously the contract declared this scheme but the AI service silently ignored it, so anything able to reach the port could read parsed transcripts and quiz answer keys. Enforcement is opt-in through an environment variable specifically so a deployment that forgets to configure it fails loudly on its first call rather than silently running unauthenticated; a blank default would have meant a shared secret checked into the repository, the same failure mode a hard-coded signing key would create.",
            "Service-to-service authentication. Non-health /api/v1 requests require a shared bearer token when CC_SERVICE_TOKEN is configured; health endpoints remain public for container probes. A blank token disables enforcement for local development and produces a startup warning. Production Compose requires the same token for both services before startup, preventing an accidentally unauthenticated production deployment without publishing a default secret in the repository.",
        ),
        (
            "A switchable client. The AI client remains an interface with a real and a mock implementation, so the backend and its 74-case system test run without the AI service present.",
            "A switchable client. The AI client remains an interface with real and mock implementations, so the backend and its 77-case system test can run without the AI service present.",
        ),
        (
            "6.4 Additional Implementation Details",
            "6.3 Additional Implementation Details",
        ),
        (
            "6.4.1 Critical Algorithms",
            "6.3.1 Critical Algorithms",
        ),
        (
            "Algorithm 1 — Skill matching decision cascade",
            "Algorithm 1: Skill matching decision cascade",
        ),
        (
            "If the lookup hits a generic single-word alias, accept only if the surrounding evidence provides context; otherwise route to review — capitalisation alone is not treated as evidence.",
            "If the lookup hits a generic single-word alias, accept only if the surrounding evidence provides context; otherwise route it to review because capitalisation alone is not evidence.",
        ),
        (
            "Algorithm 2 — Student Skill Vector (M2)",
            "Algorithm 2: Student Skill Vector (M2)",
        ),
        (
            "For each confirmed course, skip it if not passed or marked as a transfer credit.",
            "For each confirmed course, skip it if it was not completed for credit. Keep transfer credit as coverage evidence, but exclude it from the graded proficiency denominator because it has no mark.",
        ),
        (
            "Accumulate, per skill, the sum of (evidence × attainment) and the sum of evidence alone.",
            "For graded courses, accumulate weighted attainment and graded evidence. Separately accumulate total evidence coverage for both graded courses and transfer credit.",
        ),
        (
            "Divide the two sums to produce proficiency (0 to 1); the evidence sum alone is coverage.",
            "Divide weighted attainment by graded evidence to produce proficiency (0 to 1); report total evidence, including transfer-credit evidence, as coverage.",
        ),
        (
            "Algorithm 3 — Skill gap and priority (M3)",
            "Algorithm 3: Skill gap and priority (M3)",
        ),
        (
            "Algorithm 4 — Course recommendation ranking (M4)",
            "Algorithm 4: Course recommendation ranking (M4)",
        ),
        (
            "Skip non-English courses.",
            "Keep non-English courses when no preferred-language alternative is available, but multiply their relevance by the 0.25 language penalty.",
        ),
        (
            "For each candidate, compute title-match similarity, a level-fit score (does the course match the student’s Strong/Moderate/Weak classification for that skill), and the skill’s normalised market importance.",
            "For each candidate, compute a binary title-match value, a level-fit score for the student’s classification, and the skill’s normalised market importance. If a platform rating exists, apply its small multiplicative adjustment.",
        ),
        (
            "Rank candidates by relevance multiplied by the originating gap’s priority, and take the highest-scoring courses.",
            "Rank candidates by relevance multiplied by (0.25 + gap priority), and take the highest-scoring courses.",
        ),
        (
            "Algorithm 5 — Quiz generation, validation and grading (M5)",
            "Algorithm 5: Quiz generation, validation and grading (M5)",
        ),
        (
            "Return the accepted questions to the caller; return the answer key separately, to the backend only, never to the browser.",
            "Optionally run the model self-consistency check, dropping questions whose regenerated answer disagrees with their key. Return accepted questions and the separate answer key to the backend, never to the browser.",
        ),
        (
            "On submission, grade by direct comparison against the stored key — no model call — and compute the percentage correct.",
            "On submission, grade by direct comparison against the stored key, with no model call, and compute the percentage correct.",
        ),
        (
            "Algorithm 6 — Mentor matching score (M6)",
            "Algorithm 6: Mentor matching score (M6)",
        ),
        (
            "Attach the evidence signal and a human-readable explanation to the result, and rank mentors by score, breaking ties on mentor id.",
            "Attach the evidence signal and a human-readable explanation. Rank by score, then by gaps addressed, and finally by mentor id for deterministic ties.",
        ),
        (
            "6.4.2 Authentication and Session Termination",
            "6.3.2 Authentication and Session Termination",
        ),
        (
            "A parallel mechanism now protects the backend’s own calls to the AI service (Section 6.2.5): a shared service-bearer token, checked by the AI service on every /api/v1/* request once configured, closing a gap where the two sides previously agreed on a security scheme that only one side actually enforced.",
            "A parallel mechanism protects the backend’s calls to the AI service (Section 6.2.5): a shared service bearer token is checked on non-health /api/v1 requests when configured. Production requires the token before startup, while local development may run without it and logs a warning.",
        ),
    ]

    for old, new in replacements:
        replace_once(paragraphs, old, new)

    # The migration references both pointed to the implementation-size section.
    for paragraph in paragraphs:
        text = paragraph_text(paragraph)
        if "Section 6.1.6" in text:
            set_paragraph_text(paragraph, text.replace("Section 6.1.6", "Section 6.1.7"))


def update_size_table(root: ET.Element) -> None:
    table = find_table(root, {"Measure", "Source files", "Test files", "HTTP endpoints"})
    updates = {
        "Source files": ["Source files", "215", "64", "73", "Excluding tests"],
        "Test files": ["Test files", "28", "19", "6", "Frontend uses Vitest"],
        "Lines of code (source)": ["Lines of code (source)", "13,715", "16,538", "14,287", "Comments and blank lines included"],
        "Lines of code (tests)": ["Lines of code (tests)", "7,026", "5,860", "304", "Test support files included"],
        "Packages / directories": ["Packages / directories", "18", "7", "11", "Java package directories containing source; Python subpackages; frontend src/ subdirectories"],
        "HTTP endpoints": ["HTTP endpoints", "80", "23", "N/A", "Backend mapping methods; AI declared routes, including the root redirect"],
        "Database tables": ["Database tables", "30", "13", "N/A", "AI count includes its migration-history table"],
        "SQL migration scripts": ["SQL migration scripts", "6 (Flyway)", "6 (numbered)", "N/A", "Two schemas, migrated independently"],
        "Test methods / functions": ["Test methods / functions", "234", "227", "19", "Backend total includes a 77-case system test"],
        "Total": ["Total", "20,741 LOC", "22,398 LOC", "14,591 LOC", "57,730 lines across all three parts"],
    }

    for row in table.findall(W + "tr"):
        cells = row.findall(W + "tc")
        values = row_values(row)
        if not values or values[0] not in updates:
            continue
        replacement = updates[values[0]]
        if len(cells) != len(replacement):
            raise RuntimeError(f"Unexpected implementation-size row shape: {values}")
        for cell, value in zip(cells, replacement):
            set_cell_text(cell, value)


def update_technology_tables(root: ET.Element) -> None:
    backend = find_table(root, {"Technology", "Spring Boot", "MapStruct", "springdoc-openapi"})
    backend_versions = {
        "JJWT": "0.12.6",
        "MapStruct": "1.6.2",
        "springdoc-openapi": "2.6.0",
    }
    for row in backend.findall(W + "tr"):
        cells = row.findall(W + "tc")
        values = row_values(row)
        if values and values[0] in backend_versions:
            set_cell_text(cells[1], backend_versions[values[0]])

    ai = find_table(root, {"Technology", "FastAPI", "sentence-transformers", "black"})
    for row in ai.findall(W + "tr"):
        cells = row.findall(W + "tc")
        values = row_values(row)
        if values and values[0] == "black":
            set_cell_text(cells[1], "Unpinned")


def update_layer_table(root: ET.Element) -> None:
    table = find_table(root, {"DTOs", "Integration", "Entities", "Utilities"})
    rows = table.findall(W + "tr")
    expected = {
        "DTOs": "57",
        "Security": "7",
    }
    for row in rows:
        cells = row.findall(W + "tc")
        values = row_values(row)
        for label, count in expected.items():
            if label in values:
                index = values.index(label)
                set_cell_text(cells[index + 1], count)
        if values and values[0] == "Config":
            set_cell_text(cells[4], "Validation")
            set_cell_text(cells[5], "1")

    # Clarify that 33 is a directory-file count, not 33 mapped tables.
    for row in rows:
        cells = row.findall(W + "tc")
        values = row_values(row)
        if "Entities" in values:
            set_cell_text(cells[values.index("Entities")], "Entity files")


def update_contract_table(root: ET.Element) -> None:
    table = find_table(root, {"Endpoint", "POST /api/v1/mentor-matches", "Liveness and readiness"})
    rows = table.findall(W + "tr")
    template = next(row for row in rows if row_values(row)[0] == "POST /api/v1/mentor-matches")
    health = next(row for row in rows if row_values(row)[0].startswith("GET /api/v1/health"))
    insertion_index = list(table).index(health)

    additions = [
        ("GET /api/v1/career-paths/skills", "M3", "Career path in; current market requirements and demand bands out"),
        ("POST /api/v1/extractions", "M8", "Queue a syllabus-extraction proposal for content-manager review"),
        ("GET/DELETE /api/v1/extractions/{id}", "M8", "Poll or cancel an asynchronous extraction proposal"),
        ("GET /api/v1/taxonomy/skills", "M8", "Search canonical skills while reviewing extracted terms"),
        ("PUT /api/v1/course-maps/{version}", "M8", "Publish an approved, immutable course-to-skill map"),
    ]
    for offset, values in enumerate(additions):
        row = copy.deepcopy(template)
        cells = row.findall(W + "tc")
        for cell, value in zip(cells, values):
            set_cell_text(cell, value)
        table.insert(insertion_index + offset, row)

    health_cells = health.findall(W + "tc")
    set_cell_text(health_cells[1], "Health")


def normalise_chapter_punctuation(paragraphs: list[ET.Element]) -> None:
    for paragraph in paragraphs:
        original = paragraph_text(paragraph)
        if not original:
            continue
        text = original
        if original == "—":
            text = "N/A"
        else:
            text = text.replace(" — ", "; ").replace("—", ":")
        text = re.sub(r" {2,}", " ", text)
        if text != original:
            set_paragraph_text(paragraph, text)


def request_field_refresh(settings: bytes) -> bytes:
    root = ET.fromstring(settings)
    node = root.find(W + "updateFields")
    if node is None:
        node = ET.SubElement(root, W + "updateFields")
    node.set(W + "val", "true")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> int:
    if not SOURCE.exists():
        print(f"Source report not found: {SOURCE}", file=sys.stderr)
        return 1

    with ZipFile(SOURCE, "r") as source_zip:
        document = ET.fromstring(source_zip.read("word/document.xml"))
        chapter = chapter_paragraphs(document)
        apply_text_corrections(chapter)
        update_technology_tables(document)
        update_size_table(document)
        update_layer_table(document)
        update_contract_table(document)
        chapter = chapter_paragraphs(document)
        normalise_chapter_punctuation(chapter)

        document_bytes = ET.tostring(document, encoding="utf-8", xml_declaration=True)
        # The source already requests a field refresh. Keep this part byte-for-byte
        # so its intentionally declared compatibility namespaces remain intact.
        settings_bytes = source_zip.read("word/settings.xml")

        with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as output_zip:
            for info in source_zip.infolist():
                if info.filename == "word/document.xml":
                    payload = document_bytes
                elif info.filename == "word/settings.xml":
                    payload = settings_bytes
                else:
                    payload = source_zip.read(info.filename)
                output_zip.writestr(info, payload)

    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
