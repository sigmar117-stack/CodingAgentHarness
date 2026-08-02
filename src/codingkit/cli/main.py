"""CLI commands (PLAN T4.2).  The 18 commands from SPEC §3.1 plus an
additional ``config status`` (19 leaf commands in total).

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


def _load_disabled_tools() -> set[str]:
    """Return the set of tool names disabled in the project config.

    Stored as a comma-separated ``disabled_tools`` line so it survives the
    trivial ``key: value`` parser.  Returns an empty set when none are
    configured.
    """
    raw = _load_config().get("disabled_tools", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _save_disabled_tools(names: set[str]) -> None:
    """Persist the disabled-tool set to the project config."""
    cfg = _load_config()
    cfg["disabled_tools"] = ",".join(sorted(names))
    _save_config(cfg)


def _build_registry():
    """Construct a ``ToolRegistry`` with the project's disabled tools applied.

    This is what makes ``codingkit tool disable`` take effect on the next
    ``codingkit run``: the disabled tools are omitted from the LLM's tool
    definitions and refused at execution time (see ``AgentLoop``).
    """
    registry = default_registry()
    for name in _load_disabled_tools():
        registry.disable(name)
    return registry


def _build_llm_client():
    """Build an LLM client from the project config and stored credentials.

    Returns ``(client, configured)`` where ``configured`` is ``True`` when a
    real provider key was available (so callers can give an honest message in
    plan-only mode).  When no key is available — e.g. a fresh checkout or the
    test environment — falls back to ``MockLLMClient`` so the loop still runs.
    """
    model = _load_config().get("default_model", "claude-sonnet-5")
    try:
        store = _get_credential_store()
        key = store.get("api_key")
    except typer.Exit:
        raise
    except Exception:
        key = None

    if not key:
        return MockLLMClient(model="mock"), False

    from codingkit.core.llm_factory import create_llm_client

    try:
        return create_llm_client(model, api_key=key), True
    except Exception:
        return MockLLMClient(model="mock"), False


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

    llm, _configured = _build_llm_client()
    registry = _build_registry()
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
    """Generate an LLM-backed plan for a task without executing it.

    When no API key is configured, we say so honestly instead of printing a
    hard-coded 4-step outline that pretends the agent "generated a plan".
    """
    typer.echo("\nPlan:")
    llm, configured = _build_llm_client()
    if not configured:
        typer.echo("  (No API key configured — cannot generate a real plan.)")
        typer.echo("  Run `codingkit config key set` to configure an API key, then")
        typer.echo("  re-run `codingkit run --plan-only` for an LLM-generated plan.")
        return

    prompt = (
        "You are a coding agent. Break the following task into 3-6 concrete, "
        "ordered steps (one per line, numbered). Do not implement — only plan.\n\n"
        f"Task: {task}"
    )
    try:
        resp = llm.generate([{"role": "user", "content": prompt}])
    except Exception as e:
        typer.echo(f"  (LLM call failed: {e})", err=True)
        return
    plan_text = (resp.content or "").strip()
    typer.echo(plan_text or "  (LLM returned no plan.)")


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
    from codingkit.core.llm_factory import list_known_models

    models = list_known_models()
    typer.echo("Available models:")
    for provider, provider_models in models.items():
        typer.echo(f"  {provider}:")
        for m in provider_models:
            typer.echo(f"    • {m}")
    typer.echo()
    typer.echo("Use `codingkit config model set <name>` to set the default.")
    typer.echo("Routing is by prefix, so a provider's newer model names also work.")


@model_app.command("set")
def model_set(
    model_name: str = typer.Argument(..., help="Model name to set as default"),
) -> None:
    """Set the default LLM model (persisted to .codingkit/config.yaml)."""
    from codingkit.core.llm_factory import known_prefixes

    # Prefix match is case-insensitive: providers use mixed-case model
    # names (e.g. ``MiniMax-M1``) but the factory lowercases internally.
    lowered = model_name.strip().lower()
    if not lowered.startswith(known_prefixes()):
        typer.echo(
            f"Warning: '{model_name}' is not a recognised model prefix. "
            f"Known prefixes: {', '.join(known_prefixes())}",
            err=True,
        )
        raise typer.Exit(1)
    cfg = _load_config()
    cfg["default_model"] = model_name
    _save_config(cfg)
    typer.echo(f"✅ Default model set to '{model_name}' (persisted to .codingkit/config.yaml).")


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
    """List all available tools and their enabled/disabled state."""
    registry = _build_registry()
    tools = registry.list_all()
    typer.echo(f"{'Name':<25} {'Risk Level':<15} Enabled")
    typer.echo("-" * 55)
    for tool in tools:
        risk = tool.risk_level.value
        enabled = "❌ disabled" if registry.is_disabled(tool.name) else "✅"
        typer.echo(f"{tool.name:<25} {risk:<15} {enabled}")
    typer.echo()
    ndis = len(registry.disabled_names())
    typer.echo(f"Total: {len(tools)} tools ({len(registry.dangerous_tools())} dangerous, {ndis} disabled)")


@tool_app.command()
def enable(
    tool_name: str = typer.Argument(..., help="Tool name to enable"),
) -> None:
    """Enable a tool (persisted to .codingkit/config.yaml)."""
    registry = default_registry()
    if registry.get(tool_name) is None:
        typer.echo(f"Error: unknown tool '{tool_name}'. Use `codingkit tool list` to see available tools.", err=True)
        raise typer.Exit(1)
    disabled = _load_disabled_tools()
    disabled.discard(tool_name)
    _save_disabled_tools(disabled)
    typer.echo(f"✅ Tool '{tool_name}' enabled (persisted). It will be available on the next `codingkit run`.")


@tool_app.command()
def disable(
    tool_name: str = typer.Argument(..., help="Tool name to disable"),
) -> None:
    """Disable a tool (persisted to .codingkit/config.yaml)."""
    registry = default_registry()
    if registry.get(tool_name) is None:
        typer.echo(f"Error: unknown tool '{tool_name}'. Use `codingkit tool list` to see available tools.", err=True)
        raise typer.Exit(1)
    disabled = _load_disabled_tools()
    disabled.add(tool_name)
    _save_disabled_tools(disabled)
    typer.echo(f"✅ Tool '{tool_name}' disabled (persisted). It will be refused on the next `codingkit run`.")


# ---------------------------------------------------------------------------
# Simple commands
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show current agent status (config, tools, last session)."""
    typer.echo("CodingKit Status:")
    typer.echo(f"  Version: {__version__}")

    cfg = _load_config()
    typer.echo(f"  Default model: {cfg.get('default_model', 'claude-sonnet-5')}")
    typer.echo(f"  Credential method: {cfg.get('credential_method', 'keychain')}")

    registry = _build_registry()
    ndis = len(registry.disabled_names())
    typer.echo(f"  Tools: {len(registry.list_all())} registered ({ndis} disabled)")

    # Surface the most recent saved session, if any.
    try:
        from codingkit.memory.session_store import SessionStore

        sessions = SessionStore().list_sessions()
    except Exception:
        sessions = []
    if sessions:
        last = sessions[0]
        typer.echo(
            f"  Last session: {str(last.get('session_id', '?'))[:12]}… "
            f"[{last.get('status', '?')}] {str(last.get('task_description', ''))[:40]}"
        )
        typer.echo("  State: idle (no task running in this process)")
    else:
        typer.echo("  State: idle (no sessions yet)")
    typer.echo("  Use `codingkit run <task>` to start a task.")


@app.command()
def cancel() -> None:
    """Cancel the current task.

    ``codingkit run`` runs in the foreground, so there is no concurrent task
    to cancel from a separate invocation.  This command reports honestly
    rather than pretending to act on a non-existent background task.
    """
    typer.echo("ℹ No running task to cancel.")
    typer.echo("  (`codingkit run` runs in the foreground; press Ctrl+C to interrupt it.)")


@app.command()
def version() -> None:
    """Show the CodingKit version."""
    typer.echo(f"CodingKit v{__version__}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()