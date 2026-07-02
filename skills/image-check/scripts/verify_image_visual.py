#!/usr/bin/env python3
"""
Visual verification of images using a vision model.

Usage:
    python3 verify_image_visual.py --image /path/to/image.png --caption "Figure 1: description" [--arxiv-id 2506.09366]

This script prepares the verification prompt and image for a vision model to check.
The actual verification is done by the calling agent using a vision-capable model.
"""

import argparse
import base64
import json
import sys
from pathlib import Path


def prepare_verification(image_path: str, caption: str, paper_title: str = "") -> dict:
    """Prepare image verification data for a vision model."""
    img_path = Path(image_path)
    
    if not img_path.exists():
        return {"ok": False, "error": f"Image not found: {image_path}"}
    
    # Read image as base64
    with open(img_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")
    
    ext = img_path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(ext, "image/png")
    
    return {
        "ok": True,
        "image_path": str(img_path),
        "image_base64": img_data,
        "mime": mime,
        "caption": caption,
        "paper_title": paper_title,
        "prompt": f"""You are an image verification assistant for academic papers.

Paper: {paper_title}

The following image is from this paper. The assigned caption/legend is:

"{caption}"

Please verify:
1. Does the caption accurately describe the image content?
2. Is the image readable (not corrupted, blurry, or blank)?
3. Is this a figure from an academic paper (not an unrelated image)?

Respond in JSON format:
{{
  "caption_accurate": true/false,
  "image_readable": true/false,
  "is_paper_figure": true/false,
  "issues": ["list of issues found"],
  "suggested_caption": "better caption if current one is inaccurate, or null"
}}"""
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare image visual verification")
    parser.add_argument("--image", required=True, help="Path to image file")
    parser.add_argument("--caption", required=True, help="Caption/legend to verify")
    parser.add_argument("--title", default="", help="Paper title")
    parser.add_argument("--output", help="Output JSON path (default: stdout)")
    
    args = parser.parse_args()
    
    result = prepare_verification(args.image, args.caption, args.title)
    
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✅ Verification data written to: {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
