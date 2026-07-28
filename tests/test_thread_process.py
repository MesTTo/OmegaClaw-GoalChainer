from __future__ import annotations

import sys
from pathlib import Path

from goal_chainer.thread_models import ThreadSupervision
from goal_chainer.thread_process import ThreadProcessSupervisor


def supervision(
    *,
    lease: int = 2,
    idle: int = 2,
    wall: int = 4,
) -> ThreadSupervision:
    return ThreadSupervision(
        lease_seconds=lease,
        idle_timeout_seconds=idle,
        wall_timeout_seconds=wall,
        max_retries=0,
    )


def test_process_captures_combined_pty_output(tmp_path) -> None:
    result = ThreadProcessSupervisor().run(
        [
            sys.executable,
            "-c",
            "import sys; print('stdout'); print('stderr', file=sys.stderr)",
        ],
        cwd=tmp_path,
        supervision=supervision(),
    )

    assert result.exit_reason == "process-exited"
    assert result.exit_code == 0
    assert "stdout" in result.output
    assert "stderr" in result.output


def test_process_enforces_idle_timeout(tmp_path) -> None:
    result = ThreadProcessSupervisor().run(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        supervision=supervision(idle=1, wall=3),
    )

    assert result.exit_reason == "idle-timeout"
    assert result.exit_code < 0


def test_workspace_changes_count_as_passive_activity(tmp_path) -> None:
    script = (
        "import pathlib,time\n"
        "p=pathlib.Path('activity.txt')\n"
        "time.sleep(.6);p.write_text('one')\n"
        "time.sleep(.6);p.write_text('two')\n"
    )
    result = ThreadProcessSupervisor().run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        supervision=supervision(idle=1, wall=3),
    )

    assert result.exit_reason == "process-exited"
    assert result.activity_events >= 2


def test_process_enforces_output_limit(tmp_path) -> None:
    result = ThreadProcessSupervisor(output_limit=128).run(
        [sys.executable, "-c", "print('x' * 1000)"],
        cwd=tmp_path,
        supervision=supervision(),
    )

    assert result.exit_reason == "output-limit"
    assert result.output_bytes == 128


def test_failed_lease_renewal_terminates_process(tmp_path) -> None:
    renewals = 0

    def reject_renewal() -> bool:
        nonlocal renewals
        renewals += 1
        return False

    result = ThreadProcessSupervisor().run(
        [
            sys.executable,
            "-u",
            "-c",
            ("import time\nprint('alive')\ntime.sleep(5)\n"),
        ],
        cwd=tmp_path,
        supervision=supervision(lease=1, idle=2, wall=3),
        renew_lease=reject_renewal,
    )

    assert renewals == 1
    assert result.exit_reason == "lease-expired"


def test_pipe_mode_and_missing_executable_are_defined(tmp_path: Path) -> None:
    supervisor = ThreadProcessSupervisor()
    piped = supervisor.run(
        [sys.executable, "-c", "print('pipe')"],
        cwd=tmp_path,
        supervision=supervision(),
        use_pty=False,
    )
    missing = supervisor.run(
        ["goalchainer-command-that-does-not-exist"],
        cwd=tmp_path,
        supervision=supervision(),
    )

    assert piped.exit_reason == "process-exited"
    assert piped.output.strip() == "pipe"
    assert missing.exit_reason == "spawn-failed"
    assert missing.exit_code == 127
