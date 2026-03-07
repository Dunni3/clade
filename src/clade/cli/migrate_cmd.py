"""clade migrate — export/import Hearth data between Clade instances."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx


DEFAULT_INCLUDE = {"cards", "morsels"}
NEVER_EXPORT = {"api_keys", "ember_registry"}


def _resolve_include(include: str | None, exclude: str | None) -> set[str]:
    """Resolve the final set of tables to export.

    Priority:
    - If --include is given, use that set explicitly.
    - Otherwise start from DEFAULT_INCLUDE and apply --exclude.
    - NEVER_EXPORT tables are always removed.
    """
    valid = {"cards", "morsels", "tasks", "messages"}

    if include:
        tables = {t.strip() for t in include.split(",") if t.strip()}
        tables = tables & valid
    else:
        tables = set(DEFAULT_INCLUDE)

    if exclude:
        removals = {t.strip() for t in exclude.split(",") if t.strip()}
        tables -= removals

    tables -= NEVER_EXPORT
    return tables


def _strip_dead_links(data: dict) -> dict:
    """Remove links that reference objects not present in the export payload.

    This is applied before import to avoid dangling link entries.
    Trees are never exported so all tree links are stripped.
    """
    included_ids: dict[str, set[str]] = {
        "task": {str(t["id"]) for t in data.get("tasks", [])},
        "morsel": {str(m["id"]) for m in data.get("morsels", [])},
        "card": {str(c["id"]) for c in data.get("cards", [])},
        "message": {str(m["id"]) for m in data.get("messages", [])},
        "tree": set(),
    }

    def keep(link: dict) -> bool:
        obj_type = link.get("object_type", "")
        obj_id = str(link.get("object_id", ""))
        return obj_id in included_ids.get(obj_type, set())

    for card in data.get("cards", []):
        card["links"] = [lnk for lnk in card.get("links", []) if keep(lnk)]
    for morsel in data.get("morsels", []):
        morsel["links"] = [lnk for lnk in morsel.get("links", []) if keep(lnk)]

    return data


def _get_client(hearth_url: str, api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=hearth_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}"},
        verify=False,
        timeout=30,
    )


def _paginate(client: httpx.Client, path: str, extra_params: dict | None = None) -> list[dict]:
    """Fetch all records from a paginated list endpoint."""
    results: list[dict] = []
    offset = 0
    limit = 200
    while True:
        params: dict = {"limit": limit, "offset": offset}
        if extra_params:
            params.update(extra_params)
        resp = client.get(path, params=params)
        resp.raise_for_status()
        batch: list[dict] = resp.json()
        results.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return results


@click.group()
def migrate() -> None:
    """Export/import Hearth data for migration between Clade instances."""


@migrate.command("export")
@click.option(
    "--output", "-o",
    default="hearth-export.json",
    type=click.Path(),
    show_default=True,
    help="Output file path.",
)
@click.option(
    "--include",
    default=None,
    help="Comma-separated list of tables to export: cards,morsels,tasks,messages. Overrides default set.",
)
@click.option(
    "--exclude",
    default=None,
    help="Comma-separated list of tables to exclude from the default set.",
)
@click.option("--hearth-url", default=None, envvar="HEARTH_URL", help="Source Hearth URL.")
@click.option("--api-key", default=None, envvar="HEARTH_API_KEY", help="API key for source Hearth.")
@click.pass_context
def export_cmd(
    ctx: click.Context,
    output: str,
    include: str | None,
    exclude: str | None,
    hearth_url: str | None,
    api_key: str | None,
) -> None:
    """Export Hearth data (cards, morsels, ...) to a portable JSON file."""
    # Resolve credentials
    if not hearth_url or not api_key:
        from .clade_config import default_config_path, load_clade_config
        from .keys import load_keys, keys_path

        config_dir = ctx.obj.get("config_dir") if ctx.obj else None
        config = load_clade_config(default_config_path(config_dir))
        if config:
            hearth_url = hearth_url or config.server_url
            if not api_key:
                keys = load_keys(keys_path(config_dir))
                api_key = keys.get(config.personal_name)

    if not hearth_url:
        click.echo("Error: Hearth URL not configured. Set HEARTH_URL or run 'clade init'.", err=True)
        raise SystemExit(1)
    if not api_key:
        click.echo("Error: API key not configured. Set HEARTH_API_KEY or run 'clade init'.", err=True)
        raise SystemExit(1)

    tables = _resolve_include(include, exclude)
    if not tables:
        click.echo("Error: No tables selected for export.", err=True)
        raise SystemExit(1)

    click.echo(f"Exporting from {hearth_url}: {', '.join(sorted(tables))}")

    data: dict = {"cards": [], "morsels": [], "tasks": [], "messages": []}

    try:
        with _get_client(hearth_url, api_key) as client:
            if "cards" in tables:
                click.echo("  Fetching cards...", nl=False)
                cards = _paginate(client, "/api/v1/kanban/cards", {"include_archived": "true"})
                data["cards"] = cards
                click.echo(f" {len(cards)} records")

            if "morsels" in tables:
                click.echo("  Fetching morsels...", nl=False)
                morsels = _paginate(client, "/api/v1/morsels")
                data["morsels"] = morsels
                click.echo(f" {len(morsels)} records")

            if "tasks" in tables:
                click.echo("  Fetching tasks...", nl=False)
                # Tasks endpoint doesn't support offset — use large limit
                resp = client.get("/api/v1/tasks", params={"limit": 10000})
                resp.raise_for_status()
                tasks = resp.json()
                data["tasks"] = tasks
                click.echo(f" {len(tasks)} records")

            if "messages" in tables:
                click.echo("  Fetching messages...", nl=False)
                messages = _paginate(client, "/api/v1/messages/feed")
                data["messages"] = messages
                click.echo(f" {len(messages)} records")

    except httpx.HTTPStatusError as exc:
        click.echo(f"\nError: {exc.response.status_code} {exc.response.text}", err=True)
        raise SystemExit(1)
    except httpx.RequestError as exc:
        click.echo(f"\nError connecting to Hearth: {exc}", err=True)
        raise SystemExit(1)

    payload = {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_hearth": hearth_url,
        "data": data,
    }

    out_path = Path(output)
    out_path.write_text(json.dumps(payload, indent=2))
    total = sum(len(v) for v in data.values())
    click.echo(f"\nExported {total} records to {out_path}")


@migrate.command("import")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--hearth-url", default=None, envvar="HEARTH_URL", help="Target Hearth URL.")
@click.option("--api-key", default=None, envvar="HEARTH_API_KEY", help="API key for target Hearth.")
@click.option("--dry-run", is_flag=True, help="Parse and validate without actually importing.")
@click.pass_context
def import_cmd(
    ctx: click.Context,
    input_file: Path,
    hearth_url: str | None,
    api_key: str | None,
    dry_run: bool,
) -> None:
    """Import Hearth data from a JSON export file into the target Hearth."""
    # Load and validate the export file
    try:
        payload = json.loads(input_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        click.echo(f"Error reading {input_file}: {exc}", err=True)
        raise SystemExit(1)

    schema_version = payload.get("schema_version")
    if schema_version != 1:
        click.echo(f"Error: Unsupported schema_version {schema_version!r}. Only version 1 is supported.", err=True)
        raise SystemExit(1)

    source = payload.get("source_hearth", "unknown")
    exported_at = payload.get("exported_at", "unknown")
    data: dict = payload.get("data", {})

    cards = data.get("cards", [])
    morsels = data.get("morsels", [])
    tasks = data.get("tasks", [])
    messages = data.get("messages", [])

    click.echo(f"Export file: {input_file}")
    click.echo(f"  Source:      {source}")
    click.echo(f"  Exported at: {exported_at}")
    click.echo(f"  Cards:    {len(cards)}")
    click.echo(f"  Morsels:  {len(morsels)}")
    click.echo(f"  Tasks:    {len(tasks)}")
    click.echo(f"  Messages: {len(messages)}")

    # Strip dead links before import
    data = _strip_dead_links(data)

    if dry_run:
        click.echo("\nDry run — no data imported.")
        return

    # Resolve credentials
    if not hearth_url or not api_key:
        from .clade_config import default_config_path, load_clade_config
        from .keys import load_keys, keys_path

        config_dir = ctx.obj.get("config_dir") if ctx.obj else None
        config = load_clade_config(default_config_path(config_dir))
        if config:
            hearth_url = hearth_url or config.server_url
            if not api_key:
                keys = load_keys(keys_path(config_dir))
                api_key = keys.get(config.personal_name)

    if not hearth_url:
        click.echo("Error: Hearth URL not configured. Set HEARTH_URL or run 'clade init'.", err=True)
        raise SystemExit(1)
    if not api_key:
        click.echo("Error: API key not configured. Set HEARTH_API_KEY or run 'clade init'.", err=True)
        raise SystemExit(1)

    import_payload = {
        "schema_version": schema_version,
        "exported_at": exported_at,
        "source_hearth": source,
        "data": {
            "cards": data.get("cards", []),
            "morsels": data.get("morsels", []),
            "tasks": data.get("tasks", []),
            "messages": data.get("messages", []),
        },
    }

    click.echo(f"\nImporting to {hearth_url}...")
    try:
        with _get_client(hearth_url, api_key) as client:
            resp = client.post("/api/v1/migrate/import", json=import_payload, timeout=120)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        click.echo(f"Error: {exc.response.status_code} {exc.response.text}", err=True)
        raise SystemExit(1)
    except httpx.RequestError as exc:
        click.echo(f"Error connecting to Hearth: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"  Imported cards:    {result.get('imported_cards', 0)}")
    click.echo(f"  Imported morsels:  {result.get('imported_morsels', 0)}")
    click.echo(f"  Imported tasks:    {result.get('imported_tasks', 0)}")
    click.echo(f"  Imported messages: {result.get('imported_messages', 0)}")

    errors = result.get("errors", [])
    if errors:
        click.echo(f"\n{len(errors)} error(s):", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
    else:
        click.echo("\nImport complete.")
