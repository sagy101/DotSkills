#!/usr/bin/env python3
"""Tests for workspace_graph.py — repo scanning, dependency graph, topological sort."""

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

# ── Import the module under test ──────────────────────────────────────────────

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "sbt-build-test"
    / "scripts"
    / "workspace_graph.py"
)
_spec = importlib.util.spec_from_file_location("workspace_graph", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["workspace_graph"] = _mod

scan_repo = _mod.scan_repo
topo_sort = _mod.topo_sort
read_services = _mod.read_services
main = _mod.main


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a minimal multi-repo workspace for testing.

    Layout:
        workspace/
          shared-models/
            build.sbt          — leaf library, name := "shared-models"
          platform-commons/
            build.sbt          — depends on shared-models via ProjectRef + libraryDependencies
            project/
              Deps.scala       — declares name := "platform-commons"
          service-a/
            build.sbt          — depends on platform-commons via libraryDependencies
          service-b/
            build.sbt          — depends on shared-models via libraryDependencies only
          standalone/
            build.sbt          — no workspace dependencies
    """
    group = "com.example"

    # shared-models (leaf)
    models = tmp_path / "shared-models"
    models.mkdir()
    (models / "build.sbt").write_text(
        textwrap.dedent(f"""\
        organization := "{group}"
        name := "shared-models"
        version := "1.0.0"
        scalaVersion := "2.13.14"
    """)
    )

    # platform-commons (depends on shared-models)
    commons = tmp_path / "platform-commons"
    commons.mkdir()
    (commons / "project").mkdir()
    (commons / "build.sbt").write_text(
        textwrap.dedent(f"""\
        organization := "{group}"
        version := "2.0.0"
        scalaVersion := "2.13.14"

        lazy val root = (project in file("."))
          .dependsOn(sharedModelsRef)

        lazy val sharedModelsRef = ProjectRef(file("../shared-models"), "shared-models")

        libraryDependencies ++= Seq(
          "{group}" %% "shared-models" % "1.0.0"
        )
    """)
    )
    (commons / "project" / "Deps.scala").write_text(
        textwrap.dedent("""\
        import sbt._

        object Deps {
          val name = "platform-commons"
        }
    """)
    )

    # service-a (depends on platform-commons via libraryDependencies)
    svc_a = tmp_path / "service-a"
    svc_a.mkdir()
    (svc_a / "build.sbt").write_text(
        textwrap.dedent(f"""\
        organization := "{group}"
        name := "service-a"
        version := "3.0.0"
        scalaVersion := "2.13.14"

        libraryDependencies ++= Seq(
          "{group}" %% "platform-commons" % "2.0.0"
        )
    """)
    )

    # service-b (depends on shared-models only)
    svc_b = tmp_path / "service-b"
    svc_b.mkdir()
    (svc_b / "build.sbt").write_text(
        textwrap.dedent(f"""\
        organization := "{group}"
        name := "service-b"
        version := "1.0.0"
        scalaVersion := "2.13.14"

        libraryDependencies ++= Seq(
          "{group}" %% "shared-models" % "1.0.0"
        )
    """)
    )

    # standalone (no deps)
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    (standalone / "build.sbt").write_text(
        textwrap.dedent(f"""\
        organization := "{group}"
        name := "standalone"
        version := "0.1.0"
        scalaVersion := "2.13.14"
    """)
    )

    return tmp_path


@pytest.fixture
def services_file(workspace: Path, tmp_path: Path) -> Path:
    """Write a services file listing all repos in the workspace."""
    sf = tmp_path / "services.txt"
    repos = sorted(workspace.iterdir())
    sf.write_text("\n".join(str(r) for r in repos if (r / "build.sbt").exists()) + "\n")
    return sf


# ── scan_repo ─────────────────────────────────────────────────────────────────


class TestScanRepo:
    def test_extracts_artifact_name_from_build_sbt(self, workspace: Path):
        result = scan_repo(workspace / "shared-models", "com.example")
        assert "shared-models" in result["artifacts"]

    def test_extracts_artifact_name_from_project_scala(self, workspace: Path):
        result = scan_repo(workspace / "platform-commons", "com.example")
        assert "platform-commons" in result["artifacts"]

    def test_detects_project_ref(self, workspace: Path):
        result = scan_repo(workspace / "platform-commons", "com.example")
        ref_paths = result["project_ref_paths"]
        assert len(ref_paths) == 1
        assert ref_paths[0].endswith("shared-models")

    def test_detects_published_workspace_artifacts(self, workspace: Path):
        result = scan_repo(workspace / "platform-commons", "com.example")
        assert "shared-models" in result["published_workspace_artifacts"]

    def test_no_project_refs_when_none_exist(self, workspace: Path):
        result = scan_repo(workspace / "service-a", "com.example")
        assert result["project_ref_paths"] == []

    def test_published_deps_filtered_by_group(self, workspace: Path):
        result = scan_repo(workspace / "service-a", "com.example")
        assert "platform-commons" in result["published_workspace_artifacts"]

    def test_no_published_deps_with_wrong_group(self, workspace: Path):
        result = scan_repo(workspace / "service-a", "org.other")
        assert result["published_workspace_artifacts"] == []

    def test_falls_back_to_dir_name_when_no_name_setting(self, tmp_path: Path):
        repo = tmp_path / "my-repo"
        repo.mkdir()
        (repo / "build.sbt").write_text('version := "1.0.0"\n')
        result = scan_repo(repo, "com.example")
        assert "my-repo" in result["artifacts"]

    def test_repo_name_is_directory_name(self, workspace: Path):
        result = scan_repo(workspace / "service-a", "com.example")
        assert result["name"] == "service-a"

    def test_empty_group_id_skips_published_deps(self, workspace: Path):
        result = scan_repo(workspace / "service-a", "")
        assert result["published_workspace_artifacts"] == []


# ── topo_sort ─────────────────────────────────────────────────────────────────


class TestTopoSort:
    def test_linear_chain(self):
        nodes = ["a", "b", "c"]
        deps = {"a": set(), "b": {"a"}, "c": {"b"}}
        order, cycles = topo_sort(nodes, deps)
        assert cycles == []
        assert order.index("a") < order.index("b") < order.index("c")

    def test_diamond_dependency(self):
        nodes = ["a", "b", "c", "d"]
        deps = {"a": set(), "b": {"a"}, "c": {"a"}, "d": {"b", "c"}}
        order, cycles = topo_sort(nodes, deps)
        assert cycles == []
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_no_dependencies(self):
        nodes = ["x", "y", "z"]
        deps = {"x": set(), "y": set(), "z": set()}
        order, cycles = topo_sort(nodes, deps)
        assert cycles == []
        assert sorted(order) == ["x", "y", "z"]

    def test_single_node(self):
        order, cycles = topo_sort(["only"], {"only": set()})
        assert order == ["only"]
        assert cycles == []

    def test_cycle_detected(self):
        nodes = ["a", "b"]
        deps = {"a": {"b"}, "b": {"a"}}
        order, cycles = topo_sort(nodes, deps)
        assert len(cycles) > 0
        assert set(cycles) == {"a", "b"}

    def test_partial_cycle(self):
        """A cycle in part of the graph; the rest should still sort."""
        nodes = ["a", "b", "c"]
        deps = {"a": set(), "b": {"c"}, "c": {"b"}}
        order, cycles = topo_sort(nodes, deps)
        assert "a" in order
        assert set(cycles) == {"b", "c"}

    def test_empty_graph(self):
        order, cycles = topo_sort([], {})
        assert order == []
        assert cycles == []


# ── Full graph integration (main via CLI) ─────────────────────────────────────


class TestFullGraph:
    def _run_graph(
        self, workspace: Path, services_file: Path, group_id: str = "com.example"
    ) -> dict[str, Any]:
        """Run main() and capture the JSON output."""
        import io

        old_argv = sys.argv
        old_stdout = sys.stdout
        try:
            sys.argv = [
                "workspace_graph.py",
                "--workspace-dir",
                str(workspace),
                "--services-file",
                str(services_file),
                "--group-id",
                group_id,
            ]
            buf = io.StringIO()
            sys.stdout = buf
            rc = main()
            assert rc == 0
            result: dict[str, Any] = json.loads(buf.getvalue())
            return result
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout

    def test_all_repos_present(self, workspace: Path, services_file: Path):
        data = self._run_graph(workspace, services_file)
        names = {r["name"] for r in data["repos"]}
        assert names == {
            "shared-models",
            "platform-commons",
            "service-a",
            "service-b",
            "standalone",
        }

    def test_dependency_edges(self, workspace: Path, services_file: Path):
        data = self._run_graph(workspace, services_file)
        by_name = {r["name"]: r for r in data["repos"]}

        # platform-commons depends on shared-models (ProjectRef + libraryDependencies)
        assert "shared-models" in by_name["platform-commons"]["dependencies"]

        # service-a depends on platform-commons (libraryDependencies)
        assert "platform-commons" in by_name["service-a"]["dependencies"]

        # service-b depends on shared-models
        assert "shared-models" in by_name["service-b"]["dependencies"]

        # standalone has no deps
        assert by_name["standalone"]["dependencies"] == []

        # shared-models has no deps
        assert by_name["shared-models"]["dependencies"] == []

    def test_dependents_are_reverse_of_dependencies(self, workspace: Path, services_file: Path):
        data = self._run_graph(workspace, services_file)
        by_name = {r["name"]: r for r in data["repos"]}

        # shared-models is depended on by platform-commons and service-b
        assert set(by_name["shared-models"]["dependents"]) == {"platform-commons", "service-b"}

        # platform-commons is depended on by service-a
        assert by_name["platform-commons"]["dependents"] == ["service-a"]

    def test_publish_order_respects_dependencies(self, workspace: Path, services_file: Path):
        data = self._run_graph(workspace, services_file)
        order = data["publish_order"]

        assert order.index("shared-models") < order.index("platform-commons")
        assert order.index("platform-commons") < order.index("service-a")
        assert order.index("shared-models") < order.index("service-b")

    def test_no_cycles(self, workspace: Path, services_file: Path):
        data = self._run_graph(workspace, services_file)
        assert data["cycles"] == []

    def test_group_id_propagated(self, workspace: Path, services_file: Path):
        data = self._run_graph(workspace, services_file)
        assert data["group_id"] == "com.example"

    def test_workspace_path(self, workspace: Path, services_file: Path):
        data = self._run_graph(workspace, services_file)
        assert data["workspace"] == str(workspace)

    def test_empty_group_id_still_finds_project_refs(self, workspace: Path, services_file: Path):
        """Without a group_id, published artifact deps are missed but ProjectRef still works."""
        data = self._run_graph(workspace, services_file, group_id="")
        by_name = {r["name"]: r for r in data["repos"]}
        # ProjectRef still detected
        assert "shared-models" in by_name["platform-commons"]["dependencies"]
        # But libraryDependencies-only link is NOT detected
        assert "platform-commons" not in by_name["service-a"]["dependencies"]


# ── read_services ─────────────────────────────────────────────────────────────


class TestReadServices:
    def test_reads_paths(self, tmp_path: Path):
        sf = tmp_path / "services.txt"
        sf.write_text("/path/to/repo-a\n/path/to/repo-b\n")
        result = read_services(sf)
        assert len(result) == 2
        assert result[0] == Path("/path/to/repo-a")
        assert result[1] == Path("/path/to/repo-b")

    def test_skips_blank_lines(self, tmp_path: Path):
        sf = tmp_path / "services.txt"
        sf.write_text("/path/a\n\n/path/b\n\n")
        result = read_services(sf)
        assert len(result) == 2

    def test_empty_file(self, tmp_path: Path):
        sf = tmp_path / "services.txt"
        sf.write_text("")
        result = read_services(sf)
        assert result == []


# ── Edge cases: multi-artifact repos ──────────────────────────────────────────


class TestMultiArtifactRepo:
    def test_multiple_name_settings_all_detected(self, tmp_path: Path):
        repo = tmp_path / "multi"
        repo.mkdir()
        (repo / "build.sbt").write_text(
            textwrap.dedent("""\
            lazy val core = (project in file("core"))
              .settings(name := "multi-core")

            lazy val api = (project in file("api"))
              .settings(name := "multi-api")
        """)
        )
        result = scan_repo(repo, "com.example")
        assert "multi-core" in result["artifacts"]
        assert "multi-api" in result["artifacts"]

    def test_dependent_on_multi_artifact_repo(self, tmp_path: Path):
        """If repo-a produces 'lib-core' and 'lib-api', and repo-b depends on 'lib-core',
        the graph should show repo-b -> repo-a."""
        producer = tmp_path / "producer"
        producer.mkdir()
        (producer / "build.sbt").write_text(
            textwrap.dedent("""\
            organization := "com.example"
            lazy val core = (project in file("core"))
              .settings(name := "lib-core")
            lazy val api = (project in file("api"))
              .settings(name := "lib-api")
        """)
        )

        consumer = tmp_path / "consumer"
        consumer.mkdir()
        (consumer / "build.sbt").write_text(
            textwrap.dedent("""\
            organization := "com.example"
            name := "consumer"
            libraryDependencies += "com.example" %% "lib-core" % "1.0.0"
        """)
        )

        sf = tmp_path / "services.txt"
        sf.write_text(f"{producer}\n{consumer}\n")

        import io

        old_argv = sys.argv
        old_stdout = sys.stdout
        try:
            sys.argv = [
                "workspace_graph.py",
                "--workspace-dir",
                str(tmp_path),
                "--services-file",
                str(sf),
                "--group-id",
                "com.example",
            ]
            buf = io.StringIO()
            sys.stdout = buf
            main()
            data = json.loads(buf.getvalue())
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout

        by_name = {r["name"]: r for r in data["repos"]}
        assert "producer" in by_name["consumer"]["dependencies"]
