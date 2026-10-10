"""Versioned worksheet layout data, independent of worksheet wording."""

import re


REGION_TYPES = ("body", "callout", "table", "list")
TEXT_STYLES = ("normal", "bold", "italic", "underline")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_page(page):
    """Validate a complete AI page before any packet result is committed."""
    blocks = page.get("blocks")
    if not isinstance(blocks, list) or not blocks or len(blocks) > 80:
        raise ValueError("변환 결과의 내용 구조가 비어 있거나 너무 깁니다.")
    normalized = []
    finished_groups = set()
    previous_group = None
    for position, block in enumerate(blocks):
        region = block.get("region")
        group = block.get("group")
        if region not in REGION_TYPES or not isinstance(group, int) or isinstance(group, bool) or group < 0:
            raise ValueError(f"{position + 1}번째 내용의 영역 정보가 올바르지 않습니다.")
        if group != previous_group:
            if group in finished_groups:
                raise ValueError("같은 원본 영역이 떨어져 있습니다. 읽는 순서를 확인해야 합니다.")
            finished_groups.add(group)
        elif normalized[-1]["region"] != region:
            raise ValueError("같은 영역 안의 구조 종류가 서로 다릅니다.")
        previous_group = group
        text = str(block.get("text", ""))
        explanation = str(block.get("explanation", ""))
        cells = block.get("cells", [])
        if not isinstance(cells, list) or len(cells) > 6 or any(not isinstance(cell, str) or len(cell) > 5000 for cell in cells):
            raise ValueError("표의 칸 구조가 올바르지 않습니다.")
        if region != "table" and cells:
            raise ValueError("표가 아닌 영역에 표 칸이 들어 있습니다.")
        if region == "table" and not text.strip():
            text = "\t".join(cells)
        if not text.strip() and not any(cell.strip() for cell in cells):
            raise ValueError("비어 있는 내용이 있습니다. 원본에서 누락됐는지 확인해야 합니다.")
        if len(text) > 5000 or len(explanation) > 3000:
            raise ValueError("내용이 편집 가능한 길이를 넘어섰습니다.")
        background = str(block.get("background", ""))
        if background and not COLOR.fullmatch(background):
            raise ValueError("원본 배경색 형식이 올바르지 않습니다.")
        style = block.get("text_style")
        if style not in TEXT_STYLES:
            raise ValueError("원본 글자 스타일이 올바르지 않습니다.")
        kind = block.get("kind")
        if kind not in ("heading", "text", "example", "exercise", "handwriting"):
            raise ValueError("내용 종류가 올바르지 않습니다.")
        normalized.append({"kind": kind, "text": text, "explanation": explanation,
                           "uncertain": bool(block.get("uncertain")), "region": region,
                           "group": group, "background": background, "border": bool(block.get("border")),
                           "text_style": style, "cells": cells})
    for group in finished_groups:
        rows = [block for block in normalized if block["group"] == group]
        # Printed tables can contain spanning cells or handwritten marks between rows.
        # Keep their source order without inventing empty cells to satisfy a fixed grid.
    return {"version": 2, "title": str(page.get("title", ""))[:160], "blocks": normalized}


def layout_regions(page):
    """Group consecutive source regions while keeping stable block indexes for notes."""
    regions = []
    for index, block in enumerate(page["blocks"]):
        if not regions or regions[-1]["group"] != block["group"]:
            regions.append({"group": block["group"], "type": block["region"], "background": block["background"],
                            "border": block["border"], "blocks": []})
        regions[-1]["blocks"].append({**block, "index": index})
    return regions
