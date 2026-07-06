#!/usr/bin/env python3
"""
Image Understanding Pipeline — post-processing for paper notes.

Runs AFTER paper-reader creates a note. Uses vision model to verify and fix
image captions by comparing what the note says vs what the image actually shows.

Usage:
    python3 image_understand.py --note /path/to/note.md --output /tmp/figures_manifest.json

The agent then:
1. Reads manifest.json
2. For each figure, sends image_base64 + prompt to vision model
3. Vision model returns: what the image actually shows
4. Agent compares with note caption, fixes if wrong
5. Agent writes updated legend.md
"""

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def extract_note_images(note_text: str) -> list:
    """Extract all image references from a paper note with their context."""
    images = []

    # Obsidian wikilinks: ![[Method/fig1.png|500]]
    for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|(\d+))?\]\]', note_text):
        link = match.group(1)
        # Get surrounding text for context (the paragraph before the image)
        start = max(0, match.start() - 500)
        before_text = note_text[start:match.start()]
        # Find the nearest heading
        heading_match = re.search(r'^#+\s+(.+)$', before_text, re.MULTILINE)
        section = heading_match.group(1).strip() if heading_match else ""

        # Find caption: text between image and next paragraph, or text after image
        after_text = note_text[match.end():match.end()+300]
        caption_match = re.search(r'^\s*(.+?)(?:\n\n|\n#|\Z)', after_text, re.DOTALL)
        note_caption = caption_match.group(1).strip()[:200] if caption_match else ""

        images.append({
            "id": Path(link).stem,
            "reference": f"![[{link}]]",
            "section": section,
            "note_caption": note_caption,
        })

    # External markdown images: ![alt](url)
    for match in re.finditer(r'!\[([^\]]*)\]\((https?://[^)]+)\)', note_text):
        alt = match.group(1)
        url = match.group(2)
        start = max(0, match.start() - 500)
        before_text = note_text[start:match.start()]
        heading_match = re.search(r'^#+\s+(.+)$', before_text, re.MULTILINE)
        section = heading_match.group(1).strip() if heading_match else ""

        after_text = note_text[match.end():match.end()+300]
        caption_match = re.search(r'^\s*(.+?)(?:\n\n|\n#|\Z)', after_text, re.DOTALL)
        note_caption = caption_match.group(1).strip()[:200] if caption_match else ""

        images.append({
            "id": alt or Path(url).stem,
            "reference": f"![{alt}]({url})",
            "section": section,
            "note_caption": note_caption,
        })

    return images


def resolve_image_path(image_id: str, reference: str, assets_dir: Path) -> str:
    """Find the actual image file path."""
    # From wikilink: ![[Method/fig1.png]]
    wikilink_match = re.search(r'!\[\[([^\]|]+)', reference)
    if wikilink_match:
        link = wikilink_match.group(1)
        # Try full path relative to vault
        # Try just the filename in assets
        candidates = [
            assets_dir / Path(link).name,
            assets_dir / f"{image_id}.png",
            assets_dir / f"{image_id}.jpg",
            assets_dir / f"{image_id}.jpeg",
        ]
        for c in candidates:
            if c.exists():
                return str(c)

    # From external URL
    url_match = re.search(r'\((https?://[^)]+)\)', reference)
    if url_match:
        # Download to tmp
        url = url_match.group(1)
        try:
            ext = Path(url).suffix or ".png"
            tmp_path = Path(f"/tmp/image_understand_{image_id}{ext}")
            subprocess.run(
                ["curl", "-sL", url, "-o", str(tmp_path)],
                capture_output=True, timeout=30
            )
            if tmp_path.exists() and tmp_path.stat().st_size > 1000:
                return str(tmp_path)
        except Exception:
            pass

    return ""


def load_image_base64(img_path: str) -> tuple:
    """Load image as base64 with mime type."""
    p = Path(img_path)
    if not p.exists():
        return "", ""

    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(p.suffix.lower(), "image/png")
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return b64, mime


def find_arxiv_id(note_text: str) -> str:
    """Extract arXiv ID from note."""
    match = re.search(r'arxiv.*?(\d{4}\.\d{4,5})', note_text)
    if match:
        return match.group(1)
    match = re.search(r'arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})', note_text)
    if match:
        return match.group(1)
    return ""


def get_paper_images_from_html(arxiv_id: str) -> list:
    """Get all figures from arXiv HTML (to find images not in note)."""
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
        cap_match = caption_pattern.search(fig_html)
        html_caption = ""
        if cap_match:
            html_caption = re.sub(r'<[^>]+>', '', cap_match.group(1)).strip()

        if filename:
            figures.append({
                "id": filename,
                "url": img_url,
                "html_caption": html_caption[:300],
            })

    return figures


def main():
    parser = argparse.ArgumentParser(description="Image understanding pipeline (post paper-reader)")
    parser.add_argument("--note", required=True, help="Path to paper note .md")
    parser.add_argument("--assets", help="Assets directory (auto-detected if not provided)")
    parser.add_argument("--mineru-dir", help="MinerU temp directory (auto-detected from arXiv ID)")
    parser.add_argument("--output", required=True, help="Output manifest JSON path")
    parser.add_argument("--vault", help="Vault path (for auto-detecting assets)")

    args = parser.parse_args()

    note_path = Path(args.note)
    if not note_path.exists():
        print(f"❌ Note not found: {note_path}", file=sys.stderr)
        sys.exit(1)

    note_text = note_path.read_text(encoding="utf-8")
    method_name = note_path.stem

    # Find assets directory
    if args.assets:
        assets_dir = Path(args.assets)
    else:
        vault = Path(args.vault) if args.vault else Path("/root/.openclaw/shared/ObsidianVault")
        assets_dir = None
        for match in re.finditer(r'!\[\[([^\]|]+)/', note_text):
            dir_name = match.group(1)
            candidate = vault / "assets" / dir_name
            if candidate.exists():
                assets_dir = candidate
                break
        if not assets_dir:
            assets_dir = vault / "assets" / method_name

    # Find arXiv ID
    arxiv_id = find_arxiv_id(note_text)

    # Find MinerU directory (check cache from image-check's extract_figures_via_mineru)
    mineru_dir = None
    if args.mineru_dir:
        mineru_dir = Path(args.mineru_dir)
    elif arxiv_id:
        # Check standard MinerU cache locations
        candidates = [
            Path(f"/tmp/paper_verify_mineru_{arxiv_id}"),  # image-check cache
            Path(f"/tmp/paper_mineru_{arxiv_id}"),          # paper-reader temp
        ]
        for c in candidates:
            if c.exists() and (c / "images").exists():
                mineru_dir = c
                break

    print(f"📄 Note: {note_path}", file=sys.stderr)
    print(f"📁 Assets: {assets_dir}", file=sys.stderr)
    if mineru_dir:
        print(f"⛏️  MinerU: {mineru_dir}", file=sys.stderr)

    # Extract images from note
    note_images = extract_note_images(note_text)
    print(f"🖼️  Found {len(note_images)} image references in note", file=sys.stderr)

    # Get paper images from HTML or MinerU
    paper_images = []
    if arxiv_id:
        print(f"📥 Fetching paper HTML for {arxiv_id}...", file=sys.stderr)
        paper_images = get_paper_images_from_html(arxiv_id)
        print(f"   Found {len(paper_images)} figures in paper HTML", file=sys.stderr)

    # If HTML had few images, supplement from MinerU
    mineru_images = []
    if mineru_dir:
        mineru_images_dir = mineru_dir / "images"
        if mineru_images_dir.exists():
            # Check for figures_cache.json (from image-check's cached extraction)
            cache_file = mineru_dir / "figures_cache.json"
            if cache_file.exists():
                try:
                    cached = json.loads(cache_file.read_text(encoding="utf-8"))
                    for fig in cached:
                        mineru_images.append({
                            "id": fig.get("id", ""),
                            "local_path": fig.get("local_path", ""),
                            "caption": fig.get("caption", ""),
                        })
                except Exception:
                    pass

            # Also scan images directory directly
            if not mineru_images:
                for img_file in sorted(mineru_images_dir.iterdir()):
                    if img_file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                        mineru_images.append({
                            "id": img_file.stem,
                            "local_path": str(img_file),
                            "caption": "",
                        })

        print(f"⛏️  Found {len(mineru_images)} images in MinerU directory", file=sys.stderr)

    # Build manifest entries
    figures = []
    note_image_ids = set()

    # Images referenced in note
    for img in note_images:
        img_path = resolve_image_path(img["id"], img["reference"], assets_dir)
        b64, mime = load_image_base64(img_path) if img_path else ("", "")

        figures.append({
            "id": img["id"],
            "in_note": True,
            "reference": img["reference"],
            "section": img["section"],
            "note_caption": img["note_caption"],
            "local_path": img_path,
            "image_base64": b64,
            "mime": mime,
            "html_caption": "",
            "mineru_caption": "",
            "vision_caption": "",
            "figure_type": "",
            "needs_fix": False,
            "vision_analyzed": False,
        })
        note_image_ids.add(img["id"])

    # Images in arXiv HTML but NOT in note
    for paper_img in paper_images:
        if paper_img["id"] not in note_image_ids:
            img_path = ""
            try:
                ext = Path(paper_img["url"]).suffix or ".png"
                tmp_path = Path(f"/tmp/image_understand_{paper_img['id']}{ext}")
                subprocess.run(
                    ["curl", "-sL", paper_img["url"], "-o", str(tmp_path)],
                    capture_output=True, timeout=30
                )
                if tmp_path.exists() and tmp_path.stat().st_size > 1000:
                    img_path = str(tmp_path)
            except Exception:
                pass

            b64, mime = load_image_base64(img_path) if img_path else ("", "")
            figures.append({
                "id": paper_img["id"],
                "in_note": False,
                "reference": "",
                "section": "",
                "note_caption": "",
                "local_path": img_path,
                "image_base64": b64,
                "mime": mime,
                "html_caption": paper_img.get("html_caption", ""),
                "mineru_caption": "",
                "vision_caption": "",
                "figure_type": "",
                "needs_fix": False,
                "vision_analyzed": False,
            })
            note_image_ids.add(paper_img["id"])

    # Images in MinerU but NOT in note or HTML
    for mimg in mineru_images:
        if mimg["id"] not in note_image_ids:
            img_path = mimg.get("local_path", "")
            b64, mime = load_image_base64(img_path) if img_path else ("", "")
            figures.append({
                "id": mimg["id"],
                "in_note": False,
                "reference": "",
                "section": "",
                "note_caption": "",
                "local_path": img_path,
                "image_base64": b64,
                "mime": mime,
                "html_caption": "",
                "mineru_caption": mimg.get("caption", ""),
                "vision_caption": "",
                "figure_type": "",
                "needs_fix": False,
                "vision_analyzed": False,
            })

    # Write manifest
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generated": datetime.now().isoformat(),
        "note": str(note_path),
        "assets_dir": str(assets_dir),
        "mineru_dir": str(mineru_dir) if mineru_dir else "",
        "arxiv_id": arxiv_id,
        "total_figures": len(figures),
        "in_note": sum(1 for f in figures if f["in_note"]),
        "missing_from_note": sum(1 for f in figures if not f["in_note"]),
        "analyzed": 0,
        "figures": figures,
    }

    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ Manifest written to: {output_path}", file=sys.stderr)
    print(f"   In note: {manifest['in_note']}", file=sys.stderr)
    print(f"   Missing from note: {manifest['missing_from_note']}", file=sys.stderr)
    print(f"\n📋 Figures:", file=sys.stderr)
    for i, fig in enumerate(figures, 1):
        status = "📝" if fig["in_note"] else "⚠️ MISSING"
        has_b64 = "📷" if fig["image_base64"] else "❌"
        src = "html" if fig.get("html_caption") else ("mineru" if fig.get("mineru_caption") else "assets")
        print(f"  {i}. {status} {has_b64} [{src}] {fig['id']}", file=sys.stderr)


if __name__ == "__main__":
    main()
