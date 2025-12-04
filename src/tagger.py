"""ID3 태그 업데이트 모듈"""

from pathlib import Path
from typing import Optional

from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    TIT2,  # Title
    TPE1,  # Artist
    TPE2,  # Album Artist
    TALB,  # Album
    TRCK,  # Track Number
    TPOS,  # Disc Number
    TYER,  # Year (ID3v2.3)
    TDRC,  # Recording Date (ID3v2.4)
    TCON,  # Genre
    TXXX,  # User-defined text
)
from mutagen.mp3 import MP3

from .metadata import TrackMetadata


class TaggerError(Exception):
    """태그 업데이트 관련 에러"""

    pass


def read_current_tags(file_path: Path) -> dict:
    """
    현재 MP3 파일의 ID3 태그를 읽습니다.

    Args:
        file_path: MP3 파일 경로

    Returns:
        현재 태그 정보 딕셔너리
    """
    try:
        audio = MP3(str(file_path))
    except Exception as e:
        raise TaggerError(f"파일을 읽을 수 없습니다: {file_path} - {e}")

    tags = {}

    if audio.tags is None:
        return tags

    # 주요 태그 읽기
    tag_mapping = {
        "TIT2": "title",
        "TPE1": "artist",
        "TPE2": "album_artist",
        "TALB": "album",
        "TRCK": "track",
        "TPOS": "disc",
        "TYER": "year",
        "TDRC": "year",
        "TCON": "genre",
    }

    for tag_id, key in tag_mapping.items():
        if tag_id in audio.tags:
            value = str(audio.tags[tag_id].text[0])
            if key == "year" and value:
                try:
                    tags[key] = int(str(value)[:4])
                except ValueError:
                    tags[key] = value
            else:
                tags[key] = value

    return tags


def update_tags(
    file_path: Path, metadata: TrackMetadata, dry_run: bool = False
) -> dict:
    """
    MP3 파일의 ID3 태그를 업데이트합니다.

    Args:
        file_path: MP3 파일 경로
        metadata: 적용할 메타데이터
        dry_run: True면 실제 저장하지 않음

    Returns:
        변경 사항 딕셔너리
    """
    try:
        audio = MP3(str(file_path))
    except Exception as e:
        raise TaggerError(f"파일을 읽을 수 없습니다: {file_path} - {e}")

    # ID3 태그가 없으면 생성
    try:
        tags = audio.tags or ID3()
    except ID3NoHeaderError:
        tags = ID3()

    changes = {}
    old_tags = read_current_tags(file_path)

    # Title
    if metadata.title:
        old_val = old_tags.get("title", "")
        if old_val != metadata.title:
            tags["TIT2"] = TIT2(encoding=3, text=metadata.title)
            changes["title"] = {"old": old_val, "new": metadata.title}

    # Artist
    if metadata.artist:
        old_val = old_tags.get("artist", "")
        if old_val != metadata.artist:
            tags["TPE1"] = TPE1(encoding=3, text=metadata.artist)
            changes["artist"] = {"old": old_val, "new": metadata.artist}

    # Album Artist
    if metadata.album_artist:
        old_val = old_tags.get("album_artist", "")
        if old_val != metadata.album_artist:
            tags["TPE2"] = TPE2(encoding=3, text=metadata.album_artist)
            changes["album_artist"] = {"old": old_val, "new": metadata.album_artist}

    # Album
    if metadata.album:
        old_val = old_tags.get("album", "")
        if old_val != metadata.album:
            tags["TALB"] = TALB(encoding=3, text=metadata.album)
            changes["album"] = {"old": old_val, "new": metadata.album}

    # Track Number
    if metadata.track_number:
        track_str = str(metadata.track_number)
        if metadata.total_tracks:
            track_str = f"{metadata.track_number}/{metadata.total_tracks}"
        old_val = old_tags.get("track", "")
        if old_val != track_str:
            tags["TRCK"] = TRCK(encoding=3, text=track_str)
            changes["track"] = {"old": old_val, "new": track_str}

    # Disc Number
    if metadata.disc_number:
        old_val = old_tags.get("disc", "")
        disc_str = str(metadata.disc_number)
        if old_val != disc_str:
            tags["TPOS"] = TPOS(encoding=3, text=disc_str)
            changes["disc"] = {"old": old_val, "new": disc_str}

    # Year
    if metadata.year:
        old_val = old_tags.get("year")
        if old_val != metadata.year:
            tags["TDRC"] = TDRC(encoding=3, text=str(metadata.year))
            changes["year"] = {"old": old_val, "new": metadata.year}

    # Genre
    if metadata.genre:
        old_val = old_tags.get("genre", "")
        if old_val != metadata.genre:
            tags["TCON"] = TCON(encoding=3, text=metadata.genre)
            changes["genre"] = {"old": old_val, "new": metadata.genre}

    # MusicBrainz IDs (사용자 정의 태그)
    if metadata.musicbrainz_recording_id:
        tags["TXXX:MusicBrainz Recording Id"] = TXXX(
            encoding=3,
            desc="MusicBrainz Recording Id",
            text=metadata.musicbrainz_recording_id,
        )

    if metadata.musicbrainz_release_id:
        tags["TXXX:MusicBrainz Release Id"] = TXXX(
            encoding=3,
            desc="MusicBrainz Release Id",
            text=metadata.musicbrainz_release_id,
        )

    # 저장
    if changes and not dry_run:
        audio.tags = tags
        audio.save()

    return changes


def has_complete_tags(file_path: Path) -> bool:
    """파일이 기본 태그(title, artist, album)를 모두 가지고 있는지 확인합니다."""
    tags = read_current_tags(file_path)
    required = ["title", "artist", "album"]
    return all(tags.get(key) for key in required)
