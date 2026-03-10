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
    config_path: Path, approved_directory: Path, approved_directories: Optional[List[Path]] = None
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

    # Build list of all approved directories
    all_approved_dirs = [approved_directory.resolve()]
    if approved_directories:
        all_approved_dirs.extend([d.resolve() for d in approved_directories])

    seen_slugs = set()
    seen_names = set()
    seen_abs_paths = set()
    projects: List[ProjectDefinition] = []

    for idx, raw in enumerate(raw_projects):
        if not isinstance(raw, dict):
            raise ValueError(f"Project entry at index {idx} must be an object")

        slug = str(raw.get("slug", "")).strip()
        name = str(raw.get("name", "")).strip()
        path_raw = str(raw.get("path", "")).strip()
        enabled = bool(raw.get("enabled", True))

        if not slug:
            raise ValueError(f"Project entry at index {idx} is missing 'slug'")
        if not name:
            raise ValueError(f"Project '{slug}' is missing 'name'")
        if not path_raw:
            raise ValueError(f"Project '{slug}' is missing 'path'")

        path_obj = Path(path_raw)

        # Handle both absolute and relative paths
        if path_obj.is_absolute():
            # Absolute path - validate it's within one of the approved directories
            absolute_path = path_obj.resolve()

            # Check if path is within any approved directory
            is_within_any = False
            matched_base = None
            for approved_dir in all_approved_dirs:
                try:
                    rel = absolute_path.relative_to(approved_dir)
                    is_within_any = True
                    matched_base = approved_dir
                    relative_path = rel
                    break
                except ValueError:
                    continue

            if not is_within_any:
                raise ValueError(
                    f"Project '{slug}' absolute path is outside all approved directories: {path_raw}"
                )
        else:
            # Relative path - resolve against primary approved_directory
            relative_path = path_obj
            absolute_path = (approved_directory / relative_path).resolve()

            # Validate it's within one of the approved directories
            is_within_any = False
            for approved_dir in all_approved_dirs:
                try:
                    absolute_path.relative_to(approved_dir)
                    is_within_any = True
                    break
                except ValueError:
                    continue

            if not is_within_any:
                raise ValueError(
                    f"Project '{slug}' path outside all approved directories: {path_raw}"
                )

        if not absolute_path.exists() or not absolute_path.is_dir():
            raise ValueError(
                f"Project '{slug}' path does not exist or "
                f"is not a directory: {absolute_path}"
            )

        abs_path_str = str(absolute_path)
        if slug in seen_slugs:
            raise ValueError(f"Duplicate project slug: {slug}")
        if name in seen_names:
            raise ValueError(f"Duplicate project name: {name}")
        if abs_path_str in seen_abs_paths:
            raise ValueError(f"Duplicate project path: {abs_path_str}")

        seen_slugs.add(slug)
        seen_names.add(name)
        seen_abs_paths.add(abs_path_str)

        projects.append(
            ProjectDefinition(
                slug=slug,
                name=name,
                relative_path=relative_path,
                absolute_path=absolute_path,
                enabled=enabled,
            )
        )

    return ProjectRegistry(projects)
