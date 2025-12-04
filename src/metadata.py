"""MusicBrainz 메타데이터 조회 모듈"""

import time
from dataclasses import dataclass
from typing import Optional

import musicbrainzngs

# MusicBrainz API 설정
musicbrainzngs.set_useragent(
    "MP3AutoOrganizer",
    "1.0.0",
    "https://github.com/example/mp3-auto-organizer",
)

# Rate limiting을 위한 마지막 요청 시간
_last_request_time = 0.0
_MIN_REQUEST_INTERVAL = 1.0  # MusicBrainz는 초당 1회 제한


def _rate_limit():
    """MusicBrainz API rate limiting 준수"""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


@dataclass
class TrackMetadata:
    """트랙 메타데이터"""

    title: str
    artist: str
    album: str
    album_artist: Optional[str] = None
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    disc_number: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    musicbrainz_recording_id: Optional[str] = None
    musicbrainz_release_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "track_number": self.track_number,
            "total_tracks": self.total_tracks,
            "disc_number": self.disc_number,
            "year": self.year,
            "genre": self.genre,
            "musicbrainz_recording_id": self.musicbrainz_recording_id,
            "musicbrainz_release_id": self.musicbrainz_release_id,
        }


def fetch_metadata_by_recording_id(recording_id: str) -> Optional[TrackMetadata]:
    """
    MusicBrainz recording ID로 메타데이터를 조회합니다.

    Args:
        recording_id: MusicBrainz recording ID

    Returns:
        TrackMetadata 또는 None
    """
    _rate_limit()

    try:
        result = musicbrainzngs.get_recording_by_id(
            recording_id,
            includes=["artists", "releases", "release-groups"],
        )
    except musicbrainzngs.WebServiceError:
        return None

    recording = result.get("recording", {})

    # 기본 정보 추출
    title = recording.get("title", "Unknown Title")

    # 아티스트 정보
    artist_credit = recording.get("artist-credit", [])
    artist = _extract_artist_name(artist_credit)

    # 릴리스(앨범) 정보 - 가장 적합한 것 선택
    releases = recording.get("release-list", [])
    release_info = _select_best_release(releases)

    album = release_info.get("album", "Unknown Album")
    album_artist = release_info.get("album_artist")
    track_number = release_info.get("track_number")
    total_tracks = release_info.get("total_tracks")
    disc_number = release_info.get("disc_number")
    year = release_info.get("year")
    release_id = release_info.get("release_id")

    return TrackMetadata(
        title=title,
        artist=artist,
        album=album,
        album_artist=album_artist,
        track_number=track_number,
        total_tracks=total_tracks,
        disc_number=disc_number,
        year=year,
        musicbrainz_recording_id=recording_id,
        musicbrainz_release_id=release_id,
    )


def _extract_artist_name(artist_credit: list) -> str:
    """아티스트 크레딧에서 아티스트 이름을 추출합니다."""
    if not artist_credit:
        return "Unknown Artist"

    names = []
    for credit in artist_credit:
        if isinstance(credit, dict):
            artist = credit.get("artist", {})
            name = artist.get("name", "")
            if name:
                names.append(name)
            # joinphrase 처리 (feat., &, etc.)
            joinphrase = credit.get("joinphrase", "")
            if joinphrase:
                names.append(joinphrase)
        elif isinstance(credit, str):
            names.append(credit)

    return "".join(names).strip() if names else "Unknown Artist"


def _select_best_release(releases: list) -> dict:
    """
    가장 적합한 릴리스를 선택합니다.
    우선순위: Official Album > Single > Compilation
    """
    if not releases:
        return {"album": "Unknown Album"}

    # 점수 기반 정렬
    def score_release(release):
        score = 0
        status = release.get("status", "").lower()
        release_group = release.get("release-group", {})
        primary_type = release_group.get("primary-type", "").lower()

        # 공식 릴리스 우선
        if status == "official":
            score += 100

        # 앨범 타입 우선순위
        if primary_type == "album":
            score += 50
        elif primary_type == "ep":
            score += 40
        elif primary_type == "single":
            score += 30

        # 컴필레이션이 아닌 것 우선
        secondary_types = release_group.get("secondary-type-list", [])
        if "Compilation" not in secondary_types:
            score += 20

        return score

    best_release = max(releases, key=score_release)

    # 릴리스 정보 추출
    result = {
        "album": best_release.get("title", "Unknown Album"),
        "release_id": best_release.get("id"),
    }

    # 앨범 아티스트
    artist_credit = best_release.get("artist-credit", [])
    if artist_credit:
        result["album_artist"] = _extract_artist_name(artist_credit)

    # 발매년도
    date = best_release.get("date", "")
    if date and len(date) >= 4:
        try:
            result["year"] = int(date[:4])
        except ValueError:
            pass

    # 트랙 정보 (medium-list에서)
    medium_list = best_release.get("medium-list", [])
    if medium_list:
        for disc_idx, medium in enumerate(medium_list, 1):
            track_list = medium.get("track-list", [])
            result["total_tracks"] = medium.get("track-count")
            if len(medium_list) > 1:
                result["disc_number"] = disc_idx
            # 트랙 번호는 여기서 직접 얻기 어려움 (recording 기준이 아니라 release 기준)

    return result


def fetch_release_tracks(release_id: str) -> Optional[list[dict]]:
    """릴리스의 전체 트랙 리스트를 가져옵니다."""
    _rate_limit()

    try:
        result = musicbrainzngs.get_release_by_id(
            release_id,
            includes=["recordings", "artists"],
        )
    except musicbrainzngs.WebServiceError:
        return None

    release = result.get("release", {})
    tracks = []

    for medium in release.get("medium-list", []):
        disc_number = medium.get("position", 1)
        for track in medium.get("track-list", []):
            recording = track.get("recording", {})
            tracks.append(
                {
                    "recording_id": recording.get("id"),
                    "title": recording.get("title"),
                    "track_number": int(track.get("position", 0)),
                    "disc_number": disc_number,
                }
            )

    return tracks


def find_track_number(
    recording_id: str, release_id: str
) -> Optional[tuple[int, int, int]]:
    """
    특정 recording이 release에서 몇 번 트랙인지 찾습니다.

    Returns:
        (track_number, total_tracks, disc_number) 또는 None
    """
    tracks = fetch_release_tracks(release_id)
    if not tracks:
        return None

    for track in tracks:
        if track["recording_id"] == recording_id:
            # 해당 디스크의 총 트랙 수 계산
            disc_tracks = [t for t in tracks if t["disc_number"] == track["disc_number"]]
            return (
                track["track_number"],
                len(disc_tracks),
                track["disc_number"],
            )

    return None
