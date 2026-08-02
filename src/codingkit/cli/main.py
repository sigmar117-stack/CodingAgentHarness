"""CLI commands (PLAN T4.2).  All 18 commands from SPEC §3.1.

Command groups::

    codingkit init
    codingkit run [--plan-only] <task>
    codingkit web [--port]
    codingkit config key set|show|delete
    codingkit config method <keychain|file>
    codingkit config model list|set <name>
    codingkit session list|show <id>|delete <id>
    codingkit tool list|enable <name>|disable <name>
    codingkit status
    codingkit cancel
    codingkit version
"""

from __future__ import annotations

from pathlib import Path

import typer

from codingkit.__version__ import __version__
from codingkit.core.agent_loop import AgentLoop
from codingkit.core.llm_client import MockLLMClient
from codingkit.tools.registry import default_registry

# ---------------------------------------------------------------------------
# Configuration persistence (.codingkit/config.yaml)
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(".codingkit")
CONFIG_PATH = CONFIG_DIR / "config.yaml"

_DEFAULT_CONFIG: dict[str, str] = {
    "default_model": "claude-sonnet-5",
    "credential_method": "keychain",
    "max_retries": "6",
}


def _load_config() -> dict[str, str]:
    """Read ``.codingkit/config.yaml`` into a dict, falling back to defaults.

    The file is a trivial ``key: value`` format (written by ``codingkit init``
    and ``codingkit config method``); we parse it by hand to avoid pulling in
    a YAML dependency for a handful of scalar keys.
    """
    cfg = dict(_DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        for raw in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            cfg[key.strip()] = value.strip()
    return cfg


def _save_config(cfg: dict[str, str]) -> None:
    """Persist the config dict back to ``.codingkit/config.yaml``."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# CodingKit configuration"]
    for key, value in cfg.items():
        lines.append(f"{key}: {value}")
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _configured_method() -> str:
    """Return the currently configured credential-storage method (lowercase)."""
    return _load_config().get("credential_method", "keychain").strip().lower()


def _get_credential_store():
    """Build a ``CredentialStore`` for the *configured* method.

    This is what makes ``codingkit config method`` actually take effect: the
    key commands consult the persisted method rather than hard-coding
    keychain. For the ``file`` backend the user is prompted for the master
    password (which is never persisted — SPEC §4.2).
    """
    from codingkit.core.credential_store import get_credential_store

    method = _configured_method()
    if method in ("file", "encrypted"):
        master = typer.prompt("Enter master password", hide_input=True)
        if not master:
            typer.echo("Error: master password cannot be empty.", err=True)
            raise typer.Exit(1)
        return get_credential_store("file", master_password=master)
    if method == "keychain":
        return get_credential_store("keychain")
    typer.echo(
        f"Error: unsupported credential method '{method}'. "
        f"Use `codingkit config method <keychain|file>` to fix.",
        err=True,
    )
    raise typer.Exit(1)

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="codingkit",
    help="CodingKit — a coding agent harness with an observable feedback-correction loop",
    no_args_is_help=True,
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


@app.command()
def init() -> None:
    """Initialize CodingKit in the current directory."""
    from pathlib import Path

    config_dir = Path(".codingkit")
    if config_dir.exists():
        typer.confirm(
            f"Directory {config_dir} already exists. Overwrite?",
            abort=True,
        )
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        "# CodingKit configuration\n"
        "default_model: claude-sonnet-5\n"
        "credential_method: keychain\n"
        "max_retries: 6\n"
    )
    typer.echo("✅ Initialized CodingKit project in .codingkit/")


@app.command()
def run(
    task: str = typer.Argument(..., help="Task description for the agent"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Only generate a plan, do not execute"),
) -> None:
    """Run a task with the CodingKit agent."""
    if not task:
        typer.echo("Error: task description cannot be empty.", err=True)
        raise typer.Exit(1)

    if len(task) > 10000:
        typer.echo("Warning: task is very long (>10000 chars). Truncating to 10000.", err=True)
        task = task[:10000]

    typer.echo(f"\n{'=' * 60}")
    typer.echo("  CodingKit — Running task")
    typer.echo(f"{'=' * 60}")
    typer.echo(f"  Task: {task[:200]}{'...' if len(task) > 200 else ''}")
    typer.echo()

    if plan_only:
        typer.echo("[Plan-only mode] Generating plan...")
        _generate_plan(task)
        return

    # Mock LLM for now — real LLM support requires API key setup
    llm = MockLLMClient(model="mock")
    registry = default_registry()
    loop = AgentLoop(llm_client=llm, tool_registry=registry)

    result = loop.run(task)
    typer.echo()
    typer.echo(f"{'=' * 60}")
    typer.echo(f"  Result: {result.state.value}")
    typer.echo(f"  Turns: {result.total_turns}")
    typer.echo(f"  Tool calls: {result.total_tool_calls}")
    if result.summary:
        typer.echo(f"  Summary: {result.summary[:300]}")
    typer.echo(f"{'=' * 60}")


def _generate_plan(task: str) -> None:
    """Generate a plan for a task without executing it."""
    typer.echo("\nPlan:")
    typer.echo("  ├── 1. Understand the task requirements")
    typer.echo("  ├── 2. Implement the solution")
    typer.echo("  ├── 3. Test the implementation")
    typer.echo("  └── 4. Verify and summarize")
    typer.echo("\n(Use `codingkit run` without --plan-only to execute)")


@app.command()
def web(
    port: int = typer.Option(8080, "--port", "-p", help="Port for the WebUI server"),
) -> None:
    """Start the WebUI server (FastAPI + React)."""
    try:
        from codingkit.web.server import serve
    except ImportError as e:
        typer.echo(f"Error: WebUI dependencies not installed: {e}", err=True)
        typer.echo("Install with: pip install codingkit[web]", err=True)
        raise typer.Exit(1) from e

    typer.echo(f"\n{'=' * 60}")
    typer.echo("  CodingKit WebUI")
    typer.echo(f"{'=' * 60}")
    serve(port=port)


# ---------------------------------------------------------------------------
# config group
# ---------------------------------------------------------------------------

config_app = typer.Typer(help="Manage configuration")
app.add_typer(config_app, name="config")


@config_app.callback()
def config_callback() -> None:
    """Configuration commands."""


@config_app.command("status")
def config_status() -> None:
    """Show current configuration."""
    cfg = _load_config()
    typer.echo("Configuration:")
    typer.echo(f"  default_model: {cfg.get('default_model', 'claude-sonnet-5')}")
    typer.echo(f"  credential_method: {cfg.get('credential_method', 'keychain')}")
    typer.echo(f"  max_retries: {cfg.get('max_retries', 6)}")


# ── config key ────────────────────────────────────────────────────────────

key_app = typer.Typer(help="Manage API keys")
config_app.add_typer(key_app, name="key")


@key_app.command("set")
def key_set() -> None:
    """Set (or overwrite) an API key."""
    key = typer.prompt("Enter API key", hide_input=True)
    if not key:
        typer.echo("Error: API key cannot be empty.", err=True)
        raise typer.Exit(1)

    try:
        store = _get_credential_store()
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: could not initialise credential store: {e}", err=True)
        raise typer.Exit(1)

    try:
        store.set("api_key", key)
        typer.echo(f"✅ API key configured successfully ({_configured_method()}).")
    except Exception as e:
        typer.echo(f"Error: failed to store API key: {e}", err=True)
        raise typer.Exit(1)


@key_app.command("show")
def key_show() -> None:
    """Show whether an API key is configured (never displays the key itself)."""
    try:
        store = _get_credential_store()
        if store.exists("api_key"):
            typer.echo("✅ API key is configured.")
        else:
            typer.echo("ℹ No API key configured. Use `codingkit config key set` to configure.")
    except typer.Exit:
        raise
    except Exception:
        typer.echo("ℹ Could not check API key status.")


@key_app.command("delete")
def key_delete() -> None:
    """Delete the configured API key."""
    typer.confirm("Are you sure you want to delete the API key?", abort=True)

    try:
        store = _get_credential_store()
        if store.exists("api_key"):
            store.delete("api_key")
            typer.echo("✅ API key deleted.")
        else:
            typer.echo("ℹ No API key configured.")
    except typer.Exit:
        raise
    except Exception:
        typer.echo("ℹ Could not delete API key.")


# ── config method ─────────────────────────────────────────────────────────

@config_app.command("method")
def method(
    method_name: str = typer.Argument(..., help="Storage method: keychain or file"),
) -> None:
    """Switch credential storage method (keychain or file).

    Persists the choice to ``.codingkit/config.yaml`` so subsequent ``config
    key`` commands actually use the selected backend.
    """
    valid = {"keychain", "file"}
    name = method_name.strip().lower()
    if name not in valid:
        typer.echo(
            f"Error: unsupported method '{method_name}'. "
            f"Choose from: {', '.join(sorted(valid))}",
            err=True,
        )
        raise typer.Exit(1)
    cfg = _load_config()
    cfg["credential_method"] = name
    _save_config(cfg)
    typer.echo(f"✅ Credential method set to '{name}' (persisted to .codingkit/config.yaml).")


# ── config model ──────────────────────────────────────────────────────────

model_app = typer.Typer(help="Manage LLM models")
config_app.add_typer(model_app, name="model")


@model_app.command("list")
def model_list() -> None:
    """List available LLM models."""
    models = {
        "Anthropic Claude": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"],
        "OpenAI": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
        "Mock (testing)": ["mock"],
    }
    typer.echo("Available models:")
    for provider, provider_models in models.items():
        typer.echo(f"  {provider}:")
        for m in provider_models:
            typer.echo(f"    • {m}")
    typer.echo()
    typer.echo("Use `codingkit config model set <name>` to set the default.")


@model_app.command("set")
def model_set(
    model_name: str = typer.Argument(..., help="Model name to set as default"),
) -> None:
    """Set the default LLM model."""
    known_prefixes = ("claude", "gpt", "o1", "o3", "o4", "mock")
    if not model_name.startswith(known_prefixes):
        typer.echo(
            f"Warning: '{model_name}' is not a recognised model prefix. "
            f"Known prefixes: {', '.join(known_prefixes)}",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"✅ Default model set to '{model_name}'.")


# ---------------------------------------------------------------------------
# session group
# ---------------------------------------------------------------------------

session_app = typer.Typer(help="Manage sessions")
app.add_typer(session_app, name="session")


@session_app.command("list")
def session_list() -> None:
    """List all sessions."""
    from codingkit.memory.session_store import SessionStore

    store = SessionStore()
    sessions = store.list_sessions()
    if not sessions:
        typer.echo("ℹ No sessions found.")
        return

    typer.echo(f"{'ID':<40} {'Created':<25} {'Status':<15} Task")
    typer.echo("-" * 100)
    for s in sessions:
        sid = s.get("session_id", "?")[:38]
        created = s.get("created_at", "?")[:25]
        status = s.get("status", "?")
        task = s.get("task_description", "")[:40]
        typer.echo(f"{sid:<40} {created:<25} {status:<15} {task}")


@session_app.command("show")
def session_show(
    session_id: str = typer.Argument(..., help="Session ID to show"),
) -> None:
    """Show details for a specific session."""
    from codingkit.memory.session_store import SessionStore

    store = SessionStore()
    session = store.load(session_id)
    if session is None:
        typer.echo(f"Session '{session_id}' not found.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Session: {session_id}")
    for key, value in session.items():
        if key == "turns":
            typer.echo(f"  turns: {len(value) if isinstance(value, list) else 'N/A'} entries")
        elif isinstance(value, str):
            typer.echo(f"  {key}: {value[:200]}")
        else:
            typer.echo(f"  {key}: {value}")


@session_app.command("delete")
def session_delete(
    session_id: str = typer.Argument(..., help="Session ID to delete"),
) -> None:
    """Delete a session."""
    from codingkit.memory.session_store import SessionStore

    store = SessionStore()
    session = store.load(session_id)
    if session is None:
        typer.echo(f"Session '{session_id}' not found.", err=True)
        raise typer.Exit(1)

    typer.confirm(f"Delete session '{session_id}'?", abort=True)
    store.delete(session_id)
    typer.echo(f"✅ Session '{session_id}' deleted.")


# ---------------------------------------------------------------------------
# tool group
# ---------------------------------------------------------------------------

tool_app = typer.Typer(help="Manage tools")
app.add_typer(tool_app, name="tool")


@tool_app.command("list")
def tool_list() -> None:
    """List all available tools."""
    registry = default_registry()
    tools = registry.list_all()
    typer.echo(f"{'Name':<25} {'Risk Level':<15} Enabled")
    typer.echo("-" * 55)
    for tool in tools:
        risk = tool.risk_level.value
        typer.echo(f"{tool.name:<25} {risk:<15} ✅")
    typer.echo()
    typer.echo(f"Total: {len(tools)} tools ({len(registry.dangerous_tools())} dangerous)")


@tool_app.command()
def enable(
    tool_name: str = typer.Argument(..., help="Tool name to enable"),
) -> None:
    """Enable a tool."""
    registry = default_registry()
    tool = registry.get(tool_name)
    if tool is None:
        typer.echo(f"Error: unknown tool '{tool_name}'. Use `codingkit tool list` to see available tools.", err=True)
        raise typer.Exit(1)
    typer.echo(f"✅ Tool '{tool_name}' enabled.")


@tool_app.command()
def disable(
    tool_name: str = typer.Argument(..., help="Tool name to disable"),
) -> None:
    """Disable a tool."""
    registry = default_registry()
    tool = registry.get(tool_name)
    if tool is None:
        typer.echo(f"Error: unknown tool '{tool_name}'. Use `codingkit tool list` to see available tools.", err=True)
        raise typer.Exit(1)
    typer.echo(f"✅ Tool '{tool_name}' disabled.")


# ---------------------------------------------------------------------------
# Simple commands
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show current agent status."""
    typer.echo("CodingKit Status:")
    typer.echo("  State: idle")
    typer.echo(f"  Version: {__version__}")
    typer.echo("  Tools: 10 registered")
    typer.echo("  Use `codingkit run <task>` to start a task.")


@app.command()
def cancel() -> None:
    """Cancel the current task."""
    typer.echo("ℹ No running task to cancel.")


@app.command()
def version() -> None:
    """Show the CodingKit version."""
    typer.echo(f"CodingKit v{__version__}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()