"""
Advanced file handling

Features:
- Multiple file processing
- Zip archive extraction
- Code analysis
- Diff generation
"""

import shutil
import tarfile
import uuid
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from telegram import Document

from src.config import Settings
from src.security.validators import SecurityValidator


@dataclass
class ProcessedFile:
    """Processed file result"""

    type: str
    prompt: str
    metadata: Dict[str, Any]


@dataclass
class CodebaseAnalysis:
    """Codebase analysis result"""

    languages: Dict[str, int]
    frameworks: List[str]
    entry_points: List[str]
    todo_count: int
    test_coverage: bool
    file_stats: Dict[str, int]


class FileHandler:
    """Handle various file operations"""

    def __init__(self, config: Settings, security: SecurityValidator):
        self.config = config
        self.security = security
        self.temp_dir = Path("/tmp/claude_bot_files")
        self.temp_dir.mkdir(exist_ok=True)

        # Supported code extensions
        self.code_extensions = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".scala",
            ".r",
            ".jl",
            ".lua",
            ".pl",
            ".sh",
            ".bash",
            ".zsh",
            ".fish",
            ".ps1",
            ".sql",
            ".html",
            ".css",
            ".scss",
            ".sass",
            ".less",
            ".vue",
            ".yaml",
            ".yml",
            ".json",
            ".xml",
            ".toml",
            ".ini",
            ".cfg",
            ".dockerfile",
            ".makefile",
            ".cmake",
            ".gradle",
            ".maven",
        }

        # Language mapping
        self.language_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".java": "Java",
            ".cpp": "C++",
            ".c": "C",
            ".go": "Go",
            ".rs": "Rust",
            ".rb": "Ruby",
            ".php": "PHP",
            ".swift": "Swift",
            ".kt": "Kotlin",
            ".scala": "Scala",
            ".r": "R",
            ".jl": "Julia",
            ".lua": "Lua",
            ".pl": "Perl",
            ".sh": "Shell",
            ".sql": "SQL",
            ".html": "HTML",
            ".css": "CSS",
            ".vue": "Vue",
            ".yaml": "YAML",
            ".json": "JSON",
            ".xml": "XML",
        }

    async def handle_document_upload(
        self, document: Document, user_id: int, context: str = ""
    ) -> ProcessedFile:
        """Process uploaded document"""

        # Download file
        file_path = await self._download_file(document)

        try:
            # Detect file type
            file_type = self._detect_file_type(file_path)

            # Process based on type
            if file_type == "archive":
                return await self._process_archive(file_path, context)
            elif file_type == "code":
                return await self._process_code_file(file_path, context)
            elif file_type == "text":
                return await self._process_text_file(file_path, context)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

        finally:
            # Cleanup
            file_path.unlink(missing_ok=True)

    async def _download_file(self, document: Document) -> Path:
        """Download file from Telegram"""
        # Get file
        file = await document.get_file()

        # Create temp file path
        file_name = document.file_name or f"file_{uuid.uuid4()}"
        file_path = self.temp_dir / file_name

        # Download to path
        await file.download_to_drive(str(file_path))

        return file_path

    def _detect_file_type(self, file_path: Path) -> str:
        """Detect file type based on extension and content"""
        ext = file_path.suffix.lower()

        # Check if archive
        if ext in {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z"}:
            return "archive"

        # Check if code
        if ext in self.code_extensions:
            return "code"

        # Check if text
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.read(1024)  # Try reading first 1KB
            return "text"
        except (UnicodeDecodeError, IOError):
            return "binary"

    async def _process_archive(self, archive_path: Path, context: str) -> ProcessedFile:
        """Extract and analyze archive contents"""

        # Create extraction directory
        extract_dir = self.temp_dir / f"extract_{uuid.uuid4()}"
        extract_dir.mkdir()

        try:
            # Extract based on type
            if archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path) as zf:
                    # Security check - prevent zip bombs
                    total_size = sum(f.file_size for f in zf.filelist)
                    if total_size > 100 * 1024 * 1024:  # 100MB limit
                        raise ValueError("Archive too large")

                    # Extract with security checks
                    for file_info in zf.filelist:
                        # Prevent path traversal
                        file_path = Path(file_info.filename)
                        if file_path.is_absolute() or ".." in file_path.parts:
                            continue

                        # Extract file
                        target_path = extract_dir / file_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        with (
                            zf.open(file_info) as source,
                            open(target_path, "wb") as target,
                        ):
                            shutil.copyfileobj(source, target)

            elif archive_path.suffix in {".tar", ".gz", ".bz2", ".xz"}:
                with tarfile.open(archive_path) as tf:
                    # Security checks
                    total_size = sum(member.size for member in tf.getmembers())
                    if total_size > 100 * 1024 * 1024:  # 100MB limit
                        raise ValueError("Archive too large")

                    # Extract with security checks
                    for member in tf.getmembers():
                        # Prevent path traversal
                        if member.name.startswith("/") or ".." in member.name:
                            continue

                        tf.extract(member, extract_dir)

            # Analyze contents
            file_tree = self._build_file_tree(extract_dir)
            code_files = self._find_code_files(extract_dir)

            # Create analysis prompt
            prompt = f"{context}\n\nProject structure:\n{file_tree}\n\n"

            # Add key files
            for file_path in code_files[:5]:  # Limit to 5 files
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                prompt += f"\nFile: {file_path.relative_to(extract_dir)}\n```\n{content[:1000]}...\n```\n"

            return ProcessedFile(
                type="archive",
                prompt=prompt,
                metadata={
                    "file_count": len(list(extract_dir.rglob("*"))),
                    "code_files": len(code_files),
                },
            )

        finally:
            # Cleanup
            shutil.rmtree(extract_dir, ignore_errors=True)

    async def _process_code_file(self, file_path: Path, context: str) -> ProcessedFile:
        """Process single code file"""
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Detect language
        language = self._detect_language(file_path.suffix)

        # Create prompt
        prompt = f"{context}\n\nFile: {file_path.name}\nLanguage: {language}\n\n```{language.lower()}\n{content}\n```"

        return ProcessedFile(
            type="code",
            prompt=prompt,
            metadata={
                "language": language,
                "lines": len(content.splitlines()),
                "size": file_path.stat().st_size,
            },
        )

    async def _process_text_file(self, file_path: Path, context: str) -> ProcessedFile:
        """Process text file"""
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Create prompt
        prompt = f"{context}\n\nFile: {file_path.name}\n\n{content}"

        return ProcessedFile(
            type="text",
            prompt=prompt,
            metadata={
                "lines": len(content.splitlines()),
                "size": file_path.stat().st_size,
            },
        )

    def _build_file_tree(self, directory: Path, prefix: str = "") -> str:
        """Build visual file tree"""
        items = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name))
        tree_lines = []

        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            current_prefix = "└── " if is_last else "├── "

            if item.is_dir():
                tree_lines.append(f"{prefix}{current_prefix}{item.name}/")
                # Recursive call with updated prefix
                sub_prefix = prefix + ("    " if is_last else "│   ")
                tree_lines.append(self._build_file_tree(item, sub_prefix))
            else:
                size = item.stat().st_size
                tree_lines.append(
                    f"{prefix}{current_prefix}{item.name} ({self._format_size(size)})"
                )

        return "\n".join(filter(None, tree_lines))

    def _format_size(self, size: int) -> str:
        """Format file size for display"""
        size_f = float(size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size_f < 1024.0:
                return f"{size_f:.1f}{unit}"
            size_f /= 1024.0
        return f"{size_f:.1f}TB"

    def _find_code_files(self, directory: Path) -> List[Path]:
        """Find all code files in directory"""
        code_files = []

        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.code_extensions:
                # Skip common non-code directories
                if any(
                    part in file_path.parts
                    for part in ["node_modules", "__pycache__", ".git", "dist", "build"]
                ):
                    continue
                code_files.append(file_path)

        # Sort by importance (main files first, then by name)
        def sort_key(path: Path) -> tuple:
            name = path.name.lower()
            # Prioritize main/index files
            if name in [
                "main.py",
                "index.js",
                "app.py",
                "server.py",
                "main.go",
                "main.rs",
            ]:
                return (0, name)
            elif name.startswith("index."):
                return (1, name)
            elif name.startswith("main."):
                return (2, name)
            else:
                return (3, name)

        code_files.sort(key=sort_key)
        return code_files

    def _detect_language(self, extension: str) -> str:
        """Detect programming language from extension"""
        return self.language_map.get(extension.lower(), "text")

    async def analyze_codebase(self, directory: Path) -> CodebaseAnalysis:
        """Analyze entire codebase"""

        analysis = CodebaseAnalysis(
            languages={},
            frameworks=[],
            entry_points=[],
            todo_count=0,
            test_coverage=False,
            file_stats={},
        )

        # Language detection
        language_stats: Dict[str, int] = defaultdict(int)
        file_extensions: Dict[str, int] = defaultdict(int)

        for file_path in directory.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                file_extensions[ext] += 1

                language = self._detect_language(ext)
                if language and language != "text":
                    language_stats[language] += 1

        analysis.languages = dict(language_stats)
        analysis.file_stats = dict(file_extensions)

        # Find entry points
        analysis.entry_points = self._find_entry_points(directory)

        # Detect frameworks
        analysis.frameworks = self._detect_frameworks(directory)

        # Find TODOs and FIXMEs
        analysis.todo_count = await self._find_todos(directory)

        # Check for tests
        test_files = self._find_test_files(directory)
        analysis.test_coverage = len(test_files) > 0

        return analysis

    def _find_entry_points(self, directory: Path) -> List[str]:
        """Find likely entry points in the codebase"""
        entry_points = []

        # Common entry point patterns
        patterns = [
            "main.py",
            "app.py",
            "server.py",
            "__main__.py",
            "index.js",
            "app.js",
            "server.js",
            "main.js",
            "main.go",
            "main.rs",
            "main.cpp",
            "main.c",
            "Main.java",
            "App.java",
            "index.php",
            "index.html",
        ]

        for pattern in patterns:
            for file_path in directory.rglob(pattern):
                if file_path.is_file():
                    entry_points.append(str(file_path.relative_to(directory)))

        return entry_points

    def _detect_frameworks(self, directory: Path) -> List[str]:
        """Detect frameworks and libraries used"""
        frameworks = []

        # Framework indicators
        indicators = {
            "package.json": ["React", "Vue", "Angular", "Express", "Next.js"],
            "requirements.txt": ["Django", "Flask", "FastAPI", "PyTorch", "TensorFlow"],
            "Cargo.toml": ["Tokio", "Actix", "Rocket"],
            "go.mod": ["Gin", "Echo", "Fiber"],
            "pom.xml": ["Spring", "Maven"],
            "build.gradle": ["Spring", "Gradle"],
            "composer.json": ["Laravel", "Symfony"],
            "Gemfile": ["Rails", "Sinatra"],
        }

        for indicator_file, possible_frameworks in indicators.items():
            file_path = directory / indicator_file
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="ignore").lower()
                for framework in possible_frameworks:
                    if framework.lower() in content:
                        frameworks.append(framework)

        # Check for specific framework files
        if (directory / "manage.py").exists():
            frameworks.append("Django")
        if (directory / "artisan").exists():
            frameworks.append("Laravel")
        if (directory / "next.config.js").exists():
            frameworks.append("Next.js")

        return list(set(frameworks))  # Remove duplicates

    async def _find_todos(self, directory: Path) -> int:
        """Count TODO and FIXME comments"""
        todo_count = 0

        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.code_extensions:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    # Count TODOs and FIXMEs
                    todo_count += content.upper().count("TODO")
                    todo_count += content.upper().count("FIXME")
                except Exception:
                    continue

        return todo_count

    def _find_test_files(self, directory: Path) -> List[Path]:
        """Find test files in the codebase"""
        test_files: List[Path] = []

        # Common test patterns
        test_patterns = [
            "test_*.py",
            "*_test.py",
            "*_test.go",
            "*.test.js",
            "*.spec.js",
            "*.test.ts",
            "*.spec.ts",
        ]

        for pattern in test_patterns:
            test_files.extend(directory.rglob(pattern))

        # Check test directories
        for test_dir_name in ["test", "tests", "__tests__", "spec"]:
            test_dir = directory / test_dir_name
            if test_dir.exists() and test_dir.is_dir():
                test_files.extend(test_dir.rglob("*"))

        return [f for f in test_files if f.is_file()]
