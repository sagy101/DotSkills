"""
Bidirectional link rewriter: relative markdown paths <-> git browse URLs.

Supports Bitbucket (bitbucket.org) and GitHub (github.com) URL patterns.
Called automatically by create_ticket.py and update_ticket.py before sending
descriptions to Jira.

Usage as module:
    from link_rewriter import rewrite_links_to_git, rewrite_links_to_local
    description = rewrite_links_to_git(description, config)

Usage as CLI:
    python link_rewriter.py --config .jira.json --direction to-git --text "See [doc](plan/design.md)"
    python link_rewriter.py --config .jira.json --direction to-local --text "See https://bitbucket.org/..."
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import JiraConfig, load_config


def _git_remote_to_browse_base(remote_url: str, branch: str) -> Optional[str]:
    """Convert a git remote URL to a browsable base URL.

    Examples:
        git@bitbucket.org:firelayers/cap-agent-kit.git  ->  https://bitbucket.org/firelayers/cap-agent-kit/src/main/
        https://github.com/user/repo.git                ->  https://github.com/user/repo/blob/main/
        git@github.com:user/repo.git                    ->  https://github.com/user/repo/blob/main/
    """
    remote_url = remote_url.strip()

    # SSH format: git@host:org/repo.git
    ssh_match = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", remote_url)
    if ssh_match:
        host = ssh_match.group(1)
        path = ssh_match.group(2)
    else:
        # HTTPS format
        parsed = urlparse(remote_url)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/").removesuffix(".git")

    if not host or not path:
        return None

    if "bitbucket" in host:
        return f"https://{host}/{path}/src/{branch}/"
    elif "github" in host:
        return f"https://{host}/{path}/blob/{branch}/"
    elif "gitlab" in host:
        return f"https://{host}/{path}/-/blob/{branch}/"
    else:
        # Generic: assume a /blob/ pattern
        return f"https://{host}/{path}/blob/{branch}/"


def rewrite_links_to_git(text: str, config: JiraConfig) -> str:
    """Replace relative markdown links with full git browse URLs.

    Matches patterns like:
        [text](path/to/file.md)
        [text](./path/to/file.md)

    Skips links that are already absolute URLs (http://, https://).
    """
    remote_url = config.resolve_git_remote_url()
    if not remote_url:
        return text

    branch = config.resolve_git_branch()
    browse_base = _git_remote_to_browse_base(remote_url, branch)
    if not browse_base:
        return text

    def _replace_link(match):
        full_match = match.group(0)
        link_text = match.group(1)
        link_target = match.group(2)

        # Skip absolute URLs and anchors
        if link_target.startswith(("http://", "https://", "#", "mailto:")):
            return full_match

        # Normalize: strip leading ./ prefix (but preserve ../ and other paths)
        clean = link_target
        while clean.startswith("./"):
            clean = clean[2:]
        return f"[{link_text}]({browse_base}{clean})"

    # Match markdown links: [text](target)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _replace_link, text)


def rewrite_links_to_local(text: str, config: JiraConfig) -> str:
    """Replace git browse URLs back to relative markdown paths.

    Inverse of rewrite_links_to_git.
    """
    remote_url = config.resolve_git_remote_url()
    if not remote_url:
        return text

    branch = config.resolve_git_branch()
    browse_base = _git_remote_to_browse_base(remote_url, branch)
    if not browse_base:
        return text

    def _replace_link(match):
        link_text = match.group(1)
        link_target = match.group(2)

        if link_target.startswith(browse_base):
            relative = link_target[len(browse_base):]
            return f"[{link_text}]({relative})"
        return match.group(0)

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _replace_link, text)


def main():
    parser = argparse.ArgumentParser(description="Rewrite links in text")
    parser.add_argument("--config", required=True, help="Path to .jira.json")
    parser.add_argument(
        "--direction",
        choices=["to-git", "to-local"],
        required=True,
        help="Direction of link rewriting",
    )
    parser.add_argument("--text", help="Text to transform (reads stdin if omitted)")
    parser.add_argument("--file", help="File to read text from")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()

    if args.direction == "to-git":
        result = rewrite_links_to_git(text, config)
    else:
        result = rewrite_links_to_local(text, config)

    print(result)


if __name__ == "__main__":
    main()
