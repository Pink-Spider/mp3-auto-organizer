"""AcoustID 오디오 핑거프린팅 모듈"""

import subprocess
from pathlib import Path
from typing import Optional

import acoustid


class FingerprintError(Exception):
    """핑거프린팅 관련 에러"""

    pass


def check_fpcalc_installed() -> bool:
    """fpcalc(Chromaprint)가 설치되어 있는지 확인합니다."""
    try:
        result = subprocess.run(
            ["fpcalc", "-version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_fingerprint(file_path: Path) -> tuple[int, str]:
    """
    오디오 파일의 핑거프린트를 생성합니다.

    Args:
        file_path: MP3 파일 경로

    Returns:
        (duration, fingerprint) 튜플

    Raises:
        FingerprintError: 핑거프린트 생성 실패 시
    """
    try:
        duration, fingerprint = acoustid.fingerprint_file(str(file_path))
        return duration, fingerprint
    except acoustid.FingerprintGenerationError as e:
        raise FingerprintError(f"핑거프린트 생성 실패: {file_path} - {e}")


def lookup_acoustid(
    api_key: str, file_path: Path
) -> Optional[list[dict]]:
    """
    AcoustID API로 오디오 파일을 조회합니다.

    Args:
        api_key: AcoustID API 키
        file_path: MP3 파일 경로

    Returns:
        매칭된 결과 리스트 또는 None
    """
    try:
        results = acoustid.match(
            api_key,
            str(file_path),
            meta="recordings releasegroups",
            parse=False,
        )

        if results.get("status") != "ok":
            return None

        matches = results.get("results", [])
        if not matches:
            return None

        return matches

    except acoustid.FingerprintGenerationError:
        return None
    except acoustid.WebServiceError as e:
        raise FingerprintError(f"AcoustID API 오류: {e}")


def get_best_match(matches: list[dict]) -> Optional[dict]:
    """
    AcoustID 결과에서 가장 신뢰도 높은 매칭을 반환합니다.

    Args:
        matches: AcoustID 매칭 결과 리스트

    Returns:
        가장 좋은 매칭 결과 또는 None
    """
    if not matches:
        return None

    # score가 가장 높은 결과 선택
    best = max(matches, key=lambda x: x.get("score", 0))

    if best.get("score", 0) < 0.5:
        return None

    return best


def extract_recording_id(match: dict) -> Optional[str]:
    """매칭 결과에서 MusicBrainz recording ID를 추출합니다."""
    recordings = match.get("recordings", [])
    if not recordings:
        return None

    # 첫 번째 recording의 ID 반환
    return recordings[0].get("id")
