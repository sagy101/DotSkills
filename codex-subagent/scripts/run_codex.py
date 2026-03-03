#!/usr/bin/env python3
"""
Safety wrapper for invoking Codex CLI as a sub-agent.

This script is the ONLY interface the host agent should use to run codex exec.
It enforces safety policy, adds default flags, manages temp files, handles git
worktrees, and provides clear error messages.

Usage:
    echo "<PROMPT>" | python3 run_codex.py --mode read-only -
    echo "<PROMPT>" | python3 run_codex.py --mode write --collision high -
    echo "<PROMPT>" | python3 run_codex.py --mode write --collision medium -
    echo "<PROMPT>" | python3 run_codex.py --mode read-only --review-prompt /path/to/prompt.md -
    echo "<FOLLOW-UP>" | python3 run_codex.py --resume -
"""

import argparse
import atexit
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid


# ========== CONFIGURATION ==========
MIN_VERSION = "0.106.0"
MAX_PROMPT_CHARS = 50000
VALID_TIMEOUTS = {300, 600, 1200, 2400}
VALID_MODES = {"read-only", "write"}
VALID_COLLISIONS = {"high", "medium"}
DEFAULT_MAX_PARALLEL = 6
PID_TRACKING_DIR = os.path.join(tempfile.gettempdir(), "codex-agent-pids")

_SANDBOX_CONFIG_MSG = "BLOCKED: sandbox cannot be overridden via config. Use --mode read-only or --mode write."

# Flags that the wrapper handles automatically — reject if passed directly
BLOCKED_WRAPPER_FLAGS = {
    "--ephemeral": (
        "ERROR: --ephemeral is added automatically by the wrapper. Do not pass it.\n"
        'USAGE: echo "<prompt>" | python3 run_codex.py --mode read-only -'
    ),
    "--full-auto": (
        "ERROR: --full-auto is added automatically when --mode write is used.\n"
        'USAGE: echo "<prompt>" | python3 run_codex.py --mode write -'
    ),
    "-o": (
        "ERROR: -o is added automatically by the wrapper. Output path is printed to stdout.\n"
        'USAGE: echo "<prompt>" | python3 run_codex.py --mode read-only -'
    ),
    "--output-last-message": (
        "ERROR: -o is added automatically by the wrapper. Output path is printed to stdout.\n"
        'USAGE: echo "<prompt>" | python3 run_codex.py --mode read-only -'
    ),
    "--json": (
        "ERROR: --json output is not available through the wrapper (stdout is captured internally).\n"
        "Use the -o result file for output, or --output-schema for structured JSON."
    ),
}


# Global ref for atexit cleanup
_pid_file_path: str | None = None


def eprint(*args, **kwargs) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


# ========== PARALLEL AGENT TRACKING ==========

def _ensure_pid_dir() -> None:
    """Create the PID tracking directory if it doesn't exist."""
    os.makedirs(PID_TRACKING_DIR, mode=0o755, exist_ok=True)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_pid_metadata(filepath: str) -> dict:
    """Read metadata from a PID file. Returns dict with at least 'pid'."""
    try:
        with open(filepath, "r") as f:
            data = json.loads(f.read())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    # Legacy or corrupt file — extract PID from filename
    return {}


def _scan_agents() -> tuple[list[dict], int]:
    """Scan PID directory and return (active_agents, stale_cleaned_count).

    Each active agent dict has: pid, started, mode (if available).
    Stale PID files are removed during the scan.
    """
    _ensure_pid_dir()
    active = []
    stale_cleaned = 0
    for name in os.listdir(PID_TRACKING_DIR):
        filepath = os.path.join(PID_TRACKING_DIR, name)
        if not os.path.isfile(filepath):
            continue
        try:
            pid = int(name)
        except ValueError:
            continue
        if _is_pid_alive(pid):
            meta = _read_pid_metadata(filepath)
            meta["pid"] = pid
            active.append(meta)
        else:
            try:
                os.unlink(filepath)
                stale_cleaned += 1
            except OSError:
                pass
    return active, stale_cleaned


def _count_active_agents() -> int:
    """Count active codex agent processes by scanning PID files.

    Removes stale PID files for processes that are no longer running.
    """
    active, _ = _scan_agents()
    return len(active)


def _register_agent(mode: str = "unknown") -> str:
    """Register this process as an active agent. Returns the PID file path.

    Stores JSON metadata: pid, start time (ISO + epoch), mode.
    """
    _ensure_pid_dir()
    pid_file = os.path.join(PID_TRACKING_DIR, str(os.getpid()))
    metadata = {
        "pid": os.getpid(),
        "started": time.time(),
        "started_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mode": mode,
    }
    with open(pid_file, "w") as f:
        json.dump(metadata, f)
    return pid_file


def _unregister_agent() -> None:
    """Remove this process's PID file on exit."""
    if _pid_file_path and os.path.exists(_pid_file_path):
        try:
            os.unlink(_pid_file_path)
        except OSError:
            pass


def _signal_cleanup(signum: int, _frame) -> None:
    """Signal handler that cleans up PID file then re-raises."""
    _unregister_agent()
    # Re-raise with default handler so exit code reflects the signal
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def enforce_parallel_limit(max_parallel: int, mode: str = "unknown") -> None:
    """Check active agent count and block if at or above the limit.

    Also registers this process and sets up atexit + signal cleanup.
    """
    global _pid_file_path

    active = _count_active_agents()
    if active >= max_parallel:
        eprint(
            f"BLOCKED: {active} codex sub-agents already running (limit: {max_parallel}).\n"
            "Wait for running agents to finish, or pass --max-parallel N to override "
            "(not recommended — increases resource usage and cost).\n"
            "Run with --status to see which agents are active."
        )
        sys.exit(2)

    _pid_file_path = _register_agent(mode)
    atexit.register(_unregister_agent)
    # Ensure cleanup on SIGHUP (terminal close) — SIGTERM/SIGINT already trigger atexit
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _signal_cleanup)


def print_status() -> None:
    """Print status of all tracked codex sub-agents and exit."""
    active_agents, stale_cleaned = _scan_agents()
    now = time.time()

    if not active_agents and stale_cleaned == 0:
        print("No codex sub-agents tracked.")
        sys.exit(0)

    if active_agents:
        print(f"Active agents: {len(active_agents)}")
        for agent in sorted(active_agents, key=lambda a: a.get("started", 0)):
            pid = agent["pid"]
            mode = agent.get("mode", "unknown")
            started = agent.get("started")
            if started:
                elapsed = int(now - started)
                mins, secs = divmod(elapsed, 60)
                duration = f"{mins}m{secs:02d}s"
                started_str = agent.get("started_iso", "unknown")
            else:
                duration = "unknown"
                started_str = "unknown"
            print(f"  PID {pid}  mode={mode}  started={started_str}  running={duration}")
    else:
        print("Active agents: 0")

    if stale_cleaned > 0:
        print(f"Stale PIDs cleaned: {stale_cleaned}")

    print(f"Limit: {DEFAULT_MAX_PARALLEL} (override with --max-parallel N)")
    sys.exit(0)


def version_gte(current: str, minimum: str) -> bool:
    """Check if current version >= minimum version using semantic versioning."""
    def parse(v: str) -> tuple:
        parts = v.split(".")
        return tuple(int(p) for p in parts)
    try:
        return parse(current) >= parse(minimum)
    except (ValueError, IndexError):
        return False


def check_version() -> str:
    """Check codex CLI is installed and meets minimum version. Returns version string."""
    codex_path = shutil.which("codex")
    if not codex_path:
        eprint("ERROR: codex CLI not found. Install: npm i -g @openai/codex")
        sys.exit(127)

    try:
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout.strip() + result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        eprint("ERROR: codex CLI not responding. Reinstall: npm i -g @openai/codex")
        sys.exit(127)

    match = re.search(r"(\d+\.\d+\.\d+)", output)
    if not match:
        eprint(f"ERROR: Could not parse codex version from: {output}")
        sys.exit(2)

    current = match.group(1)
    if not version_gte(current, MIN_VERSION):
        eprint(
            f"ERROR: codex v{current} found, but v{MIN_VERSION}+ is required. "
            "Upgrade: npm i -g @openai/codex"
        )
        sys.exit(2)

    return current


def _check_sandbox_flag(arg: str, next_arg: str | None) -> None:
    """Check and block sandbox-related flags (all syntactic forms)."""
    if arg.startswith("--sandbox"):
        if "danger" in arg:
            eprint(f"BLOCKED: flag '{arg}' is not permitted by skill policy")
            sys.exit(2)
        if arg == "--sandbox" and next_arg is not None and "danger" in next_arg:
            eprint(f"BLOCKED: '--sandbox {next_arg}' is not permitted by skill policy")
            sys.exit(2)
        eprint("ERROR: --sandbox is controlled by --mode flag. Use --mode read-only or --mode write.")
        sys.exit(2)
    if arg == "-s" or (arg.startswith("-s") and not arg.startswith("--")):
        eprint(
            "BLOCKED: -s (--sandbox) is controlled by --mode flag. "
            "Use --mode read-only or --mode write.\n"
            "Direct sandbox flags are not permitted — the wrapper sets the correct sandbox automatically."
        )
        sys.exit(2)


def _is_sandbox_config_override(arg: str, next_arg: str | None) -> bool:
    """Check if arg is a config override targeting sandbox settings."""
    if arg in ("-c", "--config") and next_arg is not None:
        return next_arg.lower().startswith("sandbox")
    if arg.startswith("--config="):
        return arg.split("=", 1)[1].lower().startswith("sandbox")
    if arg.startswith("-c") and not arg.startswith("--") and len(arg) > 2:
        return arg[2:].lower().startswith("sandbox")
    return False


def _is_scope_flag(arg: str) -> bool:
    """Check if arg is a scope-changing flag."""
    return arg in ("--cd", "-C", "--add-dir") or arg.startswith("--cd=") or arg.startswith("--add-dir=")


def _matches_blocked_flag(arg: str, blocked: str) -> bool:
    """Check if arg matches a blocked wrapper flag in any syntactic form."""
    if arg == blocked:
        return True
    if arg.startswith(blocked + "="):
        return True
    return len(blocked) == 2 and arg.startswith(blocked) and not arg.startswith("--") and len(arg) > 2


def _check_dangerous_flag(arg: str, next_arg: str | None) -> None:
    """Check and block dangerous bypass, config sandbox overrides, and scope-changing flags."""
    if arg.startswith("--dangerously-bypass"):
        eprint(f"BLOCKED: flag '{arg}' is not permitted by skill policy")
        sys.exit(2)
    if _is_sandbox_config_override(arg, next_arg):
        eprint(_SANDBOX_CONFIG_MSG)
        sys.exit(2)
    if _is_scope_flag(arg):
        eprint(f"BLOCKED: '{arg}' is not permitted — the wrapper controls working directory.\n"
               "Use --collision medium for worktree isolation.")
        sys.exit(2)
    for blocked, msg in BLOCKED_WRAPPER_FLAGS.items():
        if _matches_blocked_flag(arg, blocked):
            eprint(msg)
            sys.exit(2)


def scan_for_dangerous_flags(passthrough: list[str]) -> None:
    """Block dangerous flags in passthrough arguments."""
    for i, arg in enumerate(passthrough):
        next_arg = passthrough[i + 1] if i + 1 < len(passthrough) else None
        _check_sandbox_flag(arg, next_arg)
        _check_dangerous_flag(arg, next_arg)


def create_temp_dir() -> str:
    """Create a secure temporary directory."""
    tmpdir = tempfile.mkdtemp(prefix="codex-")
    os.chmod(tmpdir, 0o700)
    return tmpdir


def setup_worktree(collision: str, mode: str) -> tuple[str | None, str | None, str | None]:
    """Set up a git worktree if collision is medium and mode is write.

    Returns (worktree_dir, worktree_branch, worktree_id) or (None, None, None).
    """
    if collision != "medium" or mode != "write":
        return None, None, None

    worktree_id = f"codex-work-{uuid.uuid4().hex[:12]}"
    worktree_dir = os.path.join(tempfile.gettempdir(), f"codex-wt-{worktree_id}")

    result = subprocess.run(
        ["git", "worktree", "add", worktree_dir, "-b", worktree_id],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        eprint(
            f"ERROR: Failed to create git worktree.\n"
            f"  stdout: {result.stdout.strip()}\n"
            f"  stderr: {result.stderr.strip()}\n"
            "Cannot proceed with --collision medium without worktree isolation.\n"
            "Fix: commit or stash changes, then retry. Or use --collision high (no isolation)."
        )
        sys.exit(2)

    return worktree_dir, worktree_id, worktree_id


def build_prompt_file(tmpdir: str, review_prompt_path: str | None) -> str:
    """Build the prompt file from review prompt + stdin.

    Returns path to the prompt file.
    """
    prompt_file = os.path.join(tmpdir, "prompt.txt")

    with open(prompt_file, "w", encoding="utf-8") as f:
        if review_prompt_path:
            if not os.path.isfile(review_prompt_path):
                eprint(
                    f"ERROR: Review prompt file not found: {review_prompt_path}\n"
                    "Pass an absolute path to a complete .md review prompt file.\n"
                    "Review prompt files can come from a review skill, project docs, or any .md file you create."
                )
                sys.exit(2)
            with open(review_prompt_path, "r", encoding="utf-8") as rp:
                f.write(rp.read())
            f.write("\n\n--- Additional context from host agent ---\n")

        if not sys.stdin.isatty():
            stdin_content = sys.stdin.read()
            f.write(stdin_content)

    return prompt_file


def _extract_subcommand(passthrough: list[str]) -> tuple[str | None, list[str], list[str]]:
    """Detect and extract a codex exec subcommand from passthrough args.

    Only the first non-flag positional token is considered a subcommand candidate.
    Subcommands ('review') must be placed right after 'exec' in the codex CLI.
    Returns (subcommand, subcommand_args, remaining_passthrough).
    """
    known_subcommands = {"review"}
    skip_next = False
    for i, arg in enumerate(passthrough):
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("-"):
            if "=" not in arg and arg not in ("--uncommitted",):
                skip_next = True
            continue
        if arg in known_subcommands:
            return arg, passthrough[i + 1:], passthrough[:i]
        break
    return None, [], passthrough


def build_codex_args(
    mode: str,
    resume: bool,
    persist: bool,
    web_search: bool,
    skip_git_repo_check: bool,
    result_file: str,
    worktree_dir: str | None,
    passthrough: list[str],
) -> list[str]:
    """Build the codex command-line arguments."""
    args = []

    # Detect subcommand in passthrough — must be placed right after 'exec'
    subcmd, subcmd_args, remaining_passthrough = _extract_subcommand(passthrough)

    if resume:
        args.extend(["exec", "resume", "--last"])
        args.extend(["-o", result_file])
    else:
        args.append("exec")

        # Place subcommand immediately after 'exec' (before flags)
        if subcmd:
            args.append(subcmd)

        # Sandbox mode based on --mode
        if mode == "write":
            args.extend(["--full-auto", "--sandbox", "workspace-write"])
        elif mode == "read-only":
            args.extend(["--sandbox", "read-only"])

        # Ephemeral unless persist
        if not persist:
            args.append("--ephemeral")

        args.extend(["-o", result_file])

        # Web search
        if web_search:
            args.extend(["-c", "web_search_request=true"])

        # Worktree directory
        if worktree_dir:
            args.extend(["--cd", worktree_dir])

        # Subcommand-specific args (e.g., --uncommitted, --base)
        args.extend(subcmd_args)

    # Skip git repo check if requested
    if skip_git_repo_check:
        args.append("--skip-git-repo-check")

    # Always force no color for script parsing
    args.extend(["--color", "never"])

    # Append remaining passthrough args (model overrides, etc.)
    args.extend(remaining_passthrough)

    return args


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Send SIGTERM then SIGKILL to the process group."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except OSError:
            pass
        proc.wait()


def _normalize_exit_code(code: int | None) -> int:
    """Normalize negative signal exit codes to 128 + signal_number convention."""
    if code is None:
        return 1
    if code >= 0:
        return code
    return 128 + abs(code)


def run_codex(codex_args: list[str], prompt_file: str, timeout: int) -> int:
    """Run codex with the given args, feeding prompt via stdin. Returns exit code."""
    cmd = ["codex"] + codex_args

    try:
        with open(prompt_file, "r", encoding="utf-8") as pf:
            proc = subprocess.Popen(
                cmd, stdin=pf, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
            )

        try:
            _, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            eprint(f"TIMEOUT: codex killed after {timeout}s")
            return 124

        if stderr:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if stderr_text:
                eprint(stderr_text)

        return _normalize_exit_code(proc.returncode)

    except FileNotFoundError:
        eprint("ERROR: codex CLI not found. Install: npm i -g @openai/codex")
        return 127
    except Exception as e:
        eprint(f"ERROR: Failed to run codex: {e}")
        return 1


def parse_args_with_passthrough(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Parse wrapper flags, collecting everything else as passthrough.

    Handles the `-` stdin marker to stop parsing.
    """
    wrapper_args = []
    passthrough_args = []
    i = 0
    wrapper_flags_with_value = {"--mode", "--collision", "--review-prompt", "--timeout", "--max-parallel"}
    wrapper_flags_no_value = {"--web-search", "--resume", "--persist", "--skip-git-repo-check", "--status"}

    while i < len(argv):
        arg = argv[i]

        if arg == "-":
            i += 1
            break

        # POSIX '--' end-of-options: consume it, route remaining to passthrough
        if arg == "--":
            i += 1
            while i < len(argv):
                if argv[i] == "-":
                    i += 1
                    break
                passthrough_args.append(argv[i])
                i += 1
            break

        if arg in wrapper_flags_with_value:
            wrapper_args.append(arg)
            if i + 1 < len(argv):
                wrapper_args.append(argv[i + 1])
                i += 2
            else:
                wrapper_args.append("")
                i += 1
        elif arg in wrapper_flags_no_value:
            wrapper_args.append(arg)
            i += 1
        else:
            passthrough_args.append(arg)
            i += 1

    # Anything after `-` goes to passthrough (shouldn't happen but be safe)
    while i < len(argv):
        passthrough_args.append(argv[i])
        i += 1

    parser = argparse.ArgumentParser(
        description="Codex CLI sub-agent wrapper",
        add_help=False,
    )
    parser.add_argument("--mode", default="read-only", choices=list(VALID_MODES))
    parser.add_argument("--collision", default="high", choices=list(VALID_COLLISIONS))
    parser.add_argument("--web-search", action="store_true", dest="web_search")
    parser.add_argument("--review-prompt", default=None, dest="review_prompt")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--skip-git-repo-check", action="store_true", dest="skip_git_repo_check")
    parser.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL, dest="max_parallel")
    parser.add_argument("--status", action="store_true")

    parsed = parser.parse_args(wrapper_args)

    return parsed, passthrough_args


def main() -> None:
    args, passthrough = parse_args_with_passthrough(sys.argv[1:])

    # ========== STATUS CHECK (early exit) ==========
    if args.status:
        print_status()
        return

    # ========== INPUT VALIDATION ==========
    if args.timeout not in VALID_TIMEOUTS:
        eprint(
            f"ERROR: --timeout must be 300, 600, 1200, or 2400 (seconds). Got: {args.timeout}"
        )
        sys.exit(2)

    if args.mode == "write" and not args.resume:
        if args.collision not in VALID_COLLISIONS:
            eprint(
                f"ERROR: --collision must be 'high' or 'medium'. Got: {args.collision}\n"
                "Low confidence = do NOT delegate writes. Use --mode read-only instead."
            )
            sys.exit(2)

    # ========== PARALLEL LIMIT ==========
    if args.max_parallel < 1:
        eprint("ERROR: --max-parallel must be >= 1.")
        sys.exit(2)
    if args.max_parallel > DEFAULT_MAX_PARALLEL:
        eprint(
            f"WARNING: --max-parallel {args.max_parallel} exceeds the default limit of "
            f"{DEFAULT_MAX_PARALLEL}. This is NOT RECOMMENDED — it increases resource usage, "
            "cost, and system load. Proceeding anyway."
        )
    enforce_parallel_limit(args.max_parallel, mode=args.mode)

    # ========== SAFETY SCAN ==========
    scan_for_dangerous_flags(passthrough)

    # ========== VERSION GATE ==========
    check_version()

    # ========== TEMP DIR ==========
    tmpdir = create_temp_dir()
    result_file = os.path.join(tmpdir, "result.txt")

    # ========== BUILD PROMPT (before worktree to avoid orphans on failure) ==========
    prompt_file = build_prompt_file(tmpdir, args.review_prompt)

    # ========== PROMPT VALIDATION ==========
    prompt_size = os.path.getsize(prompt_file)
    if prompt_size == 0:
        eprint("ERROR: Empty prompt. Pipe prompt content via stdin: echo '<prompt>' | run_codex.py ... -")
        sys.exit(2)
    if prompt_size > MAX_PROMPT_CHARS:
        eprint(f"WARNING: Prompt is very large ({prompt_size} chars). Consider trimming context.")

    # ========== GIT WORKTREE (after prompt validation to avoid orphans) ==========
    worktree_dir = None
    worktree_branch = None
    if not args.resume:
        worktree_dir, worktree_branch, _ = setup_worktree(args.collision, args.mode)

    # ========== BUILD CODEX ARGS ==========
    codex_args = build_codex_args(
        mode=args.mode,
        resume=args.resume,
        persist=args.persist,
        web_search=args.web_search,
        skip_git_repo_check=args.skip_git_repo_check,
        result_file=result_file,
        worktree_dir=worktree_dir,
        passthrough=passthrough,
    )

    # ========== RUN CODEX ==========
    exit_code = run_codex(codex_args, prompt_file, args.timeout)

    # ========== OUTPUT ==========
    # Always print result file path (even on failure — may contain partial results)
    print(result_file)
    if worktree_branch:
        print(f"WORKTREE_BRANCH={worktree_branch}")
        print(f"WORKTREE_DIR={worktree_dir}")

    if exit_code != 0:
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        eprint(f"EXIT_CODE={exit_code} — see {skill_dir}/references/ERROR_HANDLING.md")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
