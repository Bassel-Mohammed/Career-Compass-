#!/usr/bin/env python3
"""Generate a corrected Chen-style ERD matching the report's original theme."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "careercompass-ai-postgresql-erd-chen-style-corrected.png"

WIDTH, HEIGHT = 13000, 7200
BLACK = "#111111"
WHITE = "#FFFFFF"
LIGHT = "#FAFAFA"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def font(name: str, size: int):
    return ImageFont.truetype(str(FONT_DIR / name), size)


TITLE_FONT = font("DejaVuSans-Bold.ttf", 62)
SUBTITLE_FONT = font("DejaVuSans.ttf", 28)
ENTITY_FONT = font("DejaVuSans-Bold.ttf", 29)
REL_FONT = font("DejaVuSans-Bold.ttf", 21)
ATTR_FONT = font("DejaVuSans.ttf", 20)
ATTR_KEY_FONT = font("DejaVuSans-Bold.ttf", 20)
CARD_FONT = font("DejaVuSans-Bold.ttf", 25)
NOTE_FONT = font("DejaVuSans.ttf", 22)


@dataclass(frozen=True)
class Attribute:
    name: str
    flags: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.flags})" if self.flags else self.name


@dataclass(frozen=True)
class Entity:
    name: str
    center: tuple[int, int]
    attributes: tuple[Attribute, ...]
    radius: tuple[int, int]
    angle_range: tuple[float, float]


def a(name: str, flags: str = "") -> Attribute:
    return Attribute(name, flags)


ENTITIES = (
    Entity("LINKEDIN_JOBS", (1050, 1250), (
        a("id", "PK"), a("career_path"), a("search_query"), a("title"),
        a("company_name"), a("location"), a("url", "UQ"), a("description"),
        a("seniority_level"), a("employment_type"), a("job_function"),
        a("industries"), a("posted_date"), a("scraped_at"), a("is_relevant"),
    ), (720, 520), (120, 340)),
    Entity("LINKEDIN_JOB_SKILLS", (1050, 3300), (
        a("id", "PK"), a("linkedin_job_id", "FK"), a("skill_name"),
        a("linkedin_job_id + skill_name", "UQ"),
    ), (570, 360), (20, 160)),
    Entity("JOB_SKILLS", (3350, 1850), (
        a("id", "PK"), a("job_id", "FK"), a("term"), a("sources"), a("level"),
        a("weight"), a("skill_id", "FK, nullable"), a("match_method"),
        a("match_score"), a("review_status"), a("taxonomy_version"),
        a("created_at"), a("job_id + term", "UQ"),
    ), (820, 560), (75, 285)),
    Entity("CAREER_PATH_SKILLS", (3350, 4550), (
        a("id", "PK"), a("career_path"), a("skill_id", "FK"), a("posting_count"),
        a("sample_size"), a("coverage"), a("required_score"), a("required_level"),
        a("derived_from"), a("taxonomy_version"), a("updated_at"),
        a("skill_type", "nullable"), a("career_path + skill_id", "UQ"),
    ), (820, 540), (70, 290)),
    Entity("TAXONOMY_SKILL_ALIASES", (5050, 620), (
        a("id", "PK"), a("skill_id", "FK"), a("alias"), a("alias_normalized"),
        a("language"), a("skill_id + alias_normalized", "UQ"),
    ), (680, 360), (190, 350)),
    Entity("TAXONOMY_SKILLS", (6350, 2700), (
        a("skill_id", "PK"), a("label"), a("source"), a("skill_type"),
        a("description"), a("uri"), a("label_ar"), a("taxonomy_version"),
        a("updated_at"),
    ), (760, 500), (190, 350)),
    Entity("CATALOG_COURSE_SKILLS", (6350, 4900), (
        a("id", "PK"), a("course_id", "FK"), a("skill_id", "FK"),
        a("in_title"), a("course_id + skill_id", "UQ"),
    ), (680, 370), (195, 345)),
    Entity("CATALOG_COURSES", (6350, 6450), (
        a("course_id", "PK"), a("platform"), a("title"), a("url"), a("level"),
        a("language"), a("duration_hours"), a("rating"), a("fetched_at"),
    ), (820, 480), (10, 170)),
    Entity("COURSE_SKILLS", (8950, 1050), (
        a("id", "PK"), a("course_code"), a("term"), a("level"), a("weight"),
        a("evidence_count"), a("sources"), a("evidence", "JSONB"),
        a("skill_id", "FK, nullable"), a("match_method"), a("match_score"),
        a("review_status"), a("match_reason"), a("candidates", "JSONB"),
        a("taxonomy_version"), a("matched_at"), a("course_code + term", "UQ"),
    ), (900, 650), (130, 500)),
    Entity("SKILL_MATCH_REVIEWS", (9850, 2800), (
        a("id", "PK"), a("term_normalized", "UQ"), a("skill_id", "FK, nullable"),
        a("decision"), a("reviewer"), a("note"), a("reviewed_at"),
    ), (720, 430), (170, 520)),
    Entity("COURSE_MAP_HEADS", (9850, 4650), (
        a("institution_code", "PK"), a("catalog_version", "PK"),
        a("course_code", "PK"), a("course_map_version", "FK"), a("updated_at"),
    ), (740, 400), (190, 350)),
    Entity("COURSE_MAP_PUBLICATIONS", (9850, 6450), (
        a("course_map_version", "PK"), a("institution_code"), a("catalog_version"),
        a("course_code"), a("qualified_course_key"), a("source_outcome_id"),
        a("taxonomy_version"), a("payload_sha256"), a("artifact_filename"),
        a("skill_count"), a("payload", "JSONB"), a("published_at"),
        a("institution + catalog + course + version", "UQ"),
    ), (900, 620), (5, 175)),
    Entity("CAREERCOMPASS_AI_SCHEMA_HISTORY", (11950, 4900), (
        a("version", "PK"), a("filename", "UQ"), a("checksum"), a("applied_at"),
    ), (520, 350), (180, 540)),
)


ENTITY_BY_NAME = {entity.name: entity for entity in ENTITIES}


RELATIONSHIPS = (
    ("LINKEDIN_JOBS", "LINKEDIN_JOB_SKILLS", "HAS_RAW_SKILL", "1", "N", (1050, 2250)),
    ("LINKEDIN_JOBS", "JOB_SKILLS", "EXTRACTS", "1", "N", (2200, 1450)),
    ("JOB_SKILLS", "TAXONOMY_SKILLS", "RESOLVES_TO", "N", "0..1", (4850, 2200)),
    ("CAREER_PATH_SKILLS", "TAXONOMY_SKILLS", "REQUIRES_SKILL", "N", "1", (4850, 4050)),
    ("TAXONOMY_SKILL_ALIASES", "TAXONOMY_SKILLS", "HAS_ALIAS", "N", "1", (5700, 1550)),
    ("COURSE_SKILLS", "TAXONOMY_SKILLS", "MAPS_TO_SKILL", "N", "0..1", (7700, 1850)),
    ("SKILL_MATCH_REVIEWS", "TAXONOMY_SKILLS", "CONFIRMS_SKILL", "N", "0..1", (8100, 2800)),
    ("CATALOG_COURSE_SKILLS", "TAXONOMY_SKILLS", "COVERS", "N", "1", (6350, 3800)),
    ("CATALOG_COURSE_SKILLS", "CATALOG_COURSES", "TEACHES", "N", "1", (6350, 5650)),
    # This is the cardinality PostgreSQL actually enforces. The FK column in
    # course_map_heads is not unique, so it is not a physical one-to-one link.
    ("COURSE_MAP_HEADS", "COURSE_MAP_PUBLICATIONS", "ACTIVE_HEAD", "N", "1", (9850, 5550)),
)


ENTITY_W = 440
ENTITY_H = 112
ATTR_W = 350
ATTR_H = 70
DIAMOND_W = 390
DIAMOND_H = 150


def text_center(draw, center, value, used_font, fill=BLACK):
    box = draw.textbbox((0, 0), value, font=used_font)
    draw.text((center[0] - (box[2] - box[0]) / 2, center[1] - (box[3] - box[1]) / 2 - 2), value, font=used_font, fill=fill)


def boundary_point(start, end, padding=0):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return start
    scale = max(abs(dx) / (ENTITY_W / 2 + padding), abs(dy) / (ENTITY_H / 2 + padding))
    return (int(start[0] + dx / scale), int(start[1] + dy / scale))


def diamond_points(center):
    x, y = center
    return ((x, y - DIAMOND_H // 2), (x + DIAMOND_W // 2, y), (x, y + DIAMOND_H // 2), (x - DIAMOND_W // 2, y))


def entity_attribute_positions(entity):
    start, end = entity.angle_range
    count = len(entity.attributes)
    if count == 1:
        angles = [(start + end) / 2]
    else:
        angles = [start + (end - start) * i / (count - 1) for i in range(count)]
    positions = []
    for angle in angles:
        radians = math.radians(angle)
        positions.append((
            int(entity.center[0] + entity.radius[0] * math.cos(radians)),
            int(entity.center[1] + entity.radius[1] * math.sin(radians)),
        ))
    return positions


def draw_relationships(draw):
    for left_name, right_name, label, left_card, right_card, center in RELATIONSHIPS:
        left = ENTITY_BY_NAME[left_name].center
        right = ENTITY_BY_NAME[right_name].center
        points = diamond_points(center)
        left_end = min(points, key=lambda p: (p[0] - left[0]) ** 2 + (p[1] - left[1]) ** 2)
        right_end = min(points, key=lambda p: (p[0] - right[0]) ** 2 + (p[1] - right[1]) ** 2)
        draw.line((boundary_point(left, center), left_end), fill=BLACK, width=4)
        draw.line((boundary_point(right, center), right_end), fill=BLACK, width=4)
        draw.polygon(points, fill=WHITE, outline=BLACK)
        draw.line((*points[0], *points[1]), fill=BLACK, width=4)
        draw.line((*points[1], *points[2]), fill=BLACK, width=4)
        draw.line((*points[2], *points[3]), fill=BLACK, width=4)
        draw.line((*points[3], *points[0]), fill=BLACK, width=4)
        text_center(draw, center, label, REL_FONT)
        lx = int(left[0] * 0.72 + center[0] * 0.28)
        ly = int(left[1] * 0.72 + center[1] * 0.28)
        rx = int(right[0] * 0.72 + center[0] * 0.28)
        ry = int(right[1] * 0.72 + center[1] * 0.28)
        text_center(draw, (lx, ly - 32), left_card, CARD_FONT)
        text_center(draw, (rx, ry - 32), right_card, CARD_FONT)


def draw_attribute(draw, entity, attribute, center):
    ex, ey = entity.center
    cx, cy = center
    dx = cx - ex
    dy = cy - ey
    length = math.hypot(dx, dy) or 1
    oval_edge = (int(cx - dx / length * ATTR_W / 2), int(cy - dy / length * ATTR_H / 2))
    draw.line((boundary_point(entity.center, center), oval_edge), fill=BLACK, width=3)
    box = (cx - ATTR_W // 2, cy - ATTR_H // 2, cx + ATTR_W // 2, cy + ATTR_H // 2)
    draw.ellipse(box, fill=WHITE, outline=BLACK, width=3)
    used_font = ATTR_KEY_FONT if "PK" in attribute.flags else ATTR_FONT
    text_center(draw, center, attribute.label, used_font)
    if "PK" in attribute.flags:
        text_box = draw.textbbox((0, 0), attribute.label, font=used_font)
        tw = text_box[2] - text_box[0]
        draw.line((cx - tw / 2, cy + 14, cx + tw / 2, cy + 14), fill=BLACK, width=2)


def draw_entity(draw, entity):
    for attribute, position in zip(entity.attributes, entity_attribute_positions(entity)):
        draw_attribute(draw, entity, attribute, position)
    cx, cy = entity.center
    box = (cx - ENTITY_W // 2, cy - ENTITY_H // 2, cx + ENTITY_W // 2, cy + ENTITY_H // 2)
    draw.rectangle(box, fill=LIGHT, outline=BLACK, width=5)
    text_center(draw, entity.center, entity.name, ENTITY_FONT)


def main():
    image = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(image)
    draw.text((100, 55), "CareerCompass AI Service PostgreSQL ERD", font=TITLE_FONT, fill=BLACK)
    draw.text(
        (105, 135),
        "Corrected Chen notation based on migrations 001-006 and the migration-history table",
        font=SUBTITLE_FONT,
        fill=BLACK,
    )

    draw_relationships(draw)
    for entity in ENTITIES:
        draw_entity(draw, entity)

    note = (
        "Cardinality note: COURSE_MAP_HEADS to COURSE_MAP_PUBLICATIONS is N:1 because course_map_version is not unique in COURSE_MAP_HEADS. "
        "Add a unique or composite foreign-key constraint if the intended physical relationship is 0..1:1."
    )
    draw.rounded_rectangle((8350, 170, 12750, 280), radius=18, fill="#FFF8E7", outline=BLACK, width=3)
    draw.text((8380, 205), note, font=NOTE_FONT, fill=BLACK)

    image.save(OUTPUT, "PNG", optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
