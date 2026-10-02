"""What has to survive an install.

plotplate is a library, a command, a viewer and a set of agent skills, but it is one Python
package: the skills and the journal presets are package data, and the viewer's JavaScript is a
string inside `view.py`. So `pip install plotplate`, `pip install git+...` and an editable
checkout all carry the same files — as long as the package-data patterns say so, which is what
these tests check, by building a real wheel.
"""

import json
import zipfile
from pathlib import Path

import pytest

from plotplate.cli import main

SRC = Path(__file__).resolve().parents[1] / "src" / "plotplate"


def _data_files() -> list[str]:
    """Everything under the package that is not Python source."""
    return sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*")
        if path.is_file() and path.suffix not in {".py", ".pyc"} and "__pycache__" not in path.parts
    )


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    """A wheel built from this checkout, the way PyPI would get it."""
    build = pytest.importorskip("setuptools.build_meta")
    out = tmp_path_factory.mktemp("wheel")
    name = build.build_wheel(str(out))
    return zipfile.ZipFile(out / name)


def test_every_data_file_is_in_the_wheel(wheel):
    """Skills, presets and the demo travel with the package, or the install is broken."""
    inside = set(wheel.namelist())
    missing = [name for name in _data_files() if f"plotplate/{name}" not in inside]
    assert not missing, f"not shipped: {missing}"


def test_the_skills_are_in_the_wheel(wheel):
    skills = sorted(n for n in wheel.namelist() if "/skills/" in n and n.endswith("SKILL.md"))
    assert len(skills) == len(list((SRC / "skills").iterdir()))
    assert all(wheel.read(name).strip() for name in skills)  # and none of them is empty


def test_skills_paths_can_be_read(capsys):
    """`plotplate skills --paths` prints files an agent can open, one per line."""
    assert main(["skills", "--paths"]) == 0
    paths = [Path(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert paths and all(path.is_file() and path.name == "SKILL.md" for path in paths)
    assert all("description:" in path.read_text(encoding="utf-8") for path in paths)


def test_skills_json_lists_name_description_and_path(capsys):
    assert main(["skills", "--json"]) == 0
    skills = json.loads(capsys.readouterr().out)
    assert {"figure-review", "figure-panel-fitting"} <= {skill["name"] for skill in skills}
    for skill in skills:
        assert skill["description"] and Path(skill["path"]).is_file()


def test_skills_list_says_where_they_live(capsys):
    assert main(["skills", "--list"]) == 0
    out = capsys.readouterr().out
    assert "all of them are under" in out and str(SRC / "skills") in out


def test_skills_install_into_a_project(tmp_path, capsys):
    assert main(["skills", "--dest", str(tmp_path / ".claude" / "skills")]) == 0
    installed = sorted(p.name for p in (tmp_path / ".claude" / "skills").iterdir())
    assert installed == sorted(p.name for p in (SRC / "skills").iterdir())
    assert (tmp_path / ".claude" / "skills" / "figure-review" / "SKILL.md").read_text()
    assert main(["skills", "--dest", str(tmp_path / ".claude" / "skills")]) == 0
    assert "skip" in capsys.readouterr().out  # a second run does not overwrite
