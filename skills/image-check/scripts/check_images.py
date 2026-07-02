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


def extract_figures_via_mineru(arxiv_id: str) -> list:
    """Full MinerU extraction pipeline with PDF splitting (same as paper-reader)."""
    import subprocess

    pdf_path = Path(f"/tmp/paper_verify_{arxiv_id}.pdf")
    mineru_dir = Path(f"/tmp/paper_verify_mineru_{arxiv_id}")

    # Download PDF
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

    # Split if ≥1MB (reuse paper-reader's split script)
    split_script = Path(__file__).parent.parent.parent / "paper-reader" / "scripts" / "split_pdf_for_mineru.sh"

    if pdf_size_mb >= 1 and split_script.exists():
        chunks_dir = Path(f"/tmp/paper_verify_chunks_{arxiv_id}")
        try:
            subprocess.run(
                ["bash", str(split_script), str(pdf_path), str(chunks_dir)],
                capture_output=True, timeout=120
            )
            # Process each chunk
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
                    # Merge images
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

    # Find MinerU markdown output
    md_files = list(mineru_dir.glob("**/*.md"))
    images_dir = mineru_dir / "images"

    if not images_dir.exists() or not md_files:
        return []

    # Extract figures from markdown (chunk if large)
    all_figures = []
    md_text = md_files[0].read_text(encoding="utf-8")
    md_lines = md_text.count('\n')

    if md_lines > 500:
        # Large markdown — chunk extraction
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

    # Add image file paths
    for fig in all_figures:
        if fig.get("local_path"):
            full_path = mineru_dir / fig["local_path"]
            if full_path.exists():
                fig["local_path"] = str(full_path)

    # Also list images that aren't referenced in markdown
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

    # Cleanup
    try:
        pdf_path.unlink(missing_ok=True)
    except Exception:
        pass

    return all_figures


def fetch_paper_figures_from_html(arxiv_id: str) -> list:
    """Fetch figure info directly from arXiv HTML."""
    import subprocess
    url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        html = result.stdout
    except Exception:
        return []

    figures = []
    fig_pattern = re.compile(r'<figure[^>]*>(.*?)</figure>', re.DOTALL)
    img_pattern = re.compile(r'<img[^>]*src=["\']([^"\']+)["\']', re.DOTALL)
    caption_pattern = re.compile(r'<figcaption[^>]*>(.*?)</figcaption>', re.DOTALL)

    for fig_match in fig_pattern.finditer(html):
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


def fetch_paper_figures_from_mineru(arxiv_id: str) -> list:
    """Fetch figure info from MinerU PDF extraction."""
    import subprocess

    pdf_path = Path(f"/tmp/paper_verify_{arxiv_id}.pdf")
    mineru_dir = Path(f"/tmp/paper_verify_mineru_{arxiv_id}")

    # Download PDF
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

    # Split if needed (reuse paper-reader's split script)
    split_script = Path(__file__).parent.parent.parent / "paper-reader" / "scripts" / "split_pdf_for_mineru.sh"

    if pdf_size_mb >= 1 and split_script.exists():
        chunks_dir = Path(f"/tmp/paper_verify_chunks_{arxiv_id}")
        try:
            subprocess.run(
                ["bash", str(split_script), str(pdf_path), str(chunks_dir)],
                capture_output=True, timeout=120
            )
            # Process each chunk
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
                    # Merge images
                    for img in chunk_dir.glob("images/*"):
                        img.rename(mineru_dir / "images" / img.name)
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

    # Extract figures from MinerU output
    figures = []
    images_dir = mineru_dir / "images"
    md_file = mineru_dir / f"paper_{arxiv_id}.md"

    if not md_file.exists():
        # Try finding any .md file
        md_files = list(mineru_dir.glob("**/*.md"))
        if md_files:
            md_file = md_files[0]

    if images_dir.exists():
        for i, img_file in enumerate(sorted(images_dir.iterdir()), 1):
            if img_file.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                # Try to find caption from markdown
                caption = ""
                if md_file.exists():
                    md_text = md_file.read_text(encoding="utf-8")
                    # Look for figure references near the image filename
                    stem = img_file.stem
                    cap_match = re.search(
                        rf'(?:Figure|Fig\.?)\s*{i}[:\s]*(.*?)(?:\n\n|\n#|\Z)',
                        md_text, re.DOTALL | re.IGNORECASE
                    )
                    if cap_match:
                        caption = cap_match.group(1).strip()[:200]

                figures.append({
                    "id": f"fig{i}",
                    "url": "",
                    "local_path": str(img_file),
                    "caption": caption or "N/A",
                    "filename": img_file.name,
                    "source": "mineru",
                })

    # Cleanup temp files
    try:
        pdf_path.unlink(missing_ok=True)
    except Exception:
        pass

    return figures


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
    legends = load_legend(legend_path)
    
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
        no_legend = [l for l in legends if not l["legend"] or l["legend"] == "待补充"]
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
        # No legend — verify against original paper
        paper_verify = verify_against_paper(note_path, vault_path)
        if paper_verify["ok"]:
            checks["reference_match"] = {
                "ok": True,
                "detail": f"Verified against paper ({paper_verify.get('source', '?')}): "
                          f"{paper_verify['matched']}/{paper_verify['paper_figures']} figures matched",
            }
            checks["paper_verify"] = {
                "ok": len(paper_verify.get("unmatched_note", [])) == 0,
                "detail": f"Source: {paper_verify.get('source', '?')}, "
                          f"Paper has {paper_verify['paper_figures']} figures, "
                          f"note refs {paper_verify['note_refs']}, "
                          f"matched {paper_verify['matched']}, "
                          f"missing from note: {paper_verify.get('missing_from_note', [])}",
            }
        else:
            checks["reference_match"] = {
                "ok": False,
                "detail": paper_verify.get("detail", "No legend and cannot verify against paper"),
            }
            checks["paper_verify"] = {
                "ok": False,
                "detail": paper_verify.get("detail", "Could not fetch original paper"),
            }
    
    # Stats
    stats = {
        "note_local_images": len(note_images["local"]),
        "note_external_images": len(note_images["external"]),
        "actual_files": len(actual_files),
        "legend_entries": len(legends),
        "total_note_refs": len(note_images["local"]) + len(note_images["external"]),
    }
    
    all_ok = all(c["ok"] for c in checks.values())
    
    return {
        "method": method_name,
        "note": str(note_path),
        "assets_dir": str(assets_dir),
        "legend_path": str(legend_path),
        "checks": checks,
        "stats": stats,
        "issues": issues,
        "status": "passed" if all_ok else "failed",
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
    
    if result["issues"]:
        lines.extend([
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
