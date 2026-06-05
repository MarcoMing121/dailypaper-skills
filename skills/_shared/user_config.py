#!/usr/bin/env python3

import copy
import json
from functools import lru_cache
from pathlib import Path


DEFAULT_CONFIG = {
    "paths": {
        "obsidian_vault": "/root/.openclaw/shared/ObsidianVault",
        "paper_notes_folder": "Papers",
        "daily_papers_folder": "DailyPapers",
        "concepts_folder": "Concepts",
        "search_results_folder": "SearchResults",
        "social_images_cache": "/root/.openclaw/workspaces/paper-agent/.cache/social-images",
        "zotero_db": "~/Zotero/zotero.sqlite",
        "zotero_storage": "~/Zotero/storage",
    },
    "daily_papers": {
        "keywords": [
            "world model",
            "diffusion model",
            "embodied ai",
            "3d gaussian splatting",
            "4d gaussian splatting",
            "sim-to-real",
            "sim2real",
            "robot simulation",
        ],
        "negative_keywords": [
            "medical imaging",
            "weather forecast",
            "climate",
            "pet restoration",
            "mri",
            "ct scan",
            "pathology",
            "diagnosis",
            "protein",
            "drug discovery",
            "molecular",
            "audio generation",
            "music generation",
            "speech synthesis",
            "text-to-speech",
            "speech recognition",
            "voice cloning",
            "coding agent",
            "code agent",
            "code generation",
            "software engineering agent",
            "gui agent",
            "computer use",
            "web agent",
            "browser agent",
            "document parsing",
            "document understanding",
            "ocr",
            "rag framework",
            "retrieval augmented",
            "retrieval-augmented",
            "llm memory",
            "long-term memory for llm",
            "text-to-sql",
            "code repair",
            "code review",
            "trading",
            "financial",
        ],
        "domain_boost_keywords": [
            "robot",
            "manipulation",
            "grasping",
            "locomotion",
            "navigation",
            "planning",
            "reinforcement learning",
            "policy learning",
            "visuomotor",
            "action prediction",
        ],
        "arxiv_categories": ["cs.RO", "cs.CV", "cs.AI", "cs.LG"],
        "min_score": 2,
        "top_n": 30,
    },
    "automation": {
        "auto_refresh_indexes": True,
        "git_commit": True,
        "git_push": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@lru_cache(maxsize=1)
def load_user_config() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_dir = Path(__file__).resolve().parent

    # Only load local override if exists (optional)
    local_path = config_dir / "user-config.local.json"
    if local_path.exists():
        with local_path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            _deep_merge(config, loaded)

    return config


def _expand(path_value: str) -> Path:
    return Path(path_value).expanduser()


def paths_config() -> dict:
    return load_user_config()["paths"]


def daily_papers_config() -> dict:
    return load_user_config()["daily_papers"]


def automation_config() -> dict:
    config = load_user_config()["automation"]
    if config.get("git_push") and not config.get("git_commit"):
        config = copy.deepcopy(config)
        config["git_push"] = False
    return config


def obsidian_vault_path() -> Path:
    return _expand(paths_config()["obsidian_vault"])


def paper_notes_dir() -> Path:
    return obsidian_vault_path() / paths_config()["paper_notes_folder"]


def daily_papers_dir() -> Path:
    return obsidian_vault_path() / paths_config()["daily_papers_folder"]


def concepts_dir() -> Path:
    # concepts_folder is relative to VAULT root, not paper_notes_dir
    return obsidian_vault_path() / paths_config()["concepts_folder"]


def search_results_dir() -> Path:
    return obsidian_vault_path() / paths_config().get("search_results_folder", "SearchResults")


def social_images_cache_dir() -> Path:
    return Path(paths_config().get("social_images_cache", "/tmp/social-images"))


def zotero_db_path() -> Path:
    return _expand(paths_config()["zotero_db"])


def zotero_storage_dir() -> Path:
    return _expand(paths_config()["zotero_storage"])


def auto_refresh_indexes_enabled() -> bool:
    return bool(automation_config()["auto_refresh_indexes"])


def git_commit_enabled() -> bool:
    return bool(automation_config()["git_commit"])


def git_push_enabled() -> bool:
    return bool(automation_config()["git_push"])
