from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_omegaclaw_skill_file_exposes_system_prompt():
    source = (REPO_ROOT / "integrations/omegaclaw/goalchainer_skill.metta").read_text()

    assert "(goalchainer-system-prompt)" in source
    assert "structured English propositions" in source
    assert "native MeTTa/NAL evidence" in source
