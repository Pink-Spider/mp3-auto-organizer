"""폴더 구조 및 파일명 정리 모듈"""

import re
import shutil
from pathlib import Path
from typing import Optional

from .metadata import TrackMetadata


class OrganizerError(Exception):
    """파일 정리 관련 에러"""

    pass


# 파일명에 사용할 수 없는 문자 (Windows 호환성)
INVALID_CHARS = r'[<>:"/\\|?*]'
INVALID_CHARS_PATTERN = re.compile(INVALID_CHARS)


def sanitize_filename(name: str) -> str:
    """
    파일명에서 사용할 수 없는 문자를 제거합니다.

    Args:
        name: 원본 이름

    Returns:
        정리된 이름
    """
    if not name:
        return "Unknown"

    # 유효하지 않은 문자 제거
    sanitized = INVALID_CHARS_PATTERN.sub("", name)

    # 앞뒤 공백 및 점 제거
    sanitized = sanitized.strip(" .")

    # 연속된 공백을 하나로
    sanitized = re.sub(r"\s+", " ", sanitized)

    # 너무 긴 이름 자르기 (255바이트 제한 고려)
    if len(sanitized.encode("utf-8")) > 200:
        while len(sanitized.encode("utf-8")) > 200:
            sanitized = sanitized[:-1]
        sanitized = sanitized.strip()

    return sanitized or "Unknown"


def build_folder_path(
    base_path: Path, metadata: TrackMetadata, template: str = "{artist}/{album}"
) -> Path:
    """
    메타데이터를 기반으로 폴더 경로를 생성합니다.

    Args:
        base_path: 기본 경로
        metadata: 트랙 메타데이터
        template: 폴더 구조 템플릿

    Returns:
        생성할 폴더 경로
    """
    # 템플릿 변수 준비
    variables = {
        "artist": sanitize_filename(metadata.artist),
        "album": sanitize_filename(metadata.album),
        "album_artist": sanitize_filename(metadata.album_artist or metadata.artist),
        "year": str(metadata.year) if metadata.year else "Unknown Year",
    }

    # 템플릿 적용
    try:
        folder_structure = template.format(**variables)
    except KeyError as e:
        raise OrganizerError(f"잘못된 템플릿 변수: {e}")

    return base_path / folder_structure


def build_filename(
    metadata: TrackMetadata, template: str = "{track:02d} - {title}"
) -> str:
    """
    메타데이터를 기반으로 파일명을 생성합니다.

    Args:
        metadata: 트랙 메타데이터
        template: 파일명 템플릿

    Returns:
        새 파일명 (.mp3 확장자 포함)
    """
    # 템플릿 변수 준비
    track_num = metadata.track_number or 0

    variables = {
        "track": track_num,
        "title": sanitize_filename(metadata.title),
        "artist": sanitize_filename(metadata.artist),
        "album": sanitize_filename(metadata.album),
    }

    # 템플릿 적용
    try:
        # track:02d 같은 포맷 문자열 처리
        filename = template.format(**variables)
    except (KeyError, ValueError):
        # 포맷 실패 시 기본 형식 사용
        if track_num:
            filename = f"{track_num:02d} - {sanitize_filename(metadata.title)}"
        else:
            filename = sanitize_filename(metadata.title)

    return f"{filename}.mp3"


def get_new_path(
    base_path: Path,
    metadata: TrackMetadata,
    folder_template: str = "{artist}/{album}",
    filename_template: str = "{track:02d} - {title}",
) -> Path:
    """
    파일의 새 경로를 계산합니다.

    Args:
        base_path: 기본 출력 경로
        metadata: 트랙 메타데이터
        folder_template: 폴더 구조 템플릿
        filename_template: 파일명 템플릿

    Returns:
        새 파일 전체 경로
    """
    folder_path = build_folder_path(base_path, metadata, folder_template)
    filename = build_filename(metadata, filename_template)
    return folder_path / filename


def move_file(
    source: Path,
    destination: Path,
    dry_run: bool = False,
    backup_path: Optional[Path] = None,
) -> dict:
    """
    파일을 새 위치로 이동합니다.

    Args:
        source: 원본 파일 경로
        destination: 대상 경로
        dry_run: True면 실제 이동하지 않음
        backup_path: 백업 경로 (지정 시 원본 복사)

    Returns:
        이동 정보 딕셔너리
    """
    result = {
        "source": str(source),
        "destination": str(destination),
        "moved": False,
        "backed_up": False,
    }

    if source == destination:
        result["skipped"] = True
        result["reason"] = "same_path"
        return result

    if not dry_run:
        # 대상 폴더 생성
        destination.parent.mkdir(parents=True, exist_ok=True)

        # 중복 파일 처리
        if destination.exists():
            destination = _handle_duplicate(destination)
            result["destination"] = str(destination)

        # 백업
        if backup_path:
            backup_file = backup_path / source.name
            backup_path.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup_file)
            result["backed_up"] = True
            result["backup_location"] = str(backup_file)

        # 이동
        shutil.move(str(source), str(destination))
        result["moved"] = True

        # 원본 폴더가 비었으면 삭제
        _cleanup_empty_folders(source.parent)

    return result


def _handle_duplicate(path: Path) -> Path:
    """중복 파일명 처리 - 번호 붙이기"""
    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    counter = 1
    new_path = path
    while new_path.exists():
        new_path = parent / f"{stem} ({counter}){suffix}"
        counter += 1

    return new_path


def _cleanup_empty_folders(folder: Path) -> None:
    """빈 폴더를 재귀적으로 삭제합니다."""
    try:
        while folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    except (OSError, PermissionError):
        pass


def organize_file(
    file_path: Path,
    metadata: TrackMetadata,
    output_path: Path,
    folder_template: str = "{artist}/{album}",
    filename_template: str = "{track:02d} - {title}",
    dry_run: bool = False,
    backup_path: Optional[Path] = None,
) -> dict:
    """
    파일을 메타데이터 기반으로 정리합니다.

    Args:
        file_path: 원본 파일 경로
        metadata: 트랙 메타데이터
        output_path: 출력 기본 경로
        folder_template: 폴더 구조 템플릿
        filename_template: 파일명 템플릿
        dry_run: True면 실제 변경 없음
        backup_path: 백업 경로

    Returns:
        정리 결과 딕셔너리
    """
    new_path = get_new_path(output_path, metadata, folder_template, filename_template)

    return move_file(
        source=file_path,
        destination=new_path,
        dry_run=dry_run,
        backup_path=backup_path,
    )


def move_to_unmatched(
    file_path: Path,
    source_base_path: Path,
    output_path: Path,
    unmatched_folder: str = "_unmatched",
    dry_run: bool = False,
) -> dict:
    """
    인식 실패한 파일을 unmatched 폴더로 이동합니다.
    원본 폴더 구조를 유지합니다.

    Args:
        file_path: 원본 파일 경로
        source_base_path: 스캔 시작 기준 경로
        output_path: 출력 기본 경로
        unmatched_folder: unmatched 폴더명
        dry_run: True면 실제 이동하지 않음
    """
    # 원본 폴더 구조 유지
    try:
        relative_path = file_path.relative_to(source_base_path)
    except ValueError:
        # 상대 경로 계산 실패 시 파일명만 사용
        relative_path = Path(file_path.name)

    destination = output_path / unmatched_folder / relative_path

    return move_file(
        source=file_path,
        destination=destination,
        dry_run=dry_run,
    )
