"""Tests for the FileHandler document branch."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.features.file_handler import FileHandler
from src.config import create_test_config


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def file_handler(tmp_dir):
    settings = create_test_config(approved_directory=str(tmp_dir))
    security = MagicMock()
    return FileHandler(settings, security)


@pytest.mark.parametrize(
    "filename",
    [
        "report.pdf",
        "contract.docx",
        "budget.xlsx",
        "deck.pptx",
        "notes.odt",
        "letter.rtf",
    ],
)
def test_detect_file_type_binary_document_formats_return_document(
    file_handler, filename
):
    assert file_handler._detect_file_type(Path(filename)) == "document"


def test_detect_file_type_unknown_binary_stays_binary(file_handler, tmp_dir):
    # A file with unknown extension + non-UTF-8 bytes should not become "document"
    # — only whitelisted extensions in `document_extensions` do.
    blob = tmp_dir / "mystery.blob"
    blob.write_bytes(b"\xff\xfe\x00\x01binarydata")
    assert file_handler._detect_file_type(blob) == "binary"


def test_detect_file_type_csv_goes_through_text_branch(file_handler, tmp_dir):
    """CSV and similar UTF-8 tabular formats aren't in `document_extensions` —
    they fall through to the text branch (inline content in the prompt)."""
    csv_file = tmp_dir / "data.csv"
    csv_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert file_handler._detect_file_type(csv_file) == "text"


async def test_process_document_file_copies_and_builds_prompt(file_handler, tmp_dir):
    """_process_document_file copies PDF to <persist_root>/.uploads/ with a
    timestamp prefix, leaves it in place, and embeds the absolute path in
    the returned prompt.
    """
    source = tmp_dir / "src_ticket.pdf"
    source.write_bytes(b"%PDF-1.4\nSMOKE-TOKEN-42\n%%EOF\n")

    result = await file_handler._process_document_file(
        source,
        context="please summarize",
        persist_root=tmp_dir,
        original_name="ticket.pdf",
    )

    uploads_dir = tmp_dir / ".uploads"
    saved_files = list(uploads_dir.glob("*-ticket.pdf"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == source.read_bytes()

    assert result.type == "document"
    assert str(saved_files[0]) in result.prompt
    assert "please summarize" in result.prompt
    assert result.metadata["saved_path"] == str(saved_files[0])
    assert result.metadata["original_name"] == "ticket.pdf"
    assert result.metadata["size"] == source.stat().st_size


async def test_handle_document_upload_pdf_end_to_end(file_handler, tmp_dir):
    """handle_document_upload routes .pdf to the document branch and persists
    the file into current_dir/.uploads/."""
    pdf_bytes = b"%PDF-1.4\nSMOKE\n%%EOF\n"

    async def fake_download(target_path):
        Path(target_path).write_bytes(pdf_bytes)

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock(side_effect=fake_download)

    document = MagicMock()
    document.file_name = "ticket.pdf"
    document.get_file = AsyncMock(return_value=tg_file)

    # Use a subdirectory as current_dir to verify the handler honours it over
    # the default approved_directory.
    current_dir = tmp_dir / "project"
    current_dir.mkdir()

    result = await file_handler.handle_document_upload(
        document,
        user_id=1,
        context="summarize",
        current_dir=current_dir,
    )

    uploads_dir = current_dir / ".uploads"
    saved_files = list(uploads_dir.glob("*-ticket.pdf"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == pdf_bytes
    assert result.type == "document"
    assert str(saved_files[0]) in result.prompt


async def test_handle_document_upload_defaults_to_approved_directory(
    file_handler, tmp_dir
):
    """Without explicit current_dir, document branch falls back to
    approved_directory — backward-compatible behaviour."""
    pdf_bytes = b"%PDF-1.4\nfallback\n%%EOF\n"

    async def fake_download(target_path):
        Path(target_path).write_bytes(pdf_bytes)

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock(side_effect=fake_download)

    document = MagicMock()
    document.file_name = "fallback.pdf"
    document.get_file = AsyncMock(return_value=tg_file)

    result = await file_handler.handle_document_upload(document, user_id=1, context="")

    saved_files = list((tmp_dir / ".uploads").glob("*-fallback.pdf"))
    assert len(saved_files) == 1
    assert result.type == "document"
