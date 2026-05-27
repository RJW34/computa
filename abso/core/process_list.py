"""Helpers for parsing Windows tasklist output."""

from __future__ import annotations

import csv
from dataclasses import dataclass


@dataclass(frozen=True)
class TasklistProcess:
    """One process row from ``tasklist /FO CSV`` output."""

    image_name: str
    pid: int | None = None


def parse_tasklist_csv_processes(output: str) -> list[TasklistProcess]:
    """Parse ``tasklist /FO CSV`` output into exact process identities."""
    processes: list[TasklistProcess] = []
    for row in csv.reader(output.splitlines()):
        if len(row) < 2:
            continue
        image_name = row[0].strip()
        if not image_name:
            continue

        pid = None
        if len(row) > 1:
            try:
                pid = int(row[1].strip())
            except ValueError:
                pid = None
        processes.append(TasklistProcess(image_name=image_name, pid=pid))
    return processes


def parse_tasklist_csv_images(output: str) -> set[str]:
    """Return exact lowercase image names from ``tasklist /FO CSV`` output."""
    return {
        process.image_name.lower()
        for process in parse_tasklist_csv_processes(output)
        if process.image_name
    }
