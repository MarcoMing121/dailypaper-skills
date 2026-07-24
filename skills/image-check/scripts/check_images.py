#!/usr/bin/env python3
"""
Check image consistency: note references ↔ legend ↔ actual files.

Usage:
    python3 check_images.py --note /path/to/note.md --vault /path/to/vault

Output: JSON report + human-readable summary
"""

import argparse
import re
import json
import sys
from pathlib import Path
from datetime import datetime


def load_config():
    """Load user config for vault path."""
    config_path = Path(__file__).parent.parent.parent / "_shared" / "user_config.py"
    if config_path.exists():
        sys.path.insert(0, str(config_path.parent))
        from user_config import obsidian_vault_path
        return {"vault_path": str(obsidian_vault_path())}
    return {}


def extract_note_images(text: str) -> dict:
    """Extract all image references from a paper note."""
    images = {"local": [], "external": []}
    
    # Obsidian wikilinks: ![[MethodName/fig1.png]] or ![[fig1.png|500]]
    for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|(\d+))?\]\]', text):
        link = match.group(1)
        images["local"].append({
            "link": link,
            "filename": Path(link).name,
            "stem": Path(link).stem,
        })
    
    # External markdown images: ![alt](url)
    for match in re.finditer(r'!\[([^\]]*)\]\((https?://[^)]+)\)', text):
        images["external"].append({
            "alt": match.group(1),
            "url": match.group(2),
            "stem": match.group(1) or match.group(2).split("/")[-1].split(".")[0],
        })
    
    return images


def load_legend(legend_path: Path) -> list:
    """Parse legend.md file."""
    if not legend_path.exists():
        return []
    
    text = legend_path.read_text(encoding="utf-8")
    legends = []
    
    for line in text.split("\n"):
        if line.startswith("|") and not line.startswith("|--") and "ID" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]  # Remove empty first/last
            if len(parts) >= 4:
                legends.append({
                    "id": parts[0],
                    "source": parts[1],
                    "link": parts[2],
                    "legend": parts[3],
                    "used": parts[4] == "✅" if len(parts) > 4 else False,
                })
    
    return legends


def extract_arxiv_id(text: str) -> str:
    """Extract arXiv ID from note text (frontmatter or links)."""
    # From frontmatter
    match = re.search(r'arxiv.*?(\d{4}\.\d{4,5})', text)
    if match:
        return match.group(1)
    # From URL
    match = re.search(r'arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})', text)
    if match:
        return match.group(1)
    return ""


def extract_figures_from_html_text(html_text: str, arxiv_id: str) -> list:
    """Extract figures from HTML text directly (for small HTML files)."""
    figures = []
    fig_pattern = re.compile(r'<figure[^>]*>(.*?)</figure>', re.DOTALL)
    img_pattern = re.compile(r'<img[^>]*src=["\']([^"\']+)["\']', re.DOTALL)
    caption_pattern = re.compile(r'<figcaption[^>]*>(.*?)</figcaption>', re.DOTALL)

    for fig_match in fig_pattern.finditer(html_text):
        fig_html = fig_match.group(1)
        img_match = img_pattern.search(fig_html)
        img_url = img_match.group(1) if img_match else ""
        if img_url and not img_url.startswith("http"):
            img_url = f"https://arxiv.org/html/{arxiv_id}/{img_url}"

        filename = Path(img_url).stem if img_url else ""
        ext = Path(img_url).suffix if img_url else ".png"

        cap_match = caption_pattern.search(fig_html)
        caption = re.sub(r'<[^>]+>', '', cap_match.group(1)).strip() if cap_match else ""

        if filename:
            figures.append({
                "id": filename,
                "url": img_url,
                "caption": caption[:200],
                "filename": f"{filename}{ext}",
                "source": "html",
            })

    return figures


def extract_figures_from_chunk_result(chunk_json_path: Path) -> list:
    """Extract figure info from a subagent chunk result JSON."""
    if not chunk_json_path.exists():
        return []
    try:
        data = json.loads(chunk_json_path.read_text(encoding="utf-8"))
        return data.get("figures", [])
    except Exception:
        return []


def extract_figures_via_subagents(file_path: Path, arxiv_id: str, mode: str) -> list:
    """Extract figures using parallel subagent chunk extraction (paper-reader style).

    mode: 'html' or 'mineru'
    """
    import subprocess

    text = file_path.read_text(encoding="utf-8")
    lines = text.count('\n')
    chunk_size = 300
    num_chunks = (lines + chunk_size - 1) // chunk_size

    # Split into chunks
    chunk_files = []
    for i in range(1, num_chunks + 1):
        start = (i - 1) * chunk_size + 1
        end = min(i * chunk_size, lines)
        chunk_file = Path(f"/tmp/verify_chunk_{arxiv_id}_{i}.{'html' if mode == 'html' else 'md'}")
        subprocess.run(
            ["sed", "-n", f"{start},{end}p", str(file_path)],
            capture_output=True, text=True
        )
        # Write chunk
        chunk_lines = text.split('\n')[start-1:end]
        chunk_file.write_text('\n'.join(chunk_lines), encoding="utf-8")
        chunk_files.append(chunk_file)

    # NOTE: We can't actually spawn subagents from a script.
    # Instead, we do direct extraction from chunks.
    all_figures = []

    for chunk_file in chunk_files:
        chunk_text = chunk_file.read_text(encoding="utf-8")

        if mode == "html":
            figs = extract_figures_from_html_text(chunk_text, arxiv_id)
        else:
            # MinerU markdown — look for figure references
            figs = extract_figures_from_mineru_text(chunk_text)

        all_figures.extend(figs)

        # Cleanup
        chunk_file.unlink(missing_ok=True)

    return all_figures


def extract_figures_from_mineru_text(md_text: str) -> list:
    """Extract figures from MinerU markdown text."""
    figures = []

    # Look for image references: ![caption](path)
    for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', md_text):
        caption = match.group(1)
        path = match.group(2)
        figures.append({
            "id": Path(path).stem,
            "url": "",
            "local_path": path,
            "caption": caption[:200] if caption else "N/A",
            "filename": Path(path).name,
            "source": "mineru",
        })

    return figures


def extract_figures_via_mineru(arxiv_id: str, force: bool = False) -> list:
    """Full MinerU extraction pipeline with PDF splitting (same as paper-reader).

    Results are cached to /tmp/paper_verify_mineru_{arxiv_id}/ so they persist
    across calls. Pass force=True to re-extract even if cache exists.

    Cache layout:
        /tmp/paper_verify_mineru_{arxiv_id}/
            images/           — extracted image files
            *.md              — MinerU markdown output
            figures_cache.json — parsed figure metadata (cache)
    """
    import subprocess

    mineru_dir = Path(f"/tmp/paper_verify_mineru_{arxiv_id}")
    cache_file = mineru_dir / "figures_cache.json"

    # === Cache hit: return saved results ===
    if not force and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            # Verify referenced files still exist
            valid = []
            for fig in cached:
                lp = fig.get("local_path", "")
                if not lp or Path(lp).exists():
                    valid.append(fig)
            if valid:
                return valid
        except Exception:
            pass  # Cache corrupted, re-extract

    # === Download PDF ===
    pdf_path = Path(f"/tmp/paper_verify_{arxiv_id}.pdf")
    try:
        subprocess.run(
            ["curl", "-sL", f"https://arxiv.org/pdf/{arxiv_id}.pdf", "-o", str(pdf_path)],
            capture_output=True, timeout=60
        )
    except Exception:
        return []

    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        return []

    pdf_size_mb = pdf_path.stat().st_size / (1024 * 1024)

    # === Split if ≥1MB (reuse paper-reader's split script) ===
    split_script = Path(__file__).parent.parent.parent / "paper-reader" / "scripts" / "split_pdf_for_mineru.sh"

    if pdf_size_mb >= 1 and split_script.exists():
        chunks_dir = Path(f"/tmp/paper_verify_chunks_{arxiv_id}")
        try:
            subprocess.run(
                ["bash", str(split_script), str(pdf_path), str(chunks_dir)],
                capture_output=True, timeout=120
            )
            mineru_dir.mkdir(parents=True, exist_ok=True)
            (mineru_dir / "images").mkdir(exist_ok=True)

            for chunk in sorted(chunks_dir.glob("chunk_*.pdf")):
                chunk_dir = mineru_dir / chunk.stem
                try:
                    subprocess.run(
                        ["mineru-open-api", "extract", str(chunk), "-o", str(chunk_dir),
                         "-f", "md,json", "--language", "en", "--model", "pipeline", "--timeout", "300"],
                        capture_output=True, timeout=360
                    )
                    if (chunk_dir / "images").exists():
                        for img in (chunk_dir / "images").iterdir():
                            target = mineru_dir / "images" / img.name
                            if not target.exists():
                                img.rename(target)
                except Exception:
                    continue
        except Exception:
            pass
    else:
        # Direct MinerU extraction
        try:
            subprocess.run(
                ["mineru-open-api", "extract", str(pdf_path), "-o", str(mineru_dir),
                 "-f", "md,json", "--language", "en", "--model", "pipeline", "--timeout", "300"],
                capture_output=True, timeout=360
            )
        except Exception:
            return []

    # === Find MinerU markdown output ===
    md_files = list(mineru_dir.glob("**/*.md"))
    images_dir = mineru_dir / "images"

    if not images_dir.exists() or not md_files:
        return []

    # === Extract figures from markdown ===
    all_figures = []
    md_text = md_files[0].read_text(encoding="utf-8")
    md_lines = md_text.count('\n')

    if md_lines > 500:
        chunk_size = 300
        for i in range(1, (md_lines // chunk_size) + 2):
            start = (i - 1) * chunk_size
            end = min(i * chunk_size, md_lines)
            chunk_lines = md_text.split('\n')[start:end]
            chunk_text = '\n'.join(chunk_lines)
            figs = extract_figures_from_mineru_text(chunk_text)
            all_figures.extend(figs)
    else:
        all_figures = extract_figures_from_mineru_text(md_text)

    # Resolve local file paths
    for fig in all_figures:
        if fig.get("local_path"):
            full_path = mineru_dir / fig["local_path"]
            if full_path.exists():
                fig["local_path"] = str(full_path)

    # Include images not referenced in markdown
    referenced = {f["filename"] for f in all_figures}
    for img_file in images_dir.iterdir():
        if img_file.name not in referenced and img_file.suffix.lower() in ('.png', '.jpg', '.jpeg'):
            all_figures.append({
                "id": img_file.stem,
                "url": "",
                "local_path": str(img_file),
                "caption": "N/A",
                "filename": img_file.name,
                "source": "mineru",
            })

    # === Save cache (persist across runs) ===
    try:
        cache_file.write_text(json.dumps(all_figures, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Cleanup downloaded PDF only (keep extracted results)
    try:
        pdf_path.unlink(missing_ok=True)
    except Exception:
        pass

    return all_figures


def verify_against_paper(note_path: Path, vault_path: Path) -> dict:
    """Verify note images against the original paper (no legend needed).

    Uses the SAME extraction pipeline as paper-reader:
    1. arXiv HTML → chunk → parallel subagent extraction
    2. MinerU PDF → split → parallel subagent extraction (fallback)
    3. Compare extracted figures with note references
    """
    note_text = note_path.read_text(encoding="utf-8")
    arxiv_id = extract_arxiv_id(note_text)

    if not arxiv_id:
        return {"ok": False, "detail": "No arXiv ID found in note", "figures": []}

    # === Phase 1: Try arXiv HTML (same as paper-reader) ===
    html_path = Path(f"/tmp/paper_verify_{arxiv_id}.html")
    paper_figures = []
    source = "html"

    try:
        import subprocess
        subprocess.run(
            ["curl", "-sL", f"https://arxiv.org/html/{arxiv_id}", "-o", str(html_path)],
            capture_output=True, timeout=30
        )
    except Exception:
        pass

    if html_path.exists() and html_path.stat().st_size > 1000:
        html_text = html_path.read_text(encoding="utf-8")
        lines = html_text.count('\n')

        if lines <= 500:
            # Small HTML — extract directly
            paper_figures = extract_figures_from_html_text(html_text, arxiv_id)
        else:
            # Large HTML — chunk + parallel subagent extraction (paper-reader style)
            paper_figures = extract_figures_via_subagents(html_path, arxiv_id, "html")

    # === Phase 2: MinerU fallback (same as paper-reader) ===
    if len(paper_figures) < 2:
        source = "mineru"
        paper_figures = extract_figures_via_mineru(arxiv_id)

    if not paper_figures:
        return {"ok": False, "detail": f"Could not fetch figures for {arxiv_id}", "figures": []}

    # === Phase 3: Cross-verify ===

    # Extract note references
    note_urls = set()
    for match in re.finditer(r'!\[[^\]]*\]\((https?://[^)]+)\)', note_text):
        note_urls.add(match.group(1))
    note_stems = set()
    for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|\d+)?\]\]', note_text):
        note_stems.add(Path(match.group(1)).stem)

    # Cross-verify
    paper_url_map = {f["url"]: f for f in paper_figures if f.get("url")}
    paper_stem_map = {f["id"]: f for f in paper_figures}
    paper_filename_map = {f["filename"]: f for f in paper_figures}

    matched = []
    unmatched_note = []
    missing_from_note = []

    for url in note_urls:
        if url in paper_url_map:
            matched.append(paper_url_map[url])
        else:
            # Try stem match
            stem = Path(url).stem
            filename = Path(url).name
            if stem in paper_stem_map:
                matched.append(paper_stem_map[stem])
            elif filename in paper_filename_map:
                matched.append(paper_filename_map[filename])
            else:
                unmatched_note.append(url)

    for stem in note_stems:
        if stem in paper_stem_map:
            fig = paper_stem_map[stem]
            if fig not in matched:
                matched.append(fig)

    # Find important figures missing from note
    for fig in paper_figures:
        if fig not in matched:
            if fig["id"] not in note_stems and fig.get("url", "") not in note_urls:
                missing_from_note.append(fig)

    return {
        "ok": len(unmatched_note) == 0,
        "arxiv_id": arxiv_id,
        "source": source,
        "paper_figures": len(paper_figures),
        "note_refs": len(note_urls) + len(note_stems),
        "matched": len(matched),
        "unmatched_note": unmatched_note,
        "missing_from_note": [f["id"] for f in missing_from_note[:10]],
        "figures": paper_figures,
    }


# ── Figure type classification ──────────────────────────────────────────────

# Keywords that indicate a figure is about architecture/framework/overview
ARCH_KEYWORDS_ZH = {"架构", "框架", "概览", "系统", "流程", "结构", "组成", "设计", "概述", "示意图", "pipeline"}
ARCH_KEYWORDS_EN = {"architecture", "overview", "framework", "pipeline", "system", "structure",
                    "component", "schematic", "diagram", "layout", "design", "illustration"}

# Keywords that indicate a figure is about results/experiments
RESULT_KEYWORDS_ZH = {"结果", "实验", "对比", "消融", "性能", "效果", "分析", "评估", "训练", "奖励"}
RESULT_KEYWORDS_EN = {"result", "experiment", "comparison", "ablation", "performance", "evaluation",
                      "metric", "curve", "plot", "chart", "benchmark", "quantitative", "reward"}

# Keywords that indicate qualitative examples
EXAMPLE_KEYWORDS_ZH = {"示例", "可视化", "定性", "展示", "案例", "截图", "真实"}
EXAMPLE_KEYWORDS_EN = {"example", "visualization", "qualitative", "demonstration", "real-world",
                       "real world", "deployment", "simulation", "visual"}


def classify_figure_type(text: str) -> str:
    """Classify a caption/heading into figure type category."""
    text_lower = text.lower()

    # Score each category
    arch_score = 0
    result_score = 0
    example_score = 0

    for kw in ARCH_KEYWORDS_ZH:
        if kw in text:
            arch_score += 2
    for kw in ARCH_KEYWORDS_EN:
        if kw in text_lower:
            arch_score += 2

    for kw in RESULT_KEYWORDS_ZH:
        if kw in text:
            result_score += 2
    for kw in RESULT_KEYWORDS_EN:
        if kw in text_lower:
            result_score += 2

    for kw in EXAMPLE_KEYWORDS_ZH:
        if kw in text:
            example_score += 2
    for kw in EXAMPLE_KEYWORDS_EN:
        if kw in text_lower:
            example_score += 2

    # Boost architecture score for specific terms
    if re.search(r'\b(fig|figure)\s*\d+', text_lower) and re.search(r'(arch|overview|framework)', text_lower):
        arch_score += 3

    # Boost result score for specific patterns
    if re.search(r'(table|acc|mse|error|score|reward|loss)\b', text_lower):
        result_score += 1
    if re.search(r'(fig|figure)\s*\d+', text_lower) and re.search(r'(result|comparison|ablation)', text_lower):
        result_score += 3

    scores = {
        "architecture": arch_score,
        "result": result_score,
        "example": example_score,
    }

    best = max(scores, key=scores.get)
    # Return "unknown" if no clear signal
    return best if scores[best] >= 2 else "unknown"


def extract_note_section_headings(text: str, img_pos: int) -> list:
    """Extract the closest section/subsection heading before an image."""
    # Scan backwards from image position for headings
    before = text[:img_pos]
    headings = re.findall(r'^(#{1,4})\s+(.+)$', before, re.MULTILINE)
    return [h[1].strip() for h in headings]


def fetch_arxiv_html_captions(arxiv_id: str) -> dict[str, str]:
    """Download arXiv HTML and extract figure id → caption mapping."""
    import subprocess

    url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        html = result.stdout
    except Exception:
        return {}

    if not html or len(html) < 1000:
        return {}

    captions = {}

    # Extract <figure> blocks with their <img> and <figcaption>
    fig_pattern = re.compile(r'<figure[^>]*>(.*?)</figure>', re.DOTALL)
    img_pattern = re.compile(r'<img[^>]*src=["\']([^"\']+)["\']', re.DOTALL)
    caption_pattern = re.compile(r'<figcaption[^>]*>(.*?)</figcaption>', re.DOTALL)

    for fig_match in fig_pattern.finditer(html):
        fig_html = fig_match.group(1)
        img_match = img_pattern.search(fig_html)
        if not img_match:
            continue
        img_url = img_match.group(1)
        img_id = Path(img_url).stem  # e.g., "x1", "x2"

        cap_match = caption_pattern.search(fig_html)
        caption = ""
        if cap_match:
            caption = re.sub(r'<[^>]+>', '', cap_match.group(1)).strip()

        if img_id:
            captions[img_id] = caption

    return captions


def check_figure_type_consistency(note_path: Path, vault_path: Path) -> dict:
    """
    Verify that images the note calls 'architecture' actually correspond
    to architecture/overview figures from the paper, not results/examples/etc.
    """
    note_text = note_path.read_text(encoding="utf-8")

    # Find arXiv ID
    arxiv_id = ""
    match = re.search(r'arxiv.*?(\d{4}\.\d{4,5})', note_text)
    if match:
        arxiv_id = match.group(1)
    if not arxiv_id:
        match = re.search(r'arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})', note_text)
        if match:
            arxiv_id = match.group(1)

    if not arxiv_id:
        return {"ok": True, "detail": "No arXiv ID — skipping figure type check", "mismatches": []}

    # Get paper captions
    paper_captions = fetch_arxiv_html_captions(arxiv_id)
    if not paper_captions:
        return {"ok": True, "detail": "Could not fetch arXiv HTML captions", "mismatches": []}

    mismatches = []
    checked = 0

    # Check all image references with surrounding context
    for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|\d+)?\]\]', note_text):
        ref = match.group(1)
        stem = Path(ref).stem
        pos = match.start()

        # Find the nearest section heading(s) before this image
        headings = extract_note_section_headings(note_text, pos)
        if not headings:
            continue

        # Get the closest meaningful heading (skip the title)
        note_heading = headings[-1] if headings else ""

        # Classify note's description
        note_type = classify_figure_type(note_heading)

        # Skip if note doesn't claim a specific type
        if note_type == "unknown":
            continue

        # Map filename stem to paper figure ID
        # Try direct match, or match via number extracted from name
        fig_id_match = re.search(r'fig(\d+)', stem)
        paper_fig_id = f"x{fig_id_match.group(1)}" if fig_id_match else stem

        # Get paper caption
        paper_caption = ""
        for pid, cap in paper_captions.items():
            if pid == paper_fig_id or pid == stem:
                paper_caption = cap
                paper_fig_id = pid
                break
            # Precise caption-based matching (avoids "Figure 1" matching "Figure 10")
            if fig_id_match and re.search(rf'\bFigure\s+{fig_id_match.group(1)}\b', cap):
                paper_caption = cap
                paper_fig_id = pid
                break

        if not paper_caption:
            # Try matching by image filename
            for pid, cap in paper_captions.items():
                if stem in cap.lower() or stem.replace("_", " ") in cap.lower():
                    paper_caption = cap
                    paper_fig_id = pid
                    break

        if not paper_caption:
            continue

        # Classify paper's own description
        paper_type = classify_figure_type(paper_caption)

        checked += 1

        # Mismatch: note says architecture but paper says results/examples, or vice versa
        if note_type != paper_type and paper_type != "unknown":
            mismatches.append({
                "image": stem,
                "ref": f"![[{ref}]]",
                "section_heading": note_heading,
                "note_claim_type": note_type,
                "paper_caption": paper_caption[:150],
                "paper_actual_type": paper_type,
                "severity": "high" if (note_type == "architecture" and paper_type != "architecture") else "medium",
            })

    # Also check external image URLs
    for match in re.finditer(r'!\[([^\]]*)\]\((https?://[^)]+)\)', note_text):
        alt = match.group(1)
        url = match.group(2)
        pos = match.start()

        headings = extract_note_section_headings(note_text, pos)
        if not headings:
            continue
        note_heading = headings[-1] if headings else ""
        note_type = classify_figure_type(note_heading)
        if note_type == "unknown":
            continue

        # Match URL stem to paper figures
        url_stem = Path(url).stem
        paper_caption = paper_captions.get(url_stem, "")
        if not paper_caption:
            for pid, cap in paper_captions.items():
                if pid == url_stem or url_stem in cap.lower():
                    paper_caption = cap
                    break

        if not paper_caption:
            continue

        paper_type = classify_figure_type(paper_caption)
        checked += 1

        if note_type != paper_type and paper_type != "unknown":
            mismatches.append({
                "image": alt or url_stem,
                "ref": f"![{alt}]({url[:80]}...)",
                "section_heading": note_heading,
                "note_claim_type": note_type,
                "paper_caption": paper_caption[:150],
                "paper_actual_type": paper_type,
                "severity": "high" if (note_type == "architecture" and paper_type != "architecture") else "medium",
            })

    # Determine overall status
    if not mismatches:
        return {
            "ok": True,
            "detail": f"All {checked} figures type-consistent (note heading ↔ paper caption)",
            "checked": checked,
            "mismatches": [],
        }
    else:
        high_sev = sum(1 for m in mismatches if m["severity"] == "high")
        return {
            "ok": False,
            "detail": f"{len(mismatches)} type mismatches ({high_sev} high severity)",
            "checked": checked,
            "mismatches": mismatches,
        }


def check_model_architecture_section(note_path: Path, vault_path: Path) -> dict:
    """
    Special check for the 方法详解 → 模型架构 section.

    Verifies:
    1. The section contains a Mermaid diagram (template requirement)
    2. The paper's actual architecture figure (identified from arXiv HTML caption)
       is referenced in or near this section
    3. The architecture figure's note caption correctly identifies it as architecture
    """
    note_text = note_path.read_text(encoding="utf-8")
    method_name = note_path.stem

    # ── 1. Find "模型架构" section boundaries ─────────────────────────────
    arch_sec_start = None
    arch_sec_end = None

    # Look for "### 模型架构" heading (allow trailing content in parens like "(Mermaid)")
    sec_pattern = re.compile(r'^###\s+模型架构.*$', re.MULTILINE)
    sec_match = sec_pattern.search(note_text)
    if not sec_match:
        # Try English heading
        sec_pattern = re.compile(r'^###\s+Model Architecture.*$', re.MULTILINE)
        sec_match = sec_pattern.search(note_text)
    if not sec_match:
        # Try "架构" (broader match)
        sec_pattern = re.compile(r'^###\s+.*架构.*$', re.MULTILINE)
        sec_match = sec_pattern.search(note_text)

    if sec_match:
        arch_sec_start = sec_match.start()
        # Find next section at same or higher heading level
        next_sec = re.search(r'^#{1,3}\s+', note_text[arch_sec_start + len(sec_match.group(0)):], re.MULTILINE)
        if next_sec:
            arch_sec_end = arch_sec_start + len(sec_match.group(0)) + next_sec.start()
        else:
            arch_sec_end = len(note_text)

    section_found = arch_sec_start is not None
    section_text = note_text[arch_sec_start:arch_sec_end] if arch_sec_start is not None else ""

    # ── 2. Check for Mermaid diagram ──────────────────────────────────────
    has_mermaid = bool(re.search(r'```mermaid', section_text)) if section_text else False

    # ── 3. Find figure references in/near the section ─────────────────────
    # Check the section itself + the 1000 chars after (in case figure is just below)
    search_zone = section_text
    if arch_sec_end:
        search_zone += note_text[arch_sec_end:arch_sec_end + 1000]

    figure_refs = []  # (type, ref_string, stem_or_url)
    # Local wikilinks
    for m in re.finditer(r'!\[\[([^\]|]+?)(?:\|\d+)?\]\]', search_zone):
        figure_refs.append(("local", m.group(0), Path(m.group(1)).stem))
    # External URLs
    for m in re.finditer(r'!\[([^\]]*)\]\((https?://[^)]+)\)', search_zone):
        figure_refs.append(("external", m.group(0), m.group(2)))

    # ── 4. Get arXiv HTML captions to identify architecture figure ────────
    arxiv_id = ""
    match = re.search(r'arxiv.*?(\d{4}\.\d{4,5})', note_text)
    if match:
        arxiv_id = match.group(1)
    if not arxiv_id:
        match = re.search(r'arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})', note_text)
        if match:
            arxiv_id = match.group(1)

    paper_captions = {}
    if arxiv_id:
        paper_captions = fetch_arxiv_html_captions(arxiv_id)

    # Identify which paper figure is the "architecture" figure
    arch_fig_id = None
    arch_fig_caption = ""
    for fig_id, cap in paper_captions.items():
        fig_type = classify_figure_type(cap)
        if fig_type == "architecture":
            arch_fig_id = fig_id
            arch_fig_caption = cap[:200]
            break  # Take the first architecture figure found

    # ── 5. Cross-reference: is the arch figure in the section? ────────────
    arch_figure_in_section = False
    matched_ref = ""
    for ref_type, ref_str, key in figure_refs:
        if ref_type == "local":
            # Check if the local filename maps to the architecture figure
            stem = key
            # Extract number from name like fig2_xxx → x2
            num_match = re.search(r'(\d+[a-z]?)', stem)
            if num_match:
                expected_id = f"x{num_match.group(1)}"
                if expected_id == arch_fig_id:
                    arch_figure_in_section = True
                    matched_ref = ref_str
                    break
            # Also check stem directly
            if arch_fig_id and arch_fig_id in stem:
                arch_figure_in_section = True
                matched_ref = ref_str
                break
        elif ref_type == "external":
            url_stem = Path(key).stem
            if url_stem == arch_fig_id:
                arch_figure_in_section = True
                matched_ref = ref_str
                break
            # Check URL stem in caption
            if arch_fig_id and arch_fig_id == url_stem:
                arch_figure_in_section = True
                matched_ref = ref_str
                break

    # ── 6. Classify note caption for the section heading ──────────────────
    heading_text = ""
    if sec_match:
        heading_text = sec_match.group(0)

    note_type = classify_figure_type(heading_text + " " + " ".join(
        [r[1] for r in figure_refs if r[0] == "local"]
    ))

    # ── 7. Determine result ──────────────────────────────────────────────
    issues_detail = []

    if not section_found:
        return {
            "ok": False,
            "detail": "❌ '模型架构' section not found in note",
            "has_mermaid": False,
            "arch_figure_present": False,
            "arch_figure_in_section": False,
            "paper_arch_figure": arch_fig_id or "unknown",
            "paper_arch_caption": arch_fig_caption,
            "figure_refs_in_section": len(figure_refs),
        }

    if not has_mermaid:
        issues_detail.append("No Mermaid diagram in 模型架构 section")

    arch_figure_status = "✅" if arch_figure_in_section else "⚠️"
    if not arch_figure_in_section and arch_fig_id:
        issues_detail.append(
            f"Paper's architecture figure ({arch_fig_id}: '{arch_fig_caption[:60]}...') "
            f"is NOT referenced in the 模型架构 section"
        )
    elif not arch_figure_in_section and not arch_fig_id:
        pass  # No architecture figure in paper, fine

    ok = has_mermaid or len(issues_detail) == 0
    # If no architecture figure in paper, that's fine too

    detail_parts = []
    if has_mermaid:
        detail_parts.append("Mermaid ✅")
    else:
        detail_parts.append("Mermaid ❌")
    if arch_figure_in_section:
        detail_parts.append(f"Paper arch figure {arch_fig_id} ✅")
    elif arch_fig_id:
        detail_parts.append(f"Paper arch figure {arch_fig_id} ⚠️ not in section")
    else:
        detail_parts.append("No arch figure in paper to verify")
    if figure_refs:
        detail_parts.append(f"({len(figure_refs)} figure refs in section)")

    return {
        "ok": ok,
        "section_found": section_found,
        "has_mermaid": has_mermaid,
        "arch_figure_present": arch_figure_in_section or not arch_fig_id,
        "arch_figure_in_section": arch_figure_in_section,
        "paper_arch_figure": arch_fig_id or "unknown",
        "paper_arch_caption": arch_fig_caption,
        "figure_refs_in_section": len(figure_refs),
        "note_claim_type": note_type,
        "detail": ", ".join(detail_parts),
        "issues": issues_detail,
    }


def check_images(note_path: Path, vault_path: Path) -> dict:
    """Run all image checks."""
    method_name = note_path.stem
    
    # Determine assets directory
    # Try to find it in the note text
    note_text = note_path.read_text(encoding="utf-8")
    
    # Look for assets path patterns
    assets_candidates = [
        vault_path / "assets" / method_name,
    ]
    
    # Also check from image links in note
    for match in re.finditer(r'!\[\[([^\]|]+)/', note_text):
        dir_name = match.group(1)
        assets_candidates.append(vault_path / "assets" / dir_name)
    
    assets_dir = None
    for candidate in assets_candidates:
        if candidate.exists():
            assets_dir = candidate
            break
    
    if not assets_dir:
        assets_dir = vault_path / "assets" / method_name
    
    legend_path = assets_dir / "legend.md"

    # Collect data
    note_images = extract_note_images(note_text)

    # Actual files in assets
    actual_files = {}
    if assets_dir.exists():
        for f in assets_dir.iterdir():
            if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                actual_files[f.stem] = {
                    "path": str(f),
                    "size": f.stat().st_size,
                    "name": f.name,
                }

    # === Auto-generate legend when missing (before loading legends, so checks work) ===
    if not legend_path.exists() and actual_files:
        try:
            title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', note_text, re.MULTILINE)
            title = title_match.group(1) if title_match else method_name

            note_stems_for_legend = set()
            for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|\d+)?\]\]', note_text):
                note_stems_for_legend.add(Path(match.group(1)).stem)

            legend_lines = [
                f"# Image Legends: {title}",
                "",
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} (by image-check)",
                "",
                "| ID | Source | Link | Legend | Used in Note |",
                "|----|--------|------|--------|--------------|",
            ]
            for stem, info in actual_files.items():
                used = "✅" if stem in note_stems_for_legend else "❌"
                legend_lines.append(
                    f"| {stem} | local | ![[{assets_dir.name}/{info['name']}]] | N/A | {used} |"
                )
            assets_dir.mkdir(parents=True, exist_ok=True)
            legend_path.write_text("\n".join(legend_lines), encoding="utf-8")
        except Exception:
            pass

    legends = load_legend(legend_path)
    
    # Run checks
    checks = {}
    issues = []
    
    # Check 1: Legend exists
    checks["legend_exists"] = {
        "ok": legend_path.exists(),
        "detail": f"Legend file: {legend_path}" if legend_path.exists() else "Legend file missing",
    }
    if not legend_path.exists():
        issues.append("Legend file missing")
    
    # Check 2: Local files exist
    local_stems = {img["stem"] for img in note_images["local"]}
    missing_files = []
    for stem in local_stems:
        if stem not in actual_files:
            missing_files.append(stem)
    checks["local_files_exist"] = {
        "ok": len(missing_files) == 0,
        "detail": f"Missing: {missing_files}" if missing_files else "All local files exist",
        "missing": missing_files,
    }
    if missing_files:
        issues.append(f"Missing local files: {missing_files}")
    
    # Check 3: File sizes
    small_files = []
    for stem, info in actual_files.items():
        if info["size"] < 10240:  # < 10KB
            small_files.append(f"{info['name']} ({info['size']} bytes)")
    checks["file_sizes"] = {
        "ok": len(small_files) == 0,
        "detail": f"Too small: {small_files}" if small_files else "All files > 10KB",
    }
    if small_files:
        issues.append(f"Small files: {small_files}")
    
    # Check 4: Legend completeness
    if legends:
        no_legend = [l for l in legends if not l["legend"] or l["legend"] in ("待补充", "N/A")]
        checks["legend_complete"] = {
            "ok": len(no_legend) == 0,
            "detail": f"Missing legends: {[l['id'] for l in no_legend]}" if no_legend else "All legends filled",
        }
    else:
        checks["legend_complete"] = {
            "ok": False,
            "detail": "No legend file to check",
        }
    
    # Check 5: External link reachability
    external_urls = [img["url"] for img in note_images["external"]]
    unreachable_urls = []
    if external_urls:
        import subprocess
        for url in external_urls[:20]:  # Limit to 20 to avoid timeout
            try:
                result = subprocess.run(
                    ["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code}", url],
                    capture_output=True, text=True, timeout=10
                )
                status = result.stdout.strip()
                if status not in ("200", "301", "302"):
                    unreachable_urls.append(f"{url} ({status})")
            except Exception:
                unreachable_urls.append(f"{url} (timeout)")
    checks["external_links"] = {
        "ok": len(unreachable_urls) == 0,
        "detail": f"Unreachable: {unreachable_urls}" if unreachable_urls else f"All {len(external_urls)} external links reachable",
    }
    if unreachable_urls:
        issues.append(f"Unreachable external links: {unreachable_urls}")
    
    # Check 6: Note references match legend
    if legends:
        legend_ids = {l["id"] for l in legends}
        note_stems = {img["stem"] for img in note_images["local"] + note_images["external"]}
        unmatched = note_stems - legend_ids
        checks["reference_match"] = {
            "ok": len(unmatched) == 0,
            "detail": f"Not in legend: {unmatched}" if unmatched else "All references match",
        }
    else:
        # No legend — skip MinerU re-extraction, just report
        checks["reference_match"] = {
            "ok": False,
            "detail": "No legend file. Run paper-reader first to generate legend.",
        }

    # Stats
    stats = {
        "note_local_images": len(note_images["local"]),
        "note_external_images": len(note_images["external"]),
        "actual_files": len(actual_files),
        "legend_entries": len(legends),
        "total_note_refs": len(note_images["local"]) + len(note_images["external"]),
    }
    
    # Check 7: Figure type consistency (architecture vs results, etc.)
    type_check = check_figure_type_consistency(note_path, vault_path)
    checks["figure_type_match"] = type_check
    if not type_check["ok"]:
        issues.append(f"Figure type mismatches: {type_check['detail']}")
        mismatches = type_check.get("mismatches", [])
        for m in mismatches[:5]:
            issues.append(f"  [{m['severity']}] {m['image']}: note says '{m['note_claim_type']}' but paper figure caption '{m['paper_caption'][:60]}...' says '{m['paper_actual_type']}'")

    # Check 8: 方法详解 → 模型架构 section integrity
    arch_check = check_model_architecture_section(note_path, vault_path)
    checks["model_arch_section"] = arch_check
    if not arch_check["ok"]:
        issues.append(f"模型架构 section: {arch_check['detail']}")
        for iss in arch_check.get("issues", []):
            issues.append(f"  ⚠️ {iss}")

    # Critical checks: these indicate real problems
    critical_keys = {"local_files_exist", "file_sizes", "reference_match", "external_links", "figure_type_match", "model_arch_section"}
    critical_ok = all(checks[k]["ok"] for k in critical_keys if k in checks)
    # Non-critical: legend_complete (caption missing), etc.
    all_ok = all(c["ok"] for c in checks.values())

    return {
        "method": method_name,
        "note": str(note_path),
        "assets_dir": str(assets_dir),
        "legend_path": str(legend_path),
        "checks": checks,
        "stats": stats,
        "issues": issues,
        "status": "passed" if critical_ok else "failed",
        "all_passed": all_ok,
    }


def write_check_result(vault_path: Path, result: dict):
    """Write check result to CheckResults/ directory."""
    check_dir = vault_path / "CheckResults"
    check_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = check_dir / f"{result['method']}.md"
    
    lines = [
        "---",
        f'title: "Image Check: {result["method"]}"',
        f'date: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'status: {result["status"]}',
        f'paper_path: {result["note"]}',
        "---",
        "",
        f'# Image Check Report: {result["method"]}',
        "",
        "## 检查结果",
        "",
        "| 检查项 | 状态 | 详情 |",
        "|--------|------|------|",
    ]
    
    for check_name, check_result in result["checks"].items():
        status = "✅" if check_result["ok"] else "❌"
        lines.append(f"| {check_name} | {status} | {check_result['detail']} |")
    
    lines.extend([
        "",
        "## 统计",
        "",
        f"- 笔记中本地图片引用: {result['stats']['note_local_images']}",
        f"- 笔记中外链图片引用: {result['stats']['note_external_images']}",
        f"- Assets 目录实际文件: {result['stats']['actual_files']}",
        f"- Legend 条目数: {result['stats']['legend_entries']}",
        "",
    ])
    
    # Add figure type mismatch details
    type_check = result["checks"].get("figure_type_match", {})
    if type_check and type_check.get("mismatches"):
        lines.extend([
            "",
            "## 🔍 图片类型一致性检查",
            "",
            "| 图片 | Section | 笔记声称类型 | 论文实际类型 | 论文Caption | 严重程度 |",
            "|------|---------|-------------|-------------|-------------|---------|",
        ])
        for m in type_check["mismatches"]:
            severity_icon = "🔴" if m["severity"] == "high" else "🟡"
            lines.append(
                f"| {m['image']} | {m['section_heading'][:30]} | {m['note_claim_type']} "
                f"| {m['paper_actual_type']} | {m['paper_caption'][:60]} | {severity_icon} {m['severity']} |"
            )

    # Add model architecture section details
    arch_check = result["checks"].get("model_arch_section", {})
    if arch_check:
        lines.extend([
            "",
            "## 🏗️ 模型架构 Section 检查",
            "",
            f"| 检查项 | 结果 |",
            f"|--------|------|",
            f"| Section 存在 | {'✅' if arch_check.get('section_found') else '❌'} |",
            f"| Mermaid 图 | {'✅' if arch_check.get('has_mermaid') else '⚠️'} |",
            f"| 论文架构图引用 | {'✅' if arch_check.get('arch_figure_in_section') else '🟡 不在该section中'} |",
            f"| 论文架构图ID | {arch_check.get('paper_arch_figure', 'N/A')} |",
            f"| 论文架构图Caption | {arch_check.get('paper_arch_caption', 'N/A')[:80]} |",
            f"| Section内图片引用数 | {arch_check.get('figure_refs_in_section', 0)} |",
        ])

    if result["issues"]:
        lines.extend([
            "",
            "## ⚠️ 需要修复",
            "",
        ])
        for issue in result["issues"]:
            lines.append(f"- {issue}")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def print_report(result: dict):
    """Print human-readable report."""
    print(f"\n{'='*60}")
    print(f"Image Check: {result['method']}")
    print(f"Status: {result['status'].upper()}")
    print(f"{'='*60}\n")
    
    for name, check in result["checks"].items():
        icon = "✅" if check["ok"] else "❌"
        print(f"  {icon} {name}: {check['detail']}")
    
    print(f"\nStats: {result['stats']['total_note_refs']} refs, "
          f"{result['stats']['actual_files']} files, "
          f"{result['stats']['legend_entries']} legends")


def main():
    parser = argparse.ArgumentParser(description="Check image consistency")
    parser.add_argument("--note", required=True, help="Path to paper note .md")
    parser.add_argument("--vault", help="Vault path (auto-detected if not provided)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--write", action="store_true", help="Write result to CheckResults/")
    parser.add_argument("--generate-legend", action="store_true", help="Auto-generate legend if missing")
    
    args = parser.parse_args()
    
    vault_path = Path(args.vault) if args.vault else None
    if not vault_path:
        config = load_config()
        vault_path = Path(config.get("vault_path", "/root/.openclaw/shared/ObsidianVault"))
    
    note_path = Path(args.note)
    if not note_path.exists():
        print(f"Error: Note not found: {note_path}")
        sys.exit(1)
    
    result = check_images(note_path, vault_path)
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    
    if args.write:
        output = write_check_result(vault_path, result)
        print(f"\n📄 Report written to: {output}")
    
    # Auto-generate legend if requested and missing
    if args.generate_legend and not Path(result["legend_path"]).exists():
        note_text = Path(args.note).read_text(encoding="utf-8")
        arxiv_id = extract_arxiv_id(note_text)
        if arxiv_id:
            print(f"\n📝 Generating legend for {arxiv_id}...")
            import subprocess
            subprocess.run([
                sys.executable,
                str(Path(__file__).parent / "generate_legend.py"),
                "--note", args.note,
                "--assets", result["assets_dir"],
                "--arxiv", arxiv_id,
            ])
    
    sys.exit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
