# Hearth Migration Guide

How to export data from one Hearth instance and import it into another. Use this when rebuilding the EC2 instance, moving regions, or setting up a fresh Hearth.

## What Gets Migrated

| Table | Exported by default | Notes |
|-------|-------------------|-------|
| `cards` | Yes | Kanban board cards + links |
| `morsels` | Yes | Tagged notes + links |
| `tasks` | No (opt-in) | Task history |
| `messages` | No (opt-in) | Hearth message feed |
| `api_keys` | Never | Re-register manually after migration |
| `ember_registry` | Never | Re-registers automatically when Ember starts |

Dead links (references to objects not included in the export) are stripped automatically on import.

## Basic Procedure

### 1. Export from the old Hearth

```bash
clade migrate export -o hearth-export.json
```

This reads credentials from `~/.config/clade/clade.yaml` + `keys.json`. To export everything:

```bash
clade migrate export --include cards,morsels,tasks,messages -o hearth-export.json
```

Verify the export:

```bash
clade migrate import hearth-export.json --dry-run
```

### 2. Stand up the new Hearth

Follow the standard rebuild procedure (`clade deploy hearth`, `clade deploy frontend`, register API keys, etc.). The new Hearth should be healthy and empty before importing.

Update `~/.config/clade/clade.yaml` with the new `server_url` if the address changed.

### 3. Import into the new Hearth

```bash
clade migrate import hearth-export.json
```

Output shows counts per table and any per-record errors. Import is idempotent — re-running the same file is safe (uses `INSERT OR IGNORE` on original IDs).

## Options

### export

```
clade migrate export [OPTIONS]

  -o, --output PATH       Output file (default: hearth-export.json)
  --include TABLES        Comma-separated: cards,morsels,tasks,messages
                          (overrides default set)
  --exclude TABLES        Remove tables from the default set
  --hearth-url URL        Override HEARTH_URL
  --api-key KEY           Override HEARTH_API_KEY
```

### import

```
clade migrate import [OPTIONS] INPUT_FILE

  --dry-run               Parse and validate without importing
  --hearth-url URL        Override HEARTH_URL
  --api-key KEY           Override HEARTH_API_KEY
```

## Pointing at a Different Hearth

All commands read `HEARTH_URL` / `HEARTH_API_KEY` from env or clade config. To export from one instance and import into another in one session:

```bash
# Export from old
HEARTH_URL=https://old-ip HEARTH_API_KEY=oldkey clade migrate export -o export.json

# Import into new (after updating clade.yaml, or with explicit flags)
clade migrate import export.json --hearth-url https://new-ip --api-key newkey
```

## Notes

- `api_keys` are never exported. After migration, re-register each brother's key manually or re-run `clade add-brother`.
- `ember_registry` entries are never exported. Each Ember auto-re-registers when its service starts.
- Task and message IDs are preserved on import. If the new Hearth already has conflicting IDs (e.g. from prior activity), those records are silently skipped.
- Trees are reconstructed from the imported tasks' `parent_task_id` / `root_task_id` columns — no separate tree export needed.
