extract_originals.py

Purpose:
- For each mod `.txt` file under `mod_root/common`, create an `original_<basename>` file next to it containing the matching base-game file(s) from the Stellaris install.

Usage (simple .env-driven):

1. Copy the example `.env.example` to `.env` and edit the two paths inside:

```powershell
cd tools
copy .env.example .env
# then edit .env with your MOD_ROOT and STELLARIS_ROOT
2. Run the extractor from the workspace root (no args needed):

2. Run the extractor from the workspace root (no args needed):

```powershell
.\tools\run_extract.ps1
# or use the PowerShell helper
.\n\tools\run_extract.ps1
```

Notes:
- By default the script writes outputs to a sibling folder next to your `MOD_ROOT`, named `<MOD_FOLDER>_originals`. You can set `OUTPUT_ROOT` in `.env` to choose a different output location.
- The script will NOT create or modify files inside your `MOD_ROOT`.
- The script first tries to find the exact same relative path under `stellaris_root/common`.
- If that fails it searches the entire `stellaris_root/common` tree for files with the same filename and concatenates them.
- If no matches are found, it writes a small placeholder `original_...` file noting the miss.
By default each run creates a new timestamped output folder. To change the base
output location set `OUTPUT_ROOT` in `.env` (a timestamp will still be appended).
