#!/usr/bin/env python3
"""Tests for new confluence_api.py features: search, comments, spaces."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "confluence-publisher" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_MODULE_PATH = Path(_SCRIPTS_DIR) / "confluence_api.py"
_spec = importlib.util.spec_from_file_location("confluence_api", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["confluence_api"] = _mod

search_cql = _mod.search_cql
SearchResult = _mod.SearchResult
get_page_comments = _mod.get_page_comments
add_page_comment = _mod.add_page_comment
PageComment = _mod.PageComment
list_spaces = _mod.list_spaces
SpaceInfo = _mod.SpaceInfo
_rest_get = _mod._rest_get
_rest_post = _mod._rest_post


def _fake_config() -> mock.MagicMock:
    cfg = mock.MagicMock()
    cfg.confluence_url = "https://test.atlassian.net/wiki"
    return cfg


# ---------------------------------------------------------------------------
# search_cql
# ---------------------------------------------------------------------------


class TestSearchCql:
    def test_empty_results(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}):
            results = search_cql(_fake_config(), "type=page")
        assert results == []

    def test_parses_results(self) -> None:
        raw = {
            "results": [
                {
                    "content": {
                        "id": "123",
                        "title": "My Page",
                        "type": "page",
                        "space": {"key": "DOCS"},
                    },
                    "url": "/wiki/spaces/DOCS/pages/123",
                    "excerpt": "Some text...",
                },
                {
                    "content": {
                        "id": "456",
                        "title": "Blog Post",
                        "type": "blogpost",
                        "space": {"key": "ENG"},
                    },
                    "url": "/wiki/spaces/ENG/pages/456",
                    "excerpt": "",
                },
            ]
        }
        with mock.patch.object(_mod, "_rest_get", return_value=raw):
            results = search_cql(_fake_config(), 'type=page AND title~"My"', limit=10)
        assert len(results) == 2
        assert results[0].content_id == "123"
        assert results[0].title == "My Page"
        assert results[0].space_key == "DOCS"
        assert results[1].content_type == "blogpost"

    def test_passes_cql_and_limit(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}) as mock_get:
            search_cql(_fake_config(), "space=DEV", limit=5)
        mock_get.assert_called_once()
        call_params = mock_get.call_args[1].get("params") or mock_get.call_args[0][2]
        assert call_params["cql"] == "space=DEV"
        assert call_params["limit"] == "5"


# ---------------------------------------------------------------------------
# get_page_comments / add_page_comment
# ---------------------------------------------------------------------------


class TestPageComments:
    def test_empty_comments(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}):
            comments = get_page_comments(_fake_config(), "999")
        assert comments == []

    def test_parses_footer_comments(self) -> None:
        raw = {
            "results": [
                {
                    "id": "100",
                    "body": {"storage": {"value": "<p>Great page!</p>"}},
                    "version": {
                        "by": {"displayName": "Alice"},
                        "when": "2025-01-01T00:00:00Z",
                    },
                }
            ]
        }
        with mock.patch.object(_mod, "_rest_get", return_value=raw):
            comments = get_page_comments(_fake_config(), "999", comment_type="comment")
        assert len(comments) == 1
        assert comments[0].comment_id == "100"
        assert comments[0].author == "Alice"
        assert "Great page" in comments[0].body_html

    def test_inline_passes_location_param(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}) as mock_get:
            get_page_comments(_fake_config(), "999", comment_type="inline")
        call_params = mock_get.call_args[1].get("params") or mock_get.call_args[0][2]
        assert call_params.get("location") == "inline"

    def test_add_comment(self) -> None:
        with mock.patch.object(_mod, "_rest_post", return_value={"id": "200"}) as mock_post:
            cid = add_page_comment(_fake_config(), "999", "<p>LGTM</p>")
        assert cid == "200"
        mock_post.assert_called_once()
        payload = mock_post.call_args[0][2]
        assert payload["type"] == "comment"
        assert payload["container"]["id"] == "999"
        assert "LGTM" in payload["body"]["storage"]["value"]


# ---------------------------------------------------------------------------
# list_spaces
# ---------------------------------------------------------------------------


class TestListSpaces:
    def test_empty(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}):
            spaces = list_spaces(_fake_config())
        assert spaces == []

    def test_parses_spaces(self) -> None:
        raw = {
            "results": [
                {
                    "key": "DOCS",
                    "name": "Documentation",
                    "type": "global",
                    "status": "current",
                    "_links": {"base": "https://test.atlassian.net/wiki", "webui": "/spaces/DOCS"},
                },
                {
                    "key": "~alice",
                    "name": "Alice Personal",
                    "type": "personal",
                    "status": "current",
                    "_links": {},
                },
            ]
        }
        with mock.patch.object(_mod, "_rest_get", return_value=raw):
            spaces = list_spaces(_fake_config())
        assert len(spaces) == 2
        assert spaces[0].key == "DOCS"
        assert spaces[0].space_type == "global"
        assert "DOCS" in spaces[0].url
        assert spaces[1].url == ""

    def test_type_filter_passed(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}) as mock_get:
            list_spaces(_fake_config(), space_type="global")
        call_params = mock_get.call_args[1].get("params") or mock_get.call_args[0][2]
        assert call_params["type"] == "global"

    def test_no_type_filter(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}) as mock_get:
            list_spaces(_fake_config())
        call_params = mock_get.call_args[1].get("params") or mock_get.call_args[0][2]
        assert "type" not in call_params
