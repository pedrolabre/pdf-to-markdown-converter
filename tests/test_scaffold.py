from pathlib import Path
import pdf_to_markdown_converter


def test_package_version() -> None:
    assert pdf_to_markdown_converter.__version__ == "0.1.0"


def test_package_structure(project_root: Path) -> None:
    assert (project_root / "pyproject.toml").is_file()
    assert (project_root / "src" / "pdf_to_markdown_converter" / "__init__.py").is_file()
