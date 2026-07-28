from __future__ import annotations

from goal_chainer.thread_demo import run_thread_demo


def test_live_thread_demo_checks_every_claimed_capability(tmp_path) -> None:
    report = run_thread_demo(tmp_path / "demo")

    assert report["durable"] is True
    assert all(report["verified"].values())
    assert report["attempts"] == {
        "local": 1,
        "delegated": 1,
        "retry": 2,
        "permanent_failure": 3,
        "denied": 0,
    }
    assert "MeTTa Markdown task specifications" in report["now"]
    assert "claim and completion lifecycle only" in report["before"]
