#!/usr/bin/env python3
"""Tests for new confluence_api.py features: search, comments, spaces."""

import importlib.util
import sys
from pathlib import Path
from typing import Any
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


def _require(name: str) -> Any:
    return getattr(_mod, name)


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
        assert mock_get.call_args.args[1] == "/pages/999/inline-comments"
        call_params = mock_get.call_args.args[2]
        assert call_params["body-format"] == "storage"

    def test_add_comment(self) -> None:
        with mock.patch.object(_mod, "_rest_post", return_value={"id": "200"}) as mock_post:
            cid = add_page_comment(_fake_config(), "999", "<p>LGTM</p>")
        assert cid == "200"
        mock_post.assert_called_once()
        payload = mock_post.call_args[0][2]
        assert payload["pageId"] == "999"
        assert payload["body"]["representation"] == "storage"
        assert "LGTM" in payload["body"]["value"]


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
        assert mock_get.call_args.kwargs["api_version"] == "v2"

    def test_no_type_filter(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}) as mock_get:
            list_spaces(_fake_config())
        call_params = mock_get.call_args[1].get("params") or mock_get.call_args[0][2]
        assert "type" not in call_params
        assert mock_get.call_args.kwargs["api_version"] == "v2"


# ---------------------------------------------------------------------------
# v2 page listing and comment helpers
# ---------------------------------------------------------------------------


class TestPageListingV2:
    def test_list_pages_resolves_space_key_and_passes_filters(self) -> None:
        space_lookup = {"results": [{"id": "42", "key": "DOCS"}]}
        pages_raw = {
            "results": [
                {
                    "id": "100",
                    "status": "current",
                    "title": "API",
                    "spaceId": "42",
                    "parentId": "1",
                    "subtype": "live",
                    "version": {"number": 3, "createdAt": "2026-01-01T00:00:00Z"},
                    "_links": {"webui": "/spaces/DOCS/pages/100/API"},
                }
            ]
        }
        with mock.patch.object(
            _mod, "_rest_get", side_effect=[space_lookup, pages_raw]
        ) as mock_get:
            list_pages = _require("list_pages")
            pages = list_pages(_fake_config(), space_key="DOCS", title="API", status="current")
        assert len(pages) == 1
        assert pages[0].page_id == "100"
        assert pages[0].subtype == "live"
        assert mock_get.call_args_list[0].args[1] == "/spaces"
        assert mock_get.call_args_list[0].args[2]["keys"] == "DOCS"
        assert mock_get.call_args_list[0].kwargs["api_version"] == "v2"
        assert mock_get.call_args_list[1].args[1] == "/spaces/42/pages"
        assert mock_get.call_args_list[1].args[2]["title"] == "API"
        assert mock_get.call_args_list[1].args[2]["status"] == "current"
        assert mock_get.call_args_list[1].kwargs["api_version"] == "v2"

    def test_type_filter_is_applied_client_side(self) -> None:
        space_lookup = {"results": [{"id": "42", "key": "DOCS"}]}
        pages_raw = {
            "results": [
                {
                    "id": "100",
                    "status": "current",
                    "title": "Live Doc",
                    "spaceId": "42",
                    "subtype": "live",
                    "version": {"number": 3},
                    "_links": {},
                },
                {
                    "id": "101",
                    "status": "current",
                    "title": "Normal Doc",
                    "spaceId": "42",
                    "subtype": "page",
                    "version": {"number": 1},
                    "_links": {},
                },
            ]
        }
        with mock.patch.object(_mod, "_rest_get", side_effect=[space_lookup, pages_raw]):
            list_pages = _require("list_pages")
            pages = list_pages(_fake_config(), space_key="DOCS", page_type="live")
        assert [page.page_id for page in pages] == ["100"]


class TestCommentV2Helpers:
    def test_list_footer_comments_hits_v2_endpoint(self) -> None:
        raw = {
            "results": [
                {
                    "id": "200",
                    "status": "current",
                    "pageId": "100",
                    "body": {"storage": {"value": "<p>Hi</p>"}},
                    "version": {
                        "createdAt": "2026-01-01T00:00:00Z",
                        "authorId": "acct-1",
                    },
                }
            ]
        }
        with mock.patch.object(_mod, "_rest_get", return_value=raw) as mock_get:
            list_page_comments = _require("list_page_comments")
            comments = list_page_comments(_fake_config(), "100")
        assert len(comments) == 1
        assert comments[0].comment_id == "200"
        assert comments[0].page_id == "100"
        assert mock_get.call_args.args[1] == "/pages/100/footer-comments"
        assert mock_get.call_args.args[2]["body-format"] == "storage"
        assert mock_get.call_args.kwargs["api_version"] == "v2"

    def test_list_inline_comments_can_filter_resolution_status(self) -> None:
        with mock.patch.object(_mod, "_rest_get", return_value={"results": []}) as mock_get:
            list_page_comments = _require("list_page_comments")
            list_page_comments(
                _fake_config(), "100", comment_type="inline", resolution_status="open"
            )
        assert mock_get.call_args.args[1] == "/pages/100/inline-comments"
        assert mock_get.call_args.args[2]["resolution-status"] == "open"
        assert mock_get.call_args.kwargs["api_version"] == "v2"

    def test_add_footer_reply_uses_parent_comment_id(self) -> None:
        with mock.patch.object(_mod, "_rest_post", return_value={"id": "201"}) as mock_post:
            add_page_comment = _require("add_page_comment")
            cid = add_page_comment(
                _fake_config(),
                "100",
                "<p>Reply</p>",
                comment_type="comment",
                parent_comment_id="200",
            )
        assert cid == "201"
        payload = mock_post.call_args.args[2]
        assert mock_post.call_args.args[1] == "/footer-comments"
        assert payload["parentCommentId"] == "200"
        assert "pageId" not in payload
        assert mock_post.call_args.kwargs["api_version"] == "v2"

    def test_add_inline_comment_uses_selection_context(self) -> None:
        with mock.patch.object(_mod, "_rest_post", return_value={"id": "202"}) as mock_post:
            add_page_comment = _require("add_page_comment")
            cid = add_page_comment(
                _fake_config(),
                "100",
                "<p>Inline</p>",
                comment_type="inline",
                inline_text_selection="anchor",
                inline_text_selection_match_count=2,
                inline_text_selection_match_index=1,
            )
        assert cid == "202"
        payload = mock_post.call_args.args[2]
        assert mock_post.call_args.args[1] == "/inline-comments"
        assert payload["inlineCommentProperties"]["textSelection"] == "anchor"
        assert payload["inlineCommentProperties"]["textSelectionMatchCount"] == 2
        assert mock_post.call_args.kwargs["api_version"] == "v2"

    def test_edit_and_resolve_inline_comment(self) -> None:
        current = {
            "id": "203",
            "pageId": "100",
            "body": {"storage": {"value": "<p>Old</p>"}},
            "version": {"number": 4},
        }
        with (
            mock.patch.object(_mod, "_rest_get", return_value=current) as mock_get,
            mock.patch.object(_mod, "_rest_put", return_value={"id": "203"}) as mock_put,
        ):
            edit_comment = _require("edit_comment")
            resolve_comment = _require("resolve_comment")
            edit_comment(_fake_config(), "203", "<p>New</p>", comment_type="inline")
            resolve_comment(_fake_config(), "203", comment_type="inline")
        assert mock_get.call_args.args[1] == "/inline-comments/203"
        assert mock_get.call_args_list[1].kwargs["params"]["body-format"] == "storage"
        assert mock_put.call_args.args[1] == "/inline-comments/203"
        assert mock_put.call_args.args[2]["version"]["number"] == 5
        assert mock_put.call_args.args[2]["resolved"] is True
        assert mock_get.call_args.kwargs["api_version"] == "v2"
        assert mock_put.call_args.kwargs["api_version"] == "v2"

    def test_delete_comment_uses_correct_route(self) -> None:
        with mock.patch.object(_mod, "_rest_delete", return_value=None) as mock_delete:
            delete_comment = _require("delete_comment")
            delete_comment(_fake_config(), "203", comment_type="footer")
        assert mock_delete.call_args.args[1] == "/footer-comments/203"
        assert mock_delete.call_args.kwargs["api_version"] == "v2"

    def test_list_comment_children_hits_children_endpoint(self) -> None:
        raw = {
            "results": [
                {
                    "id": "204",
                    "pageId": "100",
                    "parentCommentId": "203",
                    "body": {"storage": {"value": "<p>Child</p>"}},
                    "version": {"createdAt": "2026-01-01T00:00:00Z", "authorId": "acct-2"},
                }
            ]
        }
        with mock.patch.object(_mod, "_rest_get", return_value=raw) as mock_get:
            list_comment_children = _require("list_comment_children")
            children = list_comment_children(_fake_config(), "203", comment_type="footer")
        assert len(children) == 1
        assert children[0].comment_id == "204"
        assert mock_get.call_args.args[1] == "/footer-comments/203/children"
        assert mock_get.call_args.kwargs["api_version"] == "v2"

    def test_walk_comment_thread_recurses_depth_first(self) -> None:
        root = {
            "results": [
                {
                    "id": "203",
                    "pageId": "100",
                    "body": {"storage": {"value": "<p>Root</p>"}},
                    "version": {"createdAt": "2026-01-01T00:00:00Z", "authorId": "acct-1"},
                }
            ]
        }
        child = {
            "results": [
                {
                    "id": "204",
                    "pageId": "100",
                    "parentCommentId": "203",
                    "body": {"storage": {"value": "<p>Child</p>"}},
                    "version": {"createdAt": "2026-01-01T00:00:00Z", "authorId": "acct-2"},
                }
            ]
        }
        grandchild = {
            "results": [
                {
                    "id": "205",
                    "pageId": "100",
                    "parentCommentId": "204",
                    "body": {"storage": {"value": "<p>Grandchild</p>"}},
                    "version": {"createdAt": "2026-01-01T00:00:00Z", "authorId": "acct-3"},
                }
            ]
        }
        empty: dict[str, list[dict[str, object]]] = {"results": []}
        with mock.patch.object(
            _mod,
            "_rest_get",
            side_effect=[root, child, grandchild, empty],
        ):
            walk_comment_thread = _require("walk_comment_thread")
            comments = walk_comment_thread(_fake_config(), "100", comment_type="footer")
        assert [c.comment_id for c in comments] == ["203", "204", "205"]

    def test_like_helpers_cover_pages_and_comments(self) -> None:
        with mock.patch.object(
            _mod,
            "_rest_get",
            side_effect=[
                {"count": 16},
                {"results": [{"accountId": "a1"}, {"accountId": "a2"}]},
                {"count": 4},
                {"results": [{"accountId": "b1"}]},
                {"count": 7},
                {"results": [{"accountId": "c1"}]},
            ],
        ) as mock_get:
            get_page_like_count = _require("get_page_like_count")
            get_page_like_users = _require("get_page_like_users")
            get_comment_like_count = _require("get_comment_like_count")
            get_comment_like_users = _require("get_comment_like_users")
            assert get_page_like_count(_fake_config(), "100") == 16
            assert get_page_like_users(_fake_config(), "100") == ["a1", "a2"]
            assert get_comment_like_count(_fake_config(), "200", comment_type="footer") == 4
            assert get_comment_like_users(_fake_config(), "200", comment_type="footer") == ["b1"]
            assert get_comment_like_count(_fake_config(), "201", comment_type="inline") == 7
            assert get_comment_like_users(_fake_config(), "201", comment_type="inline") == ["c1"]
        assert mock_get.call_count == 6
