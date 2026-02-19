"""YAML-backed project registry for thread mode."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass(frozen=True)
class ProjectDefinition:
    """Project entry from YAML configuration."""

    slug: str
    name: str
    relative_path: Path
    absolute_path: Path
    enabled: bool = True


class ProjectRegistry:
    """In-memory validated project registry."""

    def __init__(self, projects: List[ProjectDefinition]) -> None:
        self._projects = projects
        self._by_slug: Dict[str, ProjectDefinition] = {p.slug: p for p in projects}

    @property
    def projects(self) -> List[ProjectDefinition]:
        """Return all projects."""
        return list(self._projects)

    def list_enabled(self) -> List[ProjectDefinition]:
        """Return enabled projects only."""
        return [p for p in self._projects if p.enabled]

    def get_by_slug(self, slug: str) -> Optional[ProjectDefinition]:
        """Get project by slug."""
        return self._by_slug.get(slug)


def load_project_registry(
    config_path: Path, approved_directory: Path
) -> ProjectRegistry:
    """Load and validate project definitions from YAML."""
    if not config_path.exists():
        raise ValueError(f"Projects config file does not exist: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError("Projects config must be a YAML object")

    raw_projects = data.get("projects")
    if not isinstance(raw_projects, list) or not raw_projects:
        raise ValueError("Projects config must contain a non-empty 'projects' list")

    approved_root = approved_directory.resolve()
    seen_slugs = set()
    seen_names = set()
    seen_rel_paths = set()
    projects: List[ProjectDefinition] = []

    for idx, raw in enumerate(raw_projects):
        if not isinstance(raw, dict):
            raise ValueError(f"Project entry at index {idx} must be an object")

        slug = str(raw.get("slug", "")).strip()
        name = str(raw.get("name", "")).strip()
        rel_path_raw = str(raw.get("path", "")).strip()
        enabled = bool(raw.get("enabled", True))

        if not slug:
            raise ValueError(f"Project entry at index {idx} is missing 'slug'")
        if not name:
            raise ValueError(f"Project '{slug}' is missing 'name'")
        if not rel_path_raw:
            raise ValueError(f"Project '{slug}' is missing 'path'")

        rel_path = Path(rel_path_raw)
        if rel_path.is_absolute():
            raise ValueError(f"Project '{slug}' path must be relative: {rel_path_raw}")

        absolute_path = (approved_root / rel_path).resolve()

        try:
            absolute_path.relative_to(approved_root)
        except ValueError as e:
            raise ValueError(
                f"Project '{slug}' path outside approved " f"directory: {rel_path_raw}"
            ) from e

        if not absolute_path.exists() or not absolute_path.is_dir():
            raise ValueError(
                f"Project '{slug}' path does not exist or "
                f"is not a directory: {absolute_path}"
            )

        rel_path_norm = str(rel_path)
        if slug in seen_slugs:
            raise ValueError(f"Duplicate project slug: {slug}")
        if name in seen_names:
            raise ValueError(f"Duplicate project name: {name}")
        if rel_path_norm in seen_rel_paths:
            raise ValueError(f"Duplicate project path: {rel_path_norm}")

        seen_slugs.add(slug)
        seen_names.add(name)
        seen_rel_paths.add(rel_path_norm)

        projects.append(
            ProjectDefinition(
                slug=slug,
                name=name,
                relative_path=rel_path,
                absolute_path=absolute_path,
                enabled=enabled,
            )
        )

    return ProjectRegistry(projects)
