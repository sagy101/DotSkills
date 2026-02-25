"""
Shared configuration loader for confluence-publisher skill scripts.

Loads .confluence.json and resolves credentials from env vars or .env file.
"""

import base64
import json
import os
import re
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def ensure_deps(required_packages: dict) -> None:
    """Install missing Python packages. required_packages maps pip name → import name."""
    missing = []
    for pkg, imp in required_packages.items():
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing],
            stdout=subprocess.DEVNULL,
        )


@dataclass
class ConfluenceConfig:
    confluence_url: str
    space_key: str
    root_page_id: str
    docs_dir: str = "."
    manifest_path: str = ".confluence-manifest.json"
    username_env: str = "CONFLUENCE_EMAIL"
    token_env: str = "CONFLUENCE_TOKEN"
    env_file: Optional[str] = None
    title_map: dict = field(default_factory=dict)
    exclude_patterns: list = field(default_factory=list)

    # Resolved at runtime
    project_root: Path = field(default_factory=lambda: Path.cwd())

    @property
    def docs_root(self) -> Path:
        return self.project_root / self.docs_dir

    @property
    def manifest_file(self) -> Path:
        return self.project_root / self.manifest_path


def find_config(start_dir: Optional[str] = None) -> Path:
    """Walk up from start_dir looking for .confluence.json."""
    current = Path(start_dir) if start_dir else Path.cwd()
    while current != current.parent:
        candidate = current / ".confluence.json"
        if candidate.exists():
            return candidate
        current = current.parent
    print("ERROR: .confluence.json not found in any parent directory")
    print("Create one in your project root. See references/CONFIG.md for format.")
    sys.exit(1)


def load_env_file(env_path: Path) -> dict:
    """Parse a .env file into a dict."""
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            key = key.strip()
            # Handle 'export KEY=VALUE' syntax
            if key.startswith("export "):
                key = key[len("export "):].strip()
            env[key] = val.strip().strip('"').strip("'")
    return env


def load_config(config_path: Optional[str] = None) -> ConfluenceConfig:
    """Load and validate .confluence.json, resolve credentials."""
    if config_path:
        path = Path(config_path)
    else:
        path = find_config()

    if not path.exists():
        print(f"ERROR: Config file not found: {path}")
        sys.exit(1)

    raw = json.loads(path.read_text(encoding="utf-8"))
    project_root = path.parent

    # Required fields
    for field_name in ("confluence_url", "space_key", "root_page_id"):
        if field_name not in raw:
            print(f"ERROR: Missing required field '{field_name}' in {path}")
            sys.exit(1)

    creds = raw.get("credentials", {})

    config = ConfluenceConfig(
        confluence_url=raw["confluence_url"].rstrip("/"),
        space_key=raw["space_key"],
        root_page_id=str(raw["root_page_id"]),
        docs_dir=raw.get("docs_dir", "."),
        manifest_path=raw.get("manifest_path", ".confluence-manifest.json"),
        username_env=creds.get("username_env", "CONFLUENCE_EMAIL"),
        token_env=creds.get("token_env", "CONFLUENCE_TOKEN"),
        env_file=raw.get("env_file"),
        title_map=raw.get("title_map", {}),
        exclude_patterns=raw.get("exclude_patterns", []),
        project_root=project_root,
    )

    return config


def resolve_credentials(config: ConfluenceConfig) -> tuple:
    """Resolve username and API token from env file or environment variables.
    Returns (username, token). Exits on failure."""
    env_vars = {}

    # Load .env file if configured
    if config.env_file:
        env_path = config.project_root / config.env_file
        env_vars = load_env_file(env_path)

    username = env_vars.get(config.username_env) or os.environ.get(config.username_env)
    token = env_vars.get(config.token_env) or os.environ.get(config.token_env)

    if not username:
        print(f"ERROR: Credential not found: set {config.username_env} as an environment variable or in your env_file")
        sys.exit(1)
    if not token:
        print(f"ERROR: Credential not found: set {config.token_env} as an environment variable or in your env_file")
        sys.exit(1)

    return username, token


def load_manifest(config: ConfluenceConfig) -> dict:
    """Load the manifest file. Returns empty dict if not found."""
    if config.manifest_file.exists():
        return json.loads(config.manifest_file.read_text(encoding="utf-8"))
    return {}


def save_manifest(config: ConfluenceConfig, manifest: dict) -> None:
    """Save the manifest file."""
    config.manifest_file.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def connect(config: ConfluenceConfig):
    """Create a Confluence client from config credentials."""
    ensure_deps({"atlassian-python-api": "atlassian"})
    from atlassian import Confluence

    username, token = resolve_credentials(config)
    return Confluence(
        url=config.confluence_url,
        username=username,
        password=token,
        cloud=True,
        timeout=120,
    )


def get_all_children(confluence, page_id: str) -> list:
    """Fetch all child pages with pagination (handles >100 children)."""
    all_children = []
    start = 0
    limit = 100
    while True:
        batch = confluence.get_page_child_by_type(
            page_id=page_id, type="page", start=start, limit=limit
        )
        if not batch:
            break
        all_children.extend(batch)
        if len(batch) < limit:
            break
        start += limit
    return all_children


def decode_tiny_link(tiny_id: str) -> int:
    """Decode a Confluence tiny link ID to a numeric page ID.

    Confluence tiny links encode the page ID as a little-endian unsigned 32-bit
    integer, stripped of trailing zero bytes, then base64-encoded with URL-safe
    altchars (_-) and padding removed.

    Args:
        tiny_id: The encoded portion after ``/x/`` in a tiny link URL.

    Returns:
        The decoded numeric page ID.
    """
    raw = tiny_id.encode("ascii") if isinstance(tiny_id, str) else tiny_id
    # The encoding strips trailing 'A' chars (base64 zeros) and '=' padding.
    # Restore to a valid base64 length: data chars mod 4 must be 0, 2, or 3.
    remainder = len(raw) % 4
    if remainder == 1:
        raw += b"A"
        remainder = 2
    raw += b"=" * ((4 - remainder) % 4)
    page_id_bytes = (base64.b64decode(raw, altchars=b"_-") + b"\x00\x00\x00\x00")[:4]
    return struct.unpack("<L", page_id_bytes)[0]


def encode_tiny_id(page_id: int) -> str:
    """Encode a numeric page ID into a Confluence tiny link ID.

    Inverse of :func:`decode_tiny_link`.
    """
    return (
        base64.b64encode(struct.pack("<L", int(page_id)).rstrip(b"\x00"), altchars=b"_-")
        .rstrip(b"=")
        .decode("ascii")
    )


_TINY_LINK_RE = re.compile(r"/x/([-_A-Za-z0-9]+)")


def extract_page_id(page_ref: str) -> str:
    """Extract a numeric page ID from a page reference.

    Accepts:
      - A plain numeric ID (``"774112245"``)
      - A standard Confluence URL containing ``/pages/<id>``
      - A Confluence tiny link containing ``/x/<encoded>``

    Returns:
        The page ID as a string.

    Raises:
        ValueError: If the reference format is not recognised.
    """
    if page_ref.isdigit():
        return page_ref
    match = re.search(r"/pages/(\d+)", page_ref)
    if match:
        return match.group(1)
    tiny_match = _TINY_LINK_RE.search(page_ref)
    if tiny_match:
        return str(decode_tiny_link(tiny_match.group(1)))
    raise ValueError(f"Could not extract page ID from: {page_ref}")


def resolve_title(file_path: str, md_content: str, config: ConfluenceConfig) -> str:
    """Resolve page title using: title_map > first heading > filename."""
    # 1. Explicit title_map
    if file_path in config.title_map:
        return config.title_map[file_path]

    # 2. First # heading in the markdown
    match = re.search(r"^#\s+(.+)$", md_content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # 3. Filename-based
    name = Path(file_path).stem
    if name.lower() == "readme":
        # Use parent directory name
        parent = Path(file_path).parent.name
        if parent and parent != ".":
            name = parent
    return name.replace("-", " ").replace("_", " ").title()
