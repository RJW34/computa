"""Tests for shared Windows tasklist parsing."""

from __future__ import annotations

from abso.core.process_list import parse_tasklist_csv_images, parse_tasklist_csv_processes


def test_parse_tasklist_csv_processes_reads_exact_image_and_pid() -> None:
    output = '"game.exe","1234","Console","1","42,000 K"\n'

    processes = parse_tasklist_csv_processes(output)

    assert len(processes) == 1
    assert processes[0].image_name == "game.exe"
    assert processes[0].pid == 1234


def test_parse_tasklist_csv_images_does_not_match_substrings() -> None:
    output = (
        '"notgame.exe","1111","Console","1","10000 K"\n'
        '"game.exe","2222","Console","1","10000 K"\n'
    )

    assert parse_tasklist_csv_images(output) == {"notgame.exe", "game.exe"}


def test_parse_tasklist_csv_ignores_non_csv_status_lines() -> None:
    assert parse_tasklist_csv_images("INFO: No tasks are running\n") == set()
