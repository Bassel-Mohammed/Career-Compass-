#!/usr/bin/env python3
"""Generate the physical CareerCompass AI-service PostgreSQL ERD.

The diagram is intentionally generated from an explicit schema description
that mirrors migrations 001 through 006 plus the migration-history table.
It is a documentation asset, not a replacement for the SQL migrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "careercompass-ai-postgresql-erd-corrected.png"

CANVAS = (6400, 3100)
BACKGROUND = "#F8FAFC"
TEXT = "#172033"
MUTED = "#526078"
LINE = "#53627A"
ROW_LINE = "#D7DFEA"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_MONO = FONT_DIR / "DejaVuSansMono.ttf"
FONT_MONO_BOLD = FONT_DIR / "DejaVuSansMono-Bold.ttf"


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    flags: str = ""


@dataclass(frozen=True)
class Table:
    name: str
    group: str
    x: int
    y: int
    width: int
    columns: tuple[Column, ...]


GROUPS = {
    "market": ("#DCEEFF", "#1E5B8F", "Market and job data"),
    "taxonomy": ("#DDF6EE", "#176D5A", "Canonical taxonomy"),
    "course": ("#EEE5FF", "#6842A0", "Course and review data"),
    "publication": ("#FFF0D7", "#A76316", "Published course maps"),
    "system": ("#E8ECF2", "#526078", "Migration metadata"),
}


def c(name: str, data_type: str, flags: str = "") -> Column:
    return Column(name, data_type, flags)


TABLES = (
    Table("linkedin_jobs", "market", 100, 210, 1020, (
        c("id", "SERIAL", "PK"),
        c("career_path", "VARCHAR(150)", "NN"),
        c("search_query", "VARCHAR(200)", "NN"),
        c("title", "VARCHAR(300)", "NN"),
        c("company_name", "VARCHAR(200)"),
        c("location", "VARCHAR(200)"),
        c("url", "VARCHAR(500)", "NN UQ"),
        c("description", "TEXT"),
        c("seniority_level", "VARCHAR(100)"),
        c("employment_type", "VARCHAR(100)"),
        c("job_function", "VARCHAR(200)"),
        c("industries", "VARCHAR(300)"),
        c("posted_date", "VARCHAR(100)"),
        c("scraped_at", "TIMESTAMP", "NN"),
        c("is_relevant", "BOOLEAN", "NN"),
    )),
    Table("linkedin_job_skills", "market", 100, 1160, 1020, (
        c("id", "SERIAL", "PK"),
        c("linkedin_job_id", "INT", "FK NN"),
        c("skill_name", "VARCHAR(150)", "NN"),
        c("(linkedin_job_id, skill_name)", "", "UQ"),
    )),
    Table("job_skills", "market", 1260, 240, 1120, (
        c("id", "SERIAL", "PK"),
        c("job_id", "INTEGER", "FK NN"),
        c("term", "VARCHAR(300)", "NN"),
        c("sources", "VARCHAR(120)", "NN"),
        c("level", "VARCHAR(20)", "NN"),
        c("weight", "NUMERIC(4,2)", "NN"),
        c("skill_id", "VARCHAR(120)", "FK NULL"),
        c("match_method", "VARCHAR(40)"),
        c("match_score", "NUMERIC(5,3)"),
        c("review_status", "VARCHAR(20)", "NN"),
        c("taxonomy_version", "VARCHAR(20)"),
        c("created_at", "TIMESTAMP", "NN"),
        c("(job_id, term)", "", "UQ"),
    )),
    Table("career_path_skills", "market", 1260, 1250, 1120, (
        c("id", "SERIAL", "PK"),
        c("career_path", "VARCHAR(120)", "NN"),
        c("skill_id", "VARCHAR(120)", "FK NN"),
        c("posting_count", "INTEGER", "NN"),
        c("sample_size", "INTEGER", "NN"),
        c("coverage", "NUMERIC(6,4)", "NN"),
        c("required_score", "NUMERIC(5,1)", "NN"),
        c("required_level", "VARCHAR(20)", "NN"),
        c("derived_from", "VARCHAR(20)", "NN"),
        c("taxonomy_version", "VARCHAR(20)", "NN"),
        c("updated_at", "TIMESTAMP", "NN"),
        c("skill_type", "VARCHAR(20)", "NULL"),
        c("(career_path, skill_id)", "", "UQ"),
    )),
    Table("taxonomy_skill_aliases", "taxonomy", 2640, 180, 1130, (
        c("id", "SERIAL", "PK"),
        c("skill_id", "VARCHAR(120)", "FK NN"),
        c("alias", "VARCHAR(300)", "NN"),
        c("alias_normalized", "VARCHAR(300)", "NN"),
        c("language", "VARCHAR(10)", "NN"),
        c("(skill_id, alias_normalized)", "", "UQ"),
    )),
    Table("taxonomy_skills", "taxonomy", 2640, 790, 1130, (
        c("skill_id", "VARCHAR(120)", "PK"),
        c("label", "VARCHAR(300)", "NN"),
        c("source", "VARCHAR(20)", "NN"),
        c("skill_type", "VARCHAR(20)", "NN"),
        c("description", "TEXT"),
        c("uri", "VARCHAR(500)"),
        c("label_ar", "VARCHAR(300)"),
        c("taxonomy_version", "VARCHAR(20)", "NN"),
        c("updated_at", "TIMESTAMP", "NN"),
    )),
    Table("catalog_courses", "course", 2640, 2130, 1130, (
        c("course_id", "VARCHAR(200)", "PK"),
        c("platform", "VARCHAR(20)", "NN"),
        c("title", "VARCHAR(400)", "NN"),
        c("url", "TEXT", "NN"),
        c("level", "VARCHAR(20)"),
        c("language", "VARCHAR(20)"),
        c("duration_hours", "NUMERIC(6,1)"),
        c("rating", "NUMERIC(3,2)"),
        c("fetched_at", "TIMESTAMP", "NN"),
    )),
    Table("skill_match_reviews", "course", 4000, 160, 1110, (
        c("id", "SERIAL", "PK"),
        c("term_normalized", "VARCHAR(300)", "NN UQ"),
        c("skill_id", "VARCHAR(120)", "FK NULL"),
        c("decision", "VARCHAR(20)", "NN"),
        c("reviewer", "VARCHAR(100)"),
        c("note", "TEXT"),
        c("reviewed_at", "TIMESTAMP", "NN"),
    )),
    Table("course_skills", "course", 4000, 720, 1110, (
        c("id", "SERIAL", "PK"),
        c("course_code", "VARCHAR(30)", "NN"),
        c("term", "VARCHAR(300)", "NN"),
        c("level", "VARCHAR(20)", "NN"),
        c("weight", "NUMERIC(3,2)", "NN"),
        c("evidence_count", "INT", "NN"),
        c("sources", "VARCHAR(120)", "NN"),
        c("evidence", "JSONB"),
        c("skill_id", "VARCHAR(120)", "FK NULL"),
        c("match_method", "VARCHAR(30)"),
        c("match_score", "NUMERIC(4,3)"),
        c("review_status", "VARCHAR(20)", "NN"),
        c("match_reason", "TEXT"),
        c("candidates", "JSONB"),
        c("taxonomy_version", "VARCHAR(20)"),
        c("matched_at", "TIMESTAMP", "NN"),
        c("(course_code, term)", "", "UQ"),
    )),
    Table("catalog_course_skills", "course", 4000, 1900, 1110, (
        c("id", "SERIAL", "PK"),
        c("course_id", "VARCHAR(200)", "FK NN"),
        c("skill_id", "VARCHAR(120)", "FK NN"),
        c("in_title", "BOOLEAN", "NN"),
        c("(course_id, skill_id)", "", "UQ"),
    )),
    Table("course_map_publications", "publication", 5260, 260, 1050, (
        c("course_map_version", "VARCHAR(120)", "PK"),
        c("institution_code", "VARCHAR(120)", "NN"),
        c("catalog_version", "VARCHAR(80)", "NN"),
        c("course_code", "VARCHAR(64)", "NN"),
        c("qualified_course_key", "VARCHAR(266)", "NN"),
        c("source_outcome_id", "VARCHAR(120)", "NN"),
        c("taxonomy_version", "VARCHAR(20)", "NN"),
        c("payload_sha256", "CHAR(64)", "NN"),
        c("artifact_filename", "VARCHAR(255)", "NN"),
        c("skill_count", "INTEGER", "NN CHECK"),
        c("payload", "JSONB", "NN"),
        c("published_at", "TIMESTAMPTZ", "NN"),
        c("(institution, catalog, course, version)", "", "UQ"),
    )),
    Table("course_map_heads", "publication", 5260, 1320, 1050, (
        c("institution_code", "VARCHAR(120)", "PK"),
        c("catalog_version", "VARCHAR(80)", "PK"),
        c("course_code", "VARCHAR(64)", "PK"),
        c("course_map_version", "VARCHAR(120)", "FK NN"),
        c("updated_at", "TIMESTAMPTZ", "NN"),
    )),
    Table("careercompass_ai_schema_history", "system", 5260, 2210, 1050, (
        c("version", "INTEGER", "PK CHECK"),
        c("filename", "VARCHAR(255)", "NN UQ"),
        c("checksum", "CHAR(64)", "NN"),
        c("applied_at", "TIMESTAMPTZ", "NN"),
    )),
)


TABLE_BY_NAME = {table.name: table for table in TABLES}


ROW_H = 42
HEADER_H = 64


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


TITLE_FONT = load_font(FONT_BOLD, 56)
SUBTITLE_FONT = load_font(FONT_REGULAR, 27)
TABLE_FONT = load_font(FONT_MONO, 23)
TABLE_BOLD = load_font(FONT_MONO_BOLD, 24)
HEADER_FONT = load_font(FONT_BOLD, 29)
SMALL_FONT = load_font(FONT_REGULAR, 21)
SMALL_BOLD = load_font(FONT_BOLD, 22)


def table_height(table: Table) -> int:
    return HEADER_H + ROW_H * len(table.columns)


def table_box(table: Table) -> tuple[int, int, int, int]:
    return (table.x, table.y, table.x + table.width, table.y + table_height(table))


def anchor(table_name: str, side: str, fraction: float = 0.5) -> tuple[int, int]:
    table = TABLE_BY_NAME[table_name]
    x1, y1, x2, y2 = table_box(table)
    if side == "left":
        return (x1, int(y1 + (y2 - y1) * fraction))
    if side == "right":
        return (x2, int(y1 + (y2 - y1) * fraction))
    if side == "top":
        return (int(x1 + (x2 - x1) * fraction), y1)
    if side == "bottom":
        return (int(x1 + (x2 - x1) * fraction), y2)
    raise ValueError(side)


def draw_relation(
    draw: ImageDraw.ImageDraw,
    parent: str,
    child: str,
    parent_side: str,
    child_side: str,
    label: str,
    parent_fraction: float = 0.5,
    child_fraction: float = 0.5,
    via: tuple[tuple[int, int], ...] = (),
    child_cardinality: str = "0..*",
) -> None:
    start = anchor(parent, parent_side, parent_fraction)
    end = anchor(child, child_side, child_fraction)
    points = [start, *via, end]
    draw.line(points, fill=LINE, width=5, joint="curve")

    # Parent marker and child arrow make the FK direction unambiguous.
    draw.ellipse((start[0] - 9, start[1] - 9, start[0] + 9, start[1] + 9), fill="#FFFFFF", outline=LINE, width=4)
    if child_side in ("left", "right"):
        direction = 1 if child_side == "left" else -1
        tip = end
        wing1 = (end[0] - 20 * direction, end[1] - 14)
        wing2 = (end[0] - 20 * direction, end[1] + 14)
    else:
        direction = 1 if child_side == "top" else -1
        tip = end
        wing1 = (end[0] - 14, end[1] - 20 * direction)
        wing2 = (end[0] + 14, end[1] - 20 * direction)
    draw.polygon((tip, wing1, wing2), fill=LINE)

    draw.text((start[0] + 14, start[1] - 32), "1", font=SMALL_BOLD, fill=TEXT)
    draw.text((end[0] + 14, end[1] - 32), child_cardinality, font=SMALL_BOLD, fill=TEXT)

    middle = points[len(points) // 2]
    bbox = draw.textbbox((0, 0), label, font=SMALL_FONT)
    w = bbox[2] - bbox[0]
    draw.rounded_rectangle(
        (middle[0] - w // 2 - 12, middle[1] - 38, middle[0] + w // 2 + 12, middle[1] - 4),
        radius=10,
        fill="#FFFFFF",
        outline="#C5CFDD",
        width=2,
    )
    draw.text((middle[0] - w // 2, middle[1] - 35), label, font=SMALL_FONT, fill=MUTED)


def draw_table(draw: ImageDraw.ImageDraw, table: Table) -> None:
    fill, accent, _ = GROUPS[table.group]
    x1, y1, x2, y2 = table_box(table)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=18, fill="#FFFFFF", outline=accent, width=5)
    draw.rounded_rectangle((x1, y1, x2, y1 + HEADER_H), radius=18, fill=fill, outline=accent, width=5)
    draw.rectangle((x1, y1 + HEADER_H - 18, x2, y1 + HEADER_H), fill=fill)
    draw.line((x1, y1 + HEADER_H, x2, y1 + HEADER_H), fill=accent, width=4)
    draw.text((x1 + 22, y1 + 14), table.name.upper(), font=HEADER_FONT, fill=accent)

    flag_width = 172
    type_x = x2 - 445
    flag_x = x2 - flag_width
    for index, column in enumerate(table.columns):
        top = y1 + HEADER_H + index * ROW_H
        if index % 2:
            draw.rectangle((x1 + 3, top, x2 - 3, top + ROW_H), fill="#F9FBFD")
        draw.line((x1, top + ROW_H, x2, top + ROW_H), fill=ROW_LINE, width=2)
        name_font = TABLE_BOLD if "PK" in column.flags else TABLE_FONT
        draw.text((x1 + 18, top + 8), column.name, font=name_font, fill=TEXT)
        if column.data_type:
            draw.text((type_x, top + 8), column.data_type, font=TABLE_FONT, fill=MUTED)
        if column.flags:
            flag_color = "#9A3412" if "PK" in column.flags else "#1D4E89" if "FK" in column.flags else MUTED
            draw.text((flag_x, top + 8), column.flags, font=TABLE_BOLD, fill=flag_color)


def main() -> None:
    image = Image.new("RGB", CANVAS, BACKGROUND)
    draw = ImageDraw.Draw(image)

    draw.text((100, 40), "CareerCompass AI Service: PostgreSQL Physical ERD", font=TITLE_FONT, fill=TEXT)
    draw.text(
        (102, 112),
        "Generated from migrations 001-006 and the migration runner | PK = primary key, FK = foreign key, UQ = unique, NN = not null",
        font=SUBTITLE_FONT,
        fill=MUTED,
    )

    # Relationships are drawn first so table boxes remain readable.
    draw_relation(draw, "linkedin_jobs", "linkedin_job_skills", "bottom", "top", "ON DELETE CASCADE", 0.30, 0.30)
    draw_relation(draw, "linkedin_jobs", "job_skills", "right", "left", "job_id | CASCADE", 0.50, 0.20)
    draw_relation(draw, "taxonomy_skills", "taxonomy_skill_aliases", "top", "bottom", "skill_id | CASCADE", 0.30, 0.55)
    draw_relation(draw, "taxonomy_skills", "job_skills", "left", "right", "skill_id | SET NULL", 0.32, 0.56)
    draw_relation(draw, "taxonomy_skills", "career_path_skills", "left", "right", "skill_id | CASCADE", 0.76, 0.34)
    draw_relation(draw, "taxonomy_skills", "skill_match_reviews", "right", "left", "skill_id | SET NULL", 0.16, 0.56)
    draw_relation(draw, "taxonomy_skills", "course_skills", "right", "left", "skill_id | SET NULL", 0.55, 0.45)
    draw_relation(
        draw,
        "taxonomy_skills",
        "catalog_course_skills",
        "bottom",
        "left",
        "skill_id | CASCADE",
        0.70,
        0.38,
        via=((3650, 1835), (3900, 2030)),
    )
    draw_relation(draw, "catalog_courses", "catalog_course_skills", "right", "left", "course_id | CASCADE", 0.36, 0.72)
    draw_relation(
        draw,
        "course_map_publications",
        "course_map_heads",
        "bottom",
        "top",
        "course_map_version | RESTRICT",
        0.55,
        0.55,
        child_cardinality="0..*",
    )

    for table in TABLES:
        draw_table(draw, table)

    # Group legend and physical-schema caveat.
    legend_y = 2890
    x = 110
    for fill, accent, label in GROUPS.values():
        draw.rounded_rectangle((x, legend_y, x + 54, legend_y + 34), radius=8, fill=fill, outline=accent, width=3)
        draw.text((x + 68, legend_y + 3), label, font=SMALL_FONT, fill=TEXT)
        x += 620
    caveat = (
        "Physical FK note: course_map_heads.course_map_version is not UNIQUE, so PostgreSQL enforces one publication to zero or many head rows. "
        "If the intended relationship is zero-or-one active head, add a uniqueness or composite-identity constraint."
    )
    draw.text((110, 2980), caveat, font=SMALL_FONT, fill="#7C2D12")

    image.save(OUTPUT, format="PNG", optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
