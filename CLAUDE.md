# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

MP3 파일을 오디오 핑거프린트로 식별하고, ID3 태그를 고친 뒤 `Artist/Album/NN - Title.mp3` 구조로 옮기는 Python CLI 도구다.
설치 방법과 사용법은 `README.md`에 있다.

- Python 3.10 이상이 필요하다. `scanner.py`가 `set[str] | None` 문법을 쓴다.
- 패키징 설정(pyproject 등)이 없다. 의존성은 `requirements.txt`에만 있다.
- 외부 프로그램 `fpcalc`(Chromaprint)가 필요하다.
- 테스트와 lint 설정이 없다.
- README, 주석, CLI 출력 문구는 한국어로 쓴다.

## 명령어

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m src.main --help
python -m src.main -s /path/to/mp3s --limit 5 -v   # dry-run이 기본값
```

- 저장소 루트에서 `python -m src.main`으로 실행해야 한다. `src/` 모듈이 상대 import를 쓰므로 `python src/main.py`는 `ImportError`가 난다.
- `config.yaml`(기본값)과 `organizer.log`는 현재 디렉터리 기준 경로다.
- 실제 실행에는 `.env`의 AcoustID API 키와 네트워크가 필요하다. 키 없이 확인할 수 있는 것은 `organizer`, `scanner`의 함수들이다.

## 구조

`main.process_file`이 파일 하나를 처리하는 파이프라인이다.

1. `fingerprint.lookup_acoustid` → `get_best_match`(score 0.5 미만은 버림) → `extract_recording_id`
2. `metadata.fetch_metadata_by_recording_id`(recording 조회) → `find_track_number`(release 조회로 트랙 번호 확보)
3. `tagger.update_tags`
4. `organizer.organize_file`. 1단계에서 실패하면 대신 `organizer.move_to_unmatched`

결과는 dict이고, `status`는 `success`, `unmatched`, `error` 중 하나다.
`unmatched`는 파일을 `_unmatched` 폴더로 옮긴다. `error`는 파일을 그대로 둔다.

설정은 `main.load_config`에서 합쳐진다. 순서는 `config.yaml` → `.env`(`acoustid_api_key`, `source_path`, `output_path` 키로 덮어씀) → CLI 옵션이다.

## 작업 규칙

- `dry_run` 값은 `tagger.update_tags`와 `organizer.move_file`까지 전달된다. 파일을 바꾸는 새 코드도 `dry_run`을 따라야 한다.
- 사용자의 실제 음악 폴더에 `--no-dry-run`을 실행하지 않는다. 확인은 임시 폴더의 복사본으로 한다.
- MusicBrainz에 요청을 보내기 전에는 `metadata._rate_limit()`를 호출한다. MusicBrainz는 초당 1회로 요청을 제한한다.

## 알아 둘 점 (현재 코드의 문제)

- AcoustID가 `"status": "error"`를 돌려주면(예: 잘못된 API 키), `lookup_acoustid`는 `None`을 반환한다. 그 결과 파일이 `unmatched`로 처리되어 `_unmatched`로 이동한다. pyacoustid는 HTTP 400 응답에도 예외를 던지지 않는다.
- API 키 검사는 `"YOUR_API_KEY_HERE"`와 비교한다. 하지만 `.env.example`의 값은 `your_api_key_here`라서 검사를 통과한다.
- 백업은 `update_tags`가 파일을 저장한 뒤 `move_file`에서 만든다. 따라서 백업에는 원본 태그가 아니라 수정된 태그가 들어 있다.
- 백업 파일은 파일명만으로 저장된다. 이름이 같은 파일이 있으면 덮어쓴다. `move_to_unmatched`는 백업을 만들지 않는다.
- `_cleanup_empty_folders`는 스캔 기준 폴더에서 멈추지 않는다. 소스 폴더가 비면 소스 폴더 자체도 지운다.
- `scanner.EXCLUDE_FOLDERS`는 `_unmatched`, `.backup`으로 고정되어 있다. `config.yaml`의 `unmatched_folder` 값을 따르지 않는다.
- `config.yaml`의 `sanitize_filenames`, `duplicate_action`은 어떤 코드도 읽지 않는다. 특수문자는 항상 지우고, 중복 파일명에는 항상 번호를 붙인다.
- `config.yaml`에 `options` 항목이 없으면 `--dry-run`, `--no-dry-run`에서 `KeyError`가 난다.
- `TrackMetadata.genre`를 채우는 코드가 없다. 그래서 장르 태그(TCON)는 쓰이지 않는다.
- `metadata.py`의 MusicBrainz user agent URL이 `https://github.com/example/mp3-auto-organizer`로 되어 있다.
