"""スキルフォルダの .env の読み込み（load_dotenv_files）のテスト。

優先順位: OS 環境変数 > プロジェクトの .env（カレントから上位へ探索） > スキルフォルダの .env。
"""
from pathlib import Path

import pytest

import config
from config import load_dotenv_files

KEY = "GPT_IMAGE_TEST_DOTENV_KEY"
OTHER = "GPT_IMAGE_TEST_DOTENV_OTHER"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    monkeypatch.delenv(OTHER, raising=False)


def _dirs(tmp_path):
    project = tmp_path / "project"
    skill = tmp_path / "skills" / "gpt-image"
    project.mkdir()
    skill.mkdir(parents=True)
    return project, skill


def test_skill_dir_env_used_when_project_has_none(tmp_path, monkeypatch):
    project, skill = _dirs(tmp_path)
    (skill / ".env").write_text(f"{KEY}=from-skill\n", encoding="utf-8")
    applied = load_dotenv_files(start=str(project), skill_dir=str(skill))
    assert applied == [str((skill / ".env").resolve())]
    import os
    assert os.environ[KEY] == "from-skill"


def test_project_env_wins_over_skill_env(tmp_path):
    import os
    project, skill = _dirs(tmp_path)
    (project / ".env").write_text(f"{KEY}=from-project\n", encoding="utf-8")
    (skill / ".env").write_text(f"{KEY}=from-skill\n{OTHER}=skill-only\n", encoding="utf-8")
    applied = load_dotenv_files(start=str(project), skill_dir=str(skill))
    assert applied == [str((project / ".env").resolve()), str((skill / ".env").resolve())]
    assert os.environ[KEY] == "from-project"
    # プロジェクトの .env に無い値はスキルフォルダの .env で補完される
    assert os.environ[OTHER] == "skill-only"


def test_os_env_wins_over_both(tmp_path, monkeypatch):
    import os
    project, skill = _dirs(tmp_path)
    monkeypatch.setenv(KEY, "from-os")
    (project / ".env").write_text(f"{KEY}=from-project\n", encoding="utf-8")
    (skill / ".env").write_text(f"{KEY}=from-skill\n", encoding="utf-8")
    load_dotenv_files(start=str(project), skill_dir=str(skill))
    assert os.environ[KEY] == "from-os"


def test_same_file_is_applied_once(tmp_path):
    # カレントがスキルフォルダの場合、上位探索とスキルフォルダが同じ .env を指す
    _, skill = _dirs(tmp_path)
    (skill / ".env").write_text(f"{KEY}=x\n", encoding="utf-8")
    applied = load_dotenv_files(start=str(skill), skill_dir=str(skill))
    assert applied == [str((skill / ".env").resolve())]


def test_no_env_anywhere(tmp_path):
    project, skill = _dirs(tmp_path)
    assert load_dotenv_files(start=str(project), skill_dir=str(skill)) == []


def test_default_skill_dir_is_skill_root():
    assert Path(config.SKILL_DIR).name == "gpt-image"
    assert (Path(config.SKILL_DIR) / "SKILL.md").is_file()
