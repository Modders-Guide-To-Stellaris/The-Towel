#!/usr/bin/env python3
"""
extract_originals.py

Purpose
-------
Create `original_<basename>` files next to mod `.txt` files by copying or
concatenating the corresponding base-game file(s) found under a Stellaris
installation's `common` tree.

How it finds originals
----------------------
- First it tries the exact same relative path under `STELLARIS_ROOT/common`.
- If that fails it searches `STELLARIS_ROOT/common` recursively for files with
    the same filename and concatenates any matches with a small header noting
    the original source path(s).
- If no match is found, a placeholder `original_...` file is written.

Simple usage (recommended)
--------------------------
1. Copy `tools/.env.example` → `tools/.env` and set `MOD_ROOT` and
     `STELLARIS_ROOT` inside (and `OVERWRITE=true` if you want to replace
     existing `original_` files).

2. Run the script (no args needed when `.env` is present):

     PowerShell:
             .\tools\run_extract.ps1

     or
             python tools\extract_originals.py

Command-line options
--------------------
- `--mod-root` and `--stellaris-root` — alternative to using `.env`.
- `--overwrite` — allow replacing existing `original_` files.
- `--env-file` — specify a custom .env location.

Be safe: the script will not overwrite existing `original_` files unless
`--overwrite` is set or `OVERWRITE=true` is in the `.env` file.
"""

import argparse
import os
import sys
from pathlib import Path
import shlex


def read_env_file(env_path: Path):
    """Simple .env parser: KEY=VALUE, ignore comments and blank lines."""
    data = {}
    if not env_path.exists():
        return data
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip().strip('"')
            # expand simple env vars
            val = os.path.expandvars(val)
            data[key] = val
    return data


def find_mod_files(mod_common_path):
    for root, dirs, files in os.walk(mod_common_path):
        for f in files:
            if f.lower().endswith('.txt'):
                yield Path(root) / f


def iter_top_level_blocks(content: str):
    """Yield (name, start_index, block_text) for each top-level
    `name = { ... }` entry in content. Tracks brace depth and skips
    `#` line-comments and "double-quoted" strings, so nested entries
    are never reported as top-level.
    """
    import re
    entry_re = re.compile(r'([A-Za-z0-9_@]+)\s*=\s*\{')
    L = len(content)
    i = 0
    depth = 0
    in_string = False
    pending_name = None
    pending_start = 0
    while i < L:
        c = content[i]
        if c == '"':
            in_string = not in_string
            i += 1
            continue
        if in_string:
            i += 1
            continue
        if c == '#':
            nl = content.find('\n', i)
            i = L if nl == -1 else nl + 1
            continue
        if c == '{':
            depth += 1
            i += 1
            continue
        if c == '}':
            if depth > 0:
                depth -= 1
            if depth == 0 and pending_name is not None:
                yield pending_name, pending_start, content[pending_start:i+1]
                pending_name = None
            i += 1
            continue
        if depth == 0 and pending_name is None and (c.isalpha() or c == '_' or c == '@'):
            # require token boundary on the left
            if i > 0 and (content[i-1].isalnum() or content[i-1] in '_@'):
                i += 1
                continue
            m = entry_re.match(content, i)
            if m:
                pending_name = m.group(1)
                ln_start = content.rfind('\n', 0, i)
                pending_start = 0 if ln_start == -1 else ln_start + 1
                i = m.end() - 1  # position of the '{'; main loop will count it
                continue
        i += 1


def extract_entries_from_mod(mod_file_path: Path):
    """Return ordered list of top-level entry names found in the mod file.
    Only entries at brace depth 0 are returned (nested keys are ignored).
    """
    with open(mod_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    return [name for name, _, _ in iter_top_level_blocks(content)]


def extract_block_from_content(content: str, brace_index: int):
    """Given the index of an opening brace in content, return the substring
    from the opening brace backwards to include the key and forward until the
    matching closing brace. Returns (start_index_for_key, block_text).
    """
    # find start of line (approx) to include key
    start = content.rfind('\n', 0, brace_index)
    start = 0 if start == -1 else start+1
    # now walk forward from brace_index to find matching brace
    i = brace_index
    depth = 0
    L = len(content)
    while i < L:
        c = content[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return start, content[start:i+1]
        i += 1
    # If we get here, braces didn't match; return from start to end
    return start, content[start:]


def search_entries_in_folder(folder: Path, entries: list):
    """Search top-level entries by name in all .txt files under `folder`.
    Returns dict {entry_name: [(file_path, block_text), ...]}.

    Only top-level (depth 0) blocks in vanilla files are considered, so a
    nested key with the same name will not be picked up.
    """
    result = {entry: [] for entry in entries}
    if not folder.exists() or not folder.is_dir():
        return result
    wanted = set(entries)
    for root, dirs, files in os.walk(folder):
        for f in files:
            if not f.lower().endswith('.txt'):
                continue
            fp = Path(root) / f
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as inf:
                    content = inf.read()
            except Exception:
                continue
            for name, _, block in iter_top_level_blocks(content):
                if name in wanted:
                    result[name].append((fp, block))
    return result


def write_entries_output(out_path: Path, entries: list, sources_map: dict):
    with open(out_path, 'w', encoding='utf-8') as outf:
        for entry in entries:
            outf.write(f"# === {entry} ===\n")
            found = sources_map.get(entry, [])
            if not found:
                outf.write(f"# ORIGINAL NOT FOUND in Stellaris for entry: {entry}\n\n")
                continue
            for src, block in found:
                outf.write(f"# ----- SOURCE: {src} -----\n")
                outf.write(block)
                outf.write('\n\n')
    return True


def try_exact_match(stellaris_root, relpath):
    candidate = Path(stellaris_root) / 'common' / relpath
    if candidate.exists():
        return [candidate]
    return []


def find_by_basename(stellaris_common_path, basename):
    matches = []
    for root, dirs, files in os.walk(stellaris_common_path):
        for f in files:
            if f == basename:
                matches.append(Path(root) / f)
    return matches


def safe_output_path(mod_file):
    base = mod_file.name
    out_name = f'original_{base}'
    out_path = mod_file.parent / out_name
    # if already exists, return path (script will respect overwrite flag)
    return out_path


def write_concatenated(out_path, sources, overwrite=False):
    if out_path.exists() and not overwrite:
        return False, f"exists: {out_path}"
    with open(out_path, 'w', encoding='utf-8') as outf:
        for src in sources:
            outf.write(f"# ----- SOURCE: {src} -----\n")
            try:
                with open(src, 'r', encoding='utf-8', errors='replace') as inf:
                    outf.write(inf.read())
            except Exception as e:
                outf.write(f"# ERROR READING SOURCE: {e}\n")
            outf.write('\n\n')
    return True, f"written: {out_path}"


def main():
    p = argparse.ArgumentParser(description='Extract original Stellaris files for mod files')
    p.add_argument('--mod-root', help='Path to mod folder (root containing "common").')
    p.add_argument('--stellaris-root', help='Path to Stellaris install root (root containing "common").')
    p.add_argument('--env-file', help='Path to .env file to read defaults from (optional)')
    args = p.parse_args()

    # Load env defaults from tools/.env if present, then override with CLI args
    env_path = Path(args.env_file) if args.env_file else (Path(__file__).parent / '.env')
    env = read_env_file(env_path)

    mod_root_val = args.mod_root or env.get('MOD_ROOT')
    stellaris_root_val = args.stellaris_root or env.get('STELLARIS_ROOT')

    if not mod_root_val or not stellaris_root_val:
        print('Error: both --mod-root and --stellaris-root must be provided, or set MOD_ROOT and STELLARIS_ROOT in a .env file.', file=sys.stderr)
        print(f'Checked env file: {env_path}')
        sys.exit(2)

    mod_root = Path(mod_root_val).expanduser().resolve()
    stellaris_root = Path(stellaris_root_val).expanduser().resolve()

    mod_common = mod_root / 'common'
    stellaris_common = stellaris_root / 'common'

    # Determine output root base: prefer OUTPUT_ROOT from env, else sibling folder
    import datetime
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    output_root_base_val = env.get('OUTPUT_ROOT')
    if output_root_base_val:
        output_root_base = Path(output_root_base_val).expanduser().resolve()
    else:
        output_root_base = mod_root.parent / f"{mod_root.name}_originals"

    # Append timestamp to ensure a fresh folder each run
    output_root = output_root_base.with_name(f"{output_root_base.name}_{timestamp}")

    # Safety: do not write output inside the mod root
    try:
        if output_root.resolve().is_relative_to(mod_root.resolve()):
            print(f'Error: OUTPUT_ROOT {output_root} must not be inside MOD_ROOT {mod_root}', file=sys.stderr)
            sys.exit(2)
    except Exception:
        try:
            output_root.resolve().relative_to(mod_root.resolve())
            print(f'Error: OUTPUT_ROOT {output_root} must not be inside MOD_ROOT {mod_root}', file=sys.stderr)
            sys.exit(2)
        except Exception:
            pass

    # ensure output root exists
    output_root.mkdir(parents=True, exist_ok=True)

    if not mod_common.exists():
        print(f'Error: mod common path not found: {mod_common}', file=sys.stderr)
        sys.exit(2)
    if not stellaris_common.exists():
        print(f'Error: Stellaris common path not found: {stellaris_common}', file=sys.stderr)
        sys.exit(2)

    created = []
    skipped = []
    notfound = []

    for mod_file in find_mod_files(mod_common):
        # Determine output path mirroring mod folder structure
        rel_full = mod_file.relative_to(mod_root)
        out_dir = output_root / rel_full.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f'original_{mod_file.name}'

        # Extract entry names from the mod file in order
        entries = extract_entries_from_mod(mod_file)
        if not entries:
            # nothing to look for; write a placeholder
            if out_path.exists():
                skipped.append(str(out_path))
                print(f'[SKIP] {out_path} exists (no entries found)')
            else:
                with open(out_path, 'w', encoding='utf-8') as outf:
                    outf.write(f"# No top-level entries found in mod file: {mod_file}\n")
                notfound.append(str(out_path))
                print(f'[MISSING] {out_path} (no entries in mod file)')
            continue

        # Search only inside the matching vanilla subfolder (same relative path).
        rel_dir = mod_file.parent.relative_to(mod_common)
        search_root = stellaris_common / rel_dir
        sources_map = search_entries_in_folder(search_root, entries)

        # Write combined output preserving the order of entries in the mod file
        write_entries_output(out_path, entries, sources_map)
        created.append(str(out_path))
        found_total = sum(len(v) for v in sources_map.values())
        print(f'[OK] {out_path} <- entries: {len(entries)}; originals found: {found_total} (in {search_root})')

    print('\nSummary:')
    print(f'  created: {len(created)}')
    print(f'  skipped (exists): {len(skipped)}')
    print(f'  missing originals written as placeholders: {len(notfound)}')

if __name__ == "__main__":
    main()
