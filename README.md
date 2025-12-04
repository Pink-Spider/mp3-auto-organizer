# MP3 Auto Organizer

오디오 핑거프린팅을 사용하여 MP3 파일의 메타데이터를 자동으로 인식하고, 태그 업데이트 및 폴더/파일명 정리를 수행하는 도구입니다.

## 주요 기능

- **오디오 핑거프린팅**: AcoustID + Chromaprint를 사용하여 음악 파일 자동 식별
- **메타데이터 자동 수집**: MusicBrainz에서 title, artist, album, track number 등 조회
- **ID3 태그 업데이트**: 수집된 메타데이터로 MP3 태그 자동 업데이트
- **파일 자동 정리**: `Artist/Album/01 - Title.mp3` 형식으로 폴더 구조 및 파일명 정리
- **NAS 지원**: SMB/VPN으로 마운트된 네트워크 드라이브 사용 가능

## 설치

### 1. 사전 요구사항

```bash
# Chromaprint 설치 (macOS)
brew install chromaprint

# fpcalc 설치 확인
fpcalc -version
```

### 2. Python 의존성 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. API 키 발급

[AcoustID](https://acoustid.org/new-application)에서 무료 API 키를 발급받으세요.

### 4. 환경 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 설정:

```bash
ACOUSTID_API_KEY=your_api_key_here
SOURCE_PATH=/Volumes/Music
```

## 사용법

```bash
# 가상환경 활성화
source .venv/bin/activate

# dry-run 모드로 미리보기 (기본값, 실제 변경 없음)
python -m src.main

# 실제로 변경 적용
python -m src.main --no-dry-run

# 특정 경로 지정
python -m src.main -s /path/to/mp3s

# 테스트 (5개 파일만 처리)
python -m src.main --limit 5 -v

# 상세 출력
python -m src.main -v
```

### CLI 옵션

| 옵션 | 설명 |
|------|------|
| `-s`, `--source` | 스캔할 소스 경로 |
| `--dry-run` | 실제 변경 없이 미리보기만 |
| `--no-dry-run` | 실제로 변경 적용 |
| `-v`, `--verbose` | 상세 출력 |
| `--limit N` | 최대 N개 파일만 처리 (테스트용) |
| `-c`, `--config` | 설정 파일 경로 (기본: config.yaml) |

## 처리 흐름

```
1. MP3 파일 스캔
       ↓
2. 오디오 핑거프린팅 (Chromaprint)
       ↓
3. AcoustID API로 곡 식별
       ↓
4. MusicBrainz에서 메타데이터 조회
       ↓
5. ID3 태그 업데이트
       ↓
6. 폴더/파일명 정리
```

## 정리 결과 예시

**Before:**
```
/Music/
  ├── track01.mp3
  ├── unknown.mp3
  └── 노래모음/
      └── song.mp3
```

**After:**
```
/Music/
  ├── BTS/
  │   └── Map of the Soul - 7/
  │       └── 01 - Black Swan.mp3
  ├── IU/
  │   └── LILAC/
  │       └── 03 - Coin.mp3
  └── _unmatched/
      └── unknown.mp3
```

## 업데이트되는 ID3 태그

| 태그 | 설명 |
|------|------|
| TIT2 | Title (곡 제목) |
| TPE1 | Artist (아티스트) |
| TPE2 | Album Artist (앨범 아티스트) |
| TALB | Album (앨범명) |
| TRCK | Track Number (트랙 번호) |
| TPOS | Disc Number (디스크 번호) |
| TDRC | Year (발매년도) |
| TXXX | MusicBrainz ID (내부 참조용) |

## 인식 실패 처리

MusicBrainz/AcoustID 데이터베이스에 없는 파일은 `_unmatched` 폴더로 이동됩니다.
**원본 폴더 구조가 유지됩니다.**

| 상황 | 처리 |
|------|------|
| 핑거프린트 매칭 실패 | `_unmatched` 폴더로 이동 |
| 매칭 신뢰도 50% 미만 | `_unmatched` 폴더로 이동 |
| MusicBrainz에 정보 없음 | `_unmatched` 폴더로 이동 |

```
# 원본 구조
/Music/
  └── 노래모음/
      └── unknown.mp3

# 처리 후
/Music/
  └── _unmatched/
      └── 노래모음/       ← 원본 폴더 구조 유지
          └── unknown.mp3
```

### 인식률 참고

| 유형 | 예상 인식률 |
|------|------------|
| 유명 곡 (빌보드, 멜론 차트 등) | ~100% |
| 인디/마이너 앨범 | 70~80% |
| 직접 녹음/편집 파일 | 인식 불가 |
| 라이브 버전/리믹스 | 원곡과 다르면 인식 실패 가능 |

`_unmatched` 폴더의 파일들은 수동으로 태그를 편집하거나, 기존 태그가 있다면 그대로 유지됩니다.

## 설정 파일

`config.yaml`에서 상세 옵션을 설정할 수 있습니다:

```yaml
# 폴더 구조 템플릿
# 사용 가능한 변수: {artist}, {album}, {year}
folder_template: "{artist}/{album}"

# 파일명 템플릿
# 사용 가능한 변수: {track:02d}, {title}, {artist}, {album}
filename_template: "{track:02d} - {title}"

options:
  dry_run: true           # 미리보기 모드
  backup: true            # 원본 파일 백업
  unmatched_folder: "_unmatched"  # 인식 실패 파일 폴더
```

## 프로젝트 구조

```
mp3-auto-organizer/
├── src/
│   ├── main.py          # CLI 진입점
│   ├── scanner.py       # MP3 파일 탐색
│   ├── fingerprint.py   # AcoustID 핑거프린팅
│   ├── metadata.py      # MusicBrainz 메타데이터 조회
│   ├── tagger.py        # ID3 태그 업데이트
│   └── organizer.py     # 폴더/파일명 정리
├── config.yaml          # 설정 파일
├── .env                 # 환경 변수 (API 키 등)
└── requirements.txt     # Python 의존성
```

## 주의사항

- **dry-run 모드**: 기본값은 `dry_run: true`로, 실제 변경 없이 미리보기만 합니다
- **백업**: `backup: true` 설정 시 원본 파일을 `.backup` 폴더에 복사합니다
- **네트워크 드라이브**: VPN/SMB로 마운트된 경로 사용 시 속도가 느릴 수 있습니다
- **API 제한**: MusicBrainz는 초당 1회 요청 제한이 있어 자동으로 rate limiting을 적용합니다

## 라이선스

MIT License
