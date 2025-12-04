#!/usr/bin/env python3
"""MP3 Auto Organizer - 스마트 MP3 메타데이터 및 파일 정리 도구"""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from .scanner import scan_mp3_files, count_mp3_files, get_file_info
from .fingerprint import (
    check_fpcalc_installed,
    lookup_acoustid,
    get_best_match,
    extract_recording_id,
    FingerprintError,
)
from .metadata import (
    TrackMetadata,
    fetch_metadata_by_recording_id,
    find_track_number,
)
from .tagger import update_tags, read_current_tags
from .organizer import organize_file, move_to_unmatched

console = Console()


def load_config(config_path: str = "config.yaml") -> dict:
    """설정 파일과 환경 변수를 로드합니다."""
    # .env 파일 로드
    load_dotenv()

    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]설정 파일을 찾을 수 없습니다: {config_path}[/red]")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # 환경 변수로 설정 덮어쓰기
    if os.getenv("ACOUSTID_API_KEY"):
        config["acoustid_api_key"] = os.getenv("ACOUSTID_API_KEY")
    if os.getenv("SOURCE_PATH"):
        config["source_path"] = os.getenv("SOURCE_PATH")
    if os.getenv("OUTPUT_PATH"):
        config["output_path"] = os.getenv("OUTPUT_PATH")

    return config


def setup_logging(log_file: str) -> logging.Logger:
    """로깅을 설정합니다."""
    logger = logging.getLogger("mp3-organizer")
    logger.setLevel(logging.INFO)

    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(file_handler)

    return logger


def process_file(
    file_path: Path,
    config: dict,
    logger: logging.Logger,
    dry_run: bool = True,
) -> dict:
    """
    단일 MP3 파일을 처리합니다.

    Returns:
        처리 결과 딕셔너리
    """
    result = {
        "file": str(file_path),
        "status": "pending",
        "metadata": None,
        "tag_changes": {},
        "file_changes": {},
    }

    api_key = config.get("acoustid_api_key", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        result["status"] = "error"
        result["error"] = "AcoustID API 키가 설정되지 않았습니다"
        return result

    # 1. AcoustID로 곡 식별
    try:
        matches = lookup_acoustid(api_key, file_path)
    except FingerprintError as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"핑거프린팅 실패: {file_path} - {e}")
        return result

    if not matches:
        result["status"] = "unmatched"
        logger.warning(f"매칭 실패: {file_path}")
        return result

    # 2. 가장 좋은 매칭 선택
    best_match = get_best_match(matches)
    if not best_match:
        result["status"] = "unmatched"
        result["error"] = "신뢰도 높은 매칭을 찾지 못했습니다"
        logger.warning(f"낮은 신뢰도 매칭: {file_path}")
        return result

    recording_id = extract_recording_id(best_match)
    if not recording_id:
        result["status"] = "unmatched"
        result["error"] = "Recording ID를 찾지 못했습니다"
        return result

    result["acoustid_score"] = best_match.get("score", 0)

    # 3. MusicBrainz에서 메타데이터 가져오기
    metadata = fetch_metadata_by_recording_id(recording_id)
    if not metadata:
        result["status"] = "error"
        result["error"] = "MusicBrainz에서 메타데이터를 가져오지 못했습니다"
        return result

    # 4. 트랙 번호 찾기 (release에서)
    if metadata.musicbrainz_release_id and not metadata.track_number:
        track_info = find_track_number(
            recording_id, metadata.musicbrainz_release_id
        )
        if track_info:
            metadata.track_number = track_info[0]
            metadata.total_tracks = track_info[1]
            metadata.disc_number = track_info[2]

    result["metadata"] = metadata.to_dict()

    # 5. ID3 태그 업데이트
    try:
        tag_changes = update_tags(file_path, metadata, dry_run=dry_run)
        result["tag_changes"] = tag_changes
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"태그 업데이트 실패: {e}"
        logger.error(f"태그 업데이트 실패: {file_path} - {e}")
        return result

    # 6. 파일 정리 (폴더/파일명)
    output_path = Path(config.get("output_path") or config.get("source_path"))
    backup_path = None
    if config.get("options", {}).get("backup"):
        backup_dir = config.get("options", {}).get("backup_path")
        if backup_dir:
            backup_path = Path(backup_dir)
        else:
            backup_path = Path(config.get("source_path")) / ".backup"

    try:
        file_changes = organize_file(
            file_path=file_path,
            metadata=metadata,
            output_path=output_path,
            folder_template=config.get("folder_template", "{artist}/{album}"),
            filename_template=config.get("filename_template", "{track:02d} - {title}"),
            dry_run=dry_run,
            backup_path=backup_path,
        )
        result["file_changes"] = file_changes
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"파일 정리 실패: {e}"
        logger.error(f"파일 정리 실패: {file_path} - {e}")
        return result

    result["status"] = "success"
    logger.info(
        f"처리 완료: {file_path} -> {metadata.artist} - {metadata.title}"
    )

    return result


def print_summary(results: list[dict], dry_run: bool):
    """처리 결과 요약을 출력합니다."""
    success = sum(1 for r in results if r["status"] == "success")
    unmatched = sum(1 for r in results if r["status"] == "unmatched")
    errors = sum(1 for r in results if r["status"] == "error")

    table = Table(title="처리 결과 요약")
    table.add_column("상태", style="bold")
    table.add_column("파일 수", justify="right")

    table.add_row("[green]성공[/green]", str(success))
    table.add_row("[yellow]미인식[/yellow]", str(unmatched))
    table.add_row("[red]오류[/red]", str(errors))
    table.add_row("[bold]전체[/bold]", str(len(results)))

    console.print()
    console.print(table)

    if dry_run:
        console.print()
        console.print(
            Panel(
                "[yellow]Dry-run 모드로 실행되었습니다.\n"
                "실제 변경을 적용하려면 config.yaml에서 dry_run: false로 설정하세요.[/yellow]",
                title="안내",
            )
        )


def print_file_result(result: dict, verbose: bool = False):
    """개별 파일 처리 결과를 출력합니다."""
    status = result["status"]
    file_name = Path(result["file"]).name

    if status == "success":
        metadata = result.get("metadata", {})
        console.print(
            f"  [green]✓[/green] {file_name} → "
            f"[cyan]{metadata.get('artist', 'Unknown')}[/cyan] - "
            f"[white]{metadata.get('title', 'Unknown')}[/white]"
        )

        if verbose and result.get("file_changes"):
            changes = result["file_changes"]
            if changes.get("moved"):
                console.print(
                    f"    [dim]→ {changes.get('destination')}[/dim]"
                )

    elif status == "unmatched":
        console.print(f"  [yellow]?[/yellow] {file_name} - 인식 실패")

    elif status == "error":
        error = result.get("error", "알 수 없는 오류")
        console.print(f"  [red]✗[/red] {file_name} - {error}")


def main():
    parser = argparse.ArgumentParser(
        description="MP3 Auto Organizer - 스마트 MP3 메타데이터 및 파일 정리 도구"
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="설정 파일 경로 (기본: config.yaml)",
    )
    parser.add_argument(
        "-s", "--source",
        help="스캔할 소스 경로 (설정 파일보다 우선)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 변경 없이 미리보기만 (설정 파일보다 우선)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="실제로 변경 적용 (설정 파일보다 우선)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="상세 출력",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="처리할 최대 파일 수 (테스트용)",
    )

    args = parser.parse_args()

    # 설정 로드
    config = load_config(args.config)

    # 커맨드라인 옵션으로 설정 덮어쓰기
    if args.source:
        config["source_path"] = args.source

    if args.dry_run:
        config["options"]["dry_run"] = True
    elif args.no_dry_run:
        config["options"]["dry_run"] = False

    dry_run = config.get("options", {}).get("dry_run", True)
    source_path = config.get("source_path", "")

    # 유효성 검사
    if not source_path:
        console.print("[red]소스 경로가 설정되지 않았습니다.[/red]")
        sys.exit(1)

    api_key = config.get("acoustid_api_key", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        console.print("[red]AcoustID API 키가 설정되지 않았습니다.[/red]")
        console.print(".env 파일에 ACOUSTID_API_KEY를 설정해주세요.")
        sys.exit(1)

    # fpcalc 확인
    if not check_fpcalc_installed():
        console.print("[red]fpcalc(Chromaprint)가 설치되어 있지 않습니다.[/red]")
        console.print("설치: brew install chromaprint")
        sys.exit(1)

    # 로깅 설정
    log_file = config.get("options", {}).get("log_file", "organizer.log")
    logger = setup_logging(log_file)

    # 헤더 출력
    console.print()
    console.print(
        Panel(
            "[bold blue]MP3 Auto Organizer[/bold blue]\n"
            f"소스: {source_path}\n"
            f"모드: {'[yellow]Dry-run (미리보기)[/yellow]' if dry_run else '[green]실제 적용[/green]'}",
            title="시작",
        )
    )

    # 파일 스캔
    console.print()
    console.print("[bold]MP3 파일 스캔 중...[/bold]")

    try:
        file_count = count_mp3_files(source_path)
    except (FileNotFoundError, NotADirectoryError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if file_count == 0:
        console.print("[yellow]MP3 파일을 찾지 못했습니다.[/yellow]")
        sys.exit(0)

    console.print(f"총 [cyan]{file_count}[/cyan]개 파일 발견")

    if args.limit:
        console.print(f"[dim]--limit 옵션: 최대 {args.limit}개 파일만 처리[/dim]")

    # 파일 처리
    results = []
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("처리 중...", total=min(file_count, args.limit or file_count))

        for idx, file_path in enumerate(scan_mp3_files(source_path)):
            if args.limit and idx >= args.limit:
                break

            progress.update(task, description=f"처리 중: {file_path.name[:30]}...")

            result = process_file(file_path, config, logger, dry_run=dry_run)
            results.append(result)

            progress.advance(task)

    # 결과 출력
    console.print()
    console.print("[bold]처리 결과:[/bold]")

    for result in results:
        print_file_result(result, verbose=args.verbose)

    # 요약 출력
    print_summary(results, dry_run)

    # 미인식 파일 처리 안내
    unmatched = [r for r in results if r["status"] == "unmatched"]
    if unmatched and not dry_run:
        unmatched_folder = config.get("options", {}).get("unmatched_folder", "_unmatched")
        output_path = Path(config.get("output_path") or config.get("source_path"))
        console.print()
        console.print(
            f"[yellow]인식되지 않은 {len(unmatched)}개 파일은 "
            f"'{output_path / unmatched_folder}' 폴더에서 확인할 수 있습니다.[/yellow]"
        )


if __name__ == "__main__":
    main()
