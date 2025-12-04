"""MP3 파일 스캐너 모듈"""

import os
from pathlib import Path
from typing import Generator

# 스캔에서 제외할 폴더명
EXCLUDE_FOLDERS = {"_unmatched", ".backup"}


def _should_exclude(file_path: Path) -> bool:
    """제외할 폴더에 있는 파일인지 확인합니다."""
    for part in file_path.parts:
        if part in EXCLUDE_FOLDERS:
            return True
    return False


def scan_mp3_files(source_path: str, exclude_folders: set[str] | None = None) -> Generator[Path, None, None]:
    """
    지정된 경로에서 모든 MP3 파일을 재귀적으로 탐색합니다.

    Args:
        source_path: 스캔할 디렉토리 경로
        exclude_folders: 제외할 폴더명 집합

    Yields:
        MP3 파일의 Path 객체
    """
    source = Path(source_path)
    excludes = exclude_folders or EXCLUDE_FOLDERS

    if not source.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {source_path}")

    if not source.is_dir():
        raise NotADirectoryError(f"디렉토리가 아닙니다: {source_path}")

    seen = set()  # 중복 방지 (대소문자 확장자)

    for file_path in source.rglob("*.mp3"):
        if file_path.is_file() and not _should_exclude(file_path):
            if file_path not in seen:
                seen.add(file_path)
                yield file_path

    # 대문자 확장자도 처리
    for file_path in source.rglob("*.MP3"):
        if file_path.is_file() and not _should_exclude(file_path):
            if file_path not in seen:
                seen.add(file_path)
                yield file_path


def count_mp3_files(source_path: str) -> int:
    """MP3 파일 개수를 반환합니다."""
    return sum(1 for _ in scan_mp3_files(source_path))


def get_file_info(file_path: Path) -> dict:
    """파일의 기본 정보를 반환합니다."""
    stat = file_path.stat()
    return {
        "path": str(file_path),
        "name": file_path.name,
        "size": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
    }
