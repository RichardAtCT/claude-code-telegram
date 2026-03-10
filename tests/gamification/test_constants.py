"""Tests for gamification constants."""

from src.gamification.constants import (
    get_stat_for_file,
    get_xp_for_action,
    calculate_level,
    xp_for_level,
    get_title,
)


class TestFileStatMapping:
    def test_python_file_is_str(self):
        assert get_stat_for_file("server.py") == "str"

    def test_shell_file_is_str(self):
        assert get_stat_for_file("install.sh") == "str"

    def test_tsx_file_is_dex(self):
        assert get_stat_for_file("App.tsx") == "dex"

    def test_swift_file_is_dex(self):
        assert get_stat_for_file("ContentView.swift") == "dex"

    def test_test_file_is_con(self):
        assert get_stat_for_file("test_server.py") == "con"

    def test_spec_file_is_con(self):
        assert get_stat_for_file("app.spec.ts") == "con"

    def test_bats_file_is_con(self):
        assert get_stat_for_file("install.bats") == "con"

    def test_markdown_is_wis(self):
        assert get_stat_for_file("README.md") == "wis"

    def test_unknown_file_returns_none(self):
        assert get_stat_for_file("data.csv") is None


class TestXpForAction:
    def test_commit_normal(self):
        assert get_xp_for_action("commit") == 10

    def test_commit_feat(self):
        assert get_xp_for_action("commit_feat") == 30

    def test_commit_fix(self):
        assert get_xp_for_action("commit_fix") == 20

    def test_test_run(self):
        assert get_xp_for_action("test_run") == 10

    def test_qa_pass(self):
        assert get_xp_for_action("qa_pass") == 15


class TestLevelFormula:
    def test_level_1_is_0_xp(self):
        assert xp_for_level(1) == 0

    def test_level_2_is_100_xp(self):
        assert xp_for_level(2) == 100

    def test_calculate_level_0_xp(self):
        assert calculate_level(0) == 1

    def test_calculate_level_99_xp(self):
        assert calculate_level(99) == 1

    def test_calculate_level_100_xp(self):
        assert calculate_level(100) == 2

    def test_calculate_level_5000_xp(self):
        assert calculate_level(5000) >= 10


class TestTitles:
    def test_level_1(self):
        assert get_title(1) == "Junior Developer"

    def test_level_10(self):
        assert get_title(10) == "Senior Developer"

    def test_level_50(self):
        assert get_title(50) == "Legendary Architect"
