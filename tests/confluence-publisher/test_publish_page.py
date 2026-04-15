"""Unit tests for publish_page.py — attachment throttle and post-upload re-save.

Tests the two fixes applied to publish_page.publish_page():
1. Throttle: 1s sleep between individual attachment uploads to avoid
   Confluence transaction rollback errors.
2. Re-save: After uploading all diagram attachments, re-save the page body
   so Confluence resolves ri:attachment references that were UNKNOWN_ATTACHMENT
   on initial create (attachments didn't exist at first save time).
"""

import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, call, patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "confluence-publisher" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Ensure 'atlassian' is importable even without atlassian-python-api installed.
# publish_page.py calls ensure_deps() and imports Confluence at module level.
if "atlassian" not in sys.modules:
    _atlassian_mod = types.ModuleType("atlassian")
    _atlassian_mod.Confluence = MagicMock  # type: ignore[attr-defined]
    sys.modules["atlassian"] = _atlassian_mod

from confluence_config import ConfluenceConfig  # noqa: E402
from publish_page import publish_page  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> ConfluenceConfig:
    return ConfluenceConfig(
        confluence_url="https://example.atlassian.net/wiki",
        space_key="TEST",
        root_page_id="100",
    )


def _make_confluence_mock(page_id: str = "999") -> MagicMock:
    mock = MagicMock()
    mock.create_page.return_value = {"id": page_id, "_links": {"webui": "/spaces/TEST/pages/999"}}
    mock.update_page.return_value = {"id": page_id, "_links": {"webui": "/spaces/TEST/pages/999"}}
    mock.get_page_by_id.return_value = {"id": page_id, "version": {"number": 1}}
    mock.attach_file.return_value = True
    return mock


def _write_md_with_mermaid(tmp: Path, diagram_count: int = 3) -> Path:
    """Write a markdown file with N mermaid blocks."""
    blocks = [f"```mermaid\ngraph LR\n  A{i}-->B{i}\n```" for i in range(diagram_count)]
    md_path = tmp / "test.md"
    md_path.write_text("\n\n".join(["# Test"] + blocks), encoding="utf-8")
    return md_path


# ---------------------------------------------------------------------------
# Fix 1: Throttle between attachment uploads
# ---------------------------------------------------------------------------


class TestAttachmentUploadThrottle:
    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_sleep_between_uploads(self, mock_render: MagicMock, mock_time: MagicMock) -> None:
        """Verify 1s sleep is called between each attachment (not after the last)."""
        config = _make_config()
        confluence = _make_confluence_mock()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = _write_md_with_mermaid(tmp_path, diagram_count=3)

            # Simulate render_mermaid_blocks returning 3 PNG paths
            png_files = []
            for i in range(1, 4):
                p = tmp_path / f"diagram-{i}.png"
                p.write_bytes(b"fake-png")
                png_files.append(p)

            mock_render.return_value = (
                "# Test\n<!-- MERMAID_IMG:diagram-1.png -->\n<!-- MERMAID_IMG:diagram-2.png -->\n<!-- MERMAID_IMG:diagram-3.png -->",
                png_files,
            )

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="Test Page",
                mode="create",
                parent_id="100",
            )

        # Expect: sleep(2) initial wait, then sleep(1) between uploads (N-1 times)
        sleep_calls = mock_time.sleep.call_args_list
        assert call(2) in sleep_calls, "Should have initial 2s sleep before uploads"
        throttle_count = sum(1 for c in sleep_calls if c == call(1))
        assert throttle_count == 2, f"Expected 2 throttle sleeps for 3 files, got {throttle_count}"

    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_no_throttle_for_single_file(
        self, mock_render: MagicMock, mock_time: MagicMock
    ) -> None:
        """A single attachment should have no throttle sleep (only the initial 2s)."""
        config = _make_config()
        confluence = _make_confluence_mock()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = _write_md_with_mermaid(tmp_path, diagram_count=1)

            p = tmp_path / "diagram-1.png"
            p.write_bytes(b"fake-png")
            mock_render.return_value = ("# Test\n<!-- MERMAID_IMG:diagram-1.png -->", [p])

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="Test Page",
                mode="create",
                parent_id="100",
            )

        sleep_calls = mock_time.sleep.call_args_list
        throttle_count = sum(1 for c in sleep_calls if c == call(1))
        assert throttle_count == 0, "Single file should have no throttle sleeps"

    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_no_sleep_without_diagrams(self, mock_render: MagicMock, mock_time: MagicMock) -> None:
        """No mermaid diagrams → no sleeps at all."""
        config = _make_config()
        confluence = _make_confluence_mock()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = tmp_path / "test.md"
            md_path.write_text("# No diagrams here", encoding="utf-8")

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="Test Page",
                mode="create",
                parent_id="100",
            )

        mock_time.sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 2: Re-save page body after attachment uploads
# ---------------------------------------------------------------------------


class TestPostUploadReSave:
    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_update_page_called_after_attachments(
        self, mock_render: MagicMock, mock_time: MagicMock
    ) -> None:
        """After uploading diagrams, update_page must be called to re-resolve references."""
        config = _make_config()
        confluence = _make_confluence_mock(page_id="555")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = _write_md_with_mermaid(tmp_path, diagram_count=2)

            pngs = []
            for i in range(1, 3):
                p = tmp_path / f"diagram-{i}.png"
                p.write_bytes(b"fake-png")
                pngs.append(p)

            mock_render.return_value = (
                "# Test\n<!-- MERMAID_IMG:diagram-1.png -->\n<!-- MERMAID_IMG:diagram-2.png -->",
                pngs,
            )

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="My Page",
                mode="create",
                parent_id="100",
            )

        # update_page should be called AFTER attach_file calls
        update_calls = confluence.update_page.call_args_list
        assert len(update_calls) == 1, (
            f"Expected exactly 1 update_page call (re-save), got {len(update_calls)}"
        )

        # Verify the re-save call has the correct arguments
        resave_call = update_calls[0]
        assert resave_call.kwargs.get("page_id") or resave_call[1].get("page_id") == "555"
        assert resave_call.kwargs.get("title") or resave_call[1].get("title") == "My Page"

        # attach_file must have been called before the re-save
        assert confluence.attach_file.call_count == 2

    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_no_resave_without_diagrams(self, mock_render: MagicMock, mock_time: MagicMock) -> None:
        """Without mermaid diagrams, update_page should NOT be called (create mode uses create_page)."""
        config = _make_config()
        confluence = _make_confluence_mock()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = tmp_path / "test.md"
            md_path.write_text("# Plain page", encoding="utf-8")

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="Plain",
                mode="create",
                parent_id="100",
            )

        confluence.update_page.assert_not_called()
        confluence.attach_file.assert_not_called()

    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_resave_uses_same_body(self, mock_render: MagicMock, mock_time: MagicMock) -> None:
        """The re-save must use the same rendered body that was initially published."""
        config = _make_config()
        confluence = _make_confluence_mock(page_id="777")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = _write_md_with_mermaid(tmp_path, diagram_count=1)

            p = tmp_path / "diagram-1.png"
            p.write_bytes(b"fake-png")
            mock_render.return_value = ("# Test\n<!-- MERMAID_IMG:diagram-1.png -->", [p])

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="Same Body",
                mode="create",
                parent_id="100",
            )

        resave = confluence.update_page.call_args
        body_in_resave = resave.kwargs.get("body", "")
        # The body should contain the injected image macro
        assert "diagram-1.png" in body_in_resave

    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_resave_on_update_mode(self, mock_render: MagicMock, mock_time: MagicMock) -> None:
        """In update mode, update_page is called once for the initial save and once for re-save."""
        config = _make_config()
        confluence = _make_confluence_mock(page_id="888")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = _write_md_with_mermaid(tmp_path, diagram_count=1)

            p = tmp_path / "diagram-1.png"
            p.write_bytes(b"fake-png")
            mock_render.return_value = ("# Test\n<!-- MERMAID_IMG:diagram-1.png -->", [p])

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="Update Mode",
                mode="update",
                page_id="888",
            )

        # update mode: 1 initial update + 1 re-save = 2
        assert confluence.update_page.call_count == 2


# ---------------------------------------------------------------------------
# Combined: verify ordering (attach happens between create and re-save)
# ---------------------------------------------------------------------------


class TestUploadOrdering:
    @patch("publish_page.time")
    @patch("publish_page.render_mermaid_blocks")
    def test_call_order_create_attach_resave(
        self, mock_render: MagicMock, mock_time: MagicMock
    ) -> None:
        """Verify the exact call order: create_page → attach_file(s) → update_page."""
        config = _make_config()
        confluence = _make_confluence_mock(page_id="123")

        call_log: list[str] = []
        _page_result = {"id": "123", "_links": {"webui": "/p/123"}}

        def _log_create(**kw) -> dict:  # noqa: ANN003
            call_log.append("create_page")
            return _page_result

        def _log_attach(**kw) -> None:  # noqa: ANN003
            call_log.append("attach_file")

        def _log_update(**kw) -> dict:  # noqa: ANN003
            call_log.append("update_page")
            return _page_result

        confluence.create_page.side_effect = _log_create
        confluence.attach_file.side_effect = _log_attach
        confluence.update_page.side_effect = _log_update

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_path = _write_md_with_mermaid(tmp_path, diagram_count=2)

            pngs = []
            for i in range(1, 3):
                p = tmp_path / f"diagram-{i}.png"
                p.write_bytes(b"fake-png")
                pngs.append(p)

            mock_render.return_value = (
                "# Test\n<!-- MERMAID_IMG:diagram-1.png -->\n<!-- MERMAID_IMG:diagram-2.png -->",
                pngs,
            )

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="Order Test",
                mode="create",
                parent_id="100",
            )

        assert call_log == [
            "create_page",
            "attach_file",
            "attach_file",
            "update_page",  # re-save after attachments
        ], f"Unexpected call order: {call_log}"


# ---------------------------------------------------------------------------
# Fix 3: Strip duplicate H1 heading that matches page title
# ---------------------------------------------------------------------------


class TestStripTitleHeading:
    def test_h1_matching_title_is_stripped(self) -> None:
        """When the first H1 matches the page title, it should not appear in the body."""
        config = _make_config()
        confluence = _make_confluence_mock()

        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "test.md"
            md_path.write_text("# My Page\n\nBody content", encoding="utf-8")

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="My Page",
                mode="create",
                parent_id="100",
            )

        body = confluence.create_page.call_args.kwargs.get("body", "")
        assert "<h1>" not in body, f"H1 should be stripped from body but got: {body}"
        assert "Body content" in body

    def test_h1_not_matching_title_is_kept(self) -> None:
        """When the first H1 does NOT match the title, it should remain in the body."""
        config = _make_config()
        confluence = _make_confluence_mock()

        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "test.md"
            md_path.write_text("# Different Heading\n\nBody content", encoding="utf-8")

            publish_page(
                confluence=confluence,
                config=config,
                file_path=md_path,
                title="My Page",
                mode="create",
                parent_id="100",
            )

        body = confluence.create_page.call_args.kwargs.get("body", "")
        assert "Different Heading" in body
