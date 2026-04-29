# Migrating DART from pip/venv to uv

## What changes

| File | Action |
|---|---|
| `requirements.txt` | Keep as-is (for reference), but no longer used |
| `pyproject.toml` | **New** — uv reads dependencies from here |
| `update.bat` | Replaced — uses `uv sync` instead of `pip install` |
| `server.bat` | Replaced — uses `uv run` instead of activating venv |
| `start_dart.bat` | Minimal change — now calls updated `update.bat`/`server.bat` |

## Steps

### 1. Install uv (once, on each machine)

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
```

Or via pip if you prefer:
```
pip install uv
```

### 2. Replace files

Copy the provided files into the root of your DART checkout, overwriting the originals:

- `pyproject.toml`
- `update.bat`
- `server.bat`
- `start_dart.bat`

### 3. Remove the old virtual environment (optional but recommended)

```
rmdir /s /q dart_env
```

uv will create a `.venv` directory instead.

### 4. Run the application as normal

```
start_dart.bat
```

uv will automatically create `.venv`, install all dependencies from `pyproject.toml`, and start the server.

## Key differences

- **No manual `venv` activation** — `uv run` handles it automatically.
- **`uv sync`** replaces `pip install -r requirements.txt`. It installs exactly what's in `pyproject.toml` and produces a `uv.lock` file for reproducible installs.
- **`.venv`** is the new virtual environment folder (was `dart_env`). You may want to add `.venv` to `.gitignore` if it isn't already.
- **`uv.lock`** will be created automatically. Commit it to git to pin exact versions for your team.

## Keeping requirements.txt in sync (optional)

If you still need `requirements.txt` for other tooling, you can regenerate it from uv:

```
uv export --no-hashes > requirements.txt
```

## Troubleshooting

**`uv` not found after install**
Close and reopen your command window so the updated PATH takes effect, or run:
```
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
```

**cx_Oracle / C++ Build Tools error**
This is unchanged from before — cx_Oracle still requires Microsoft C++ Build Tools and Oracle Instant Client. See the README for details.
