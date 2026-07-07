# GitHub Sync Workflow

## First-Time Remote Setup

After creating an empty repository on GitHub, copy its HTTPS URL, then run:

```powershell
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

The `-u origin main` option remembers the default remote branch. After that, `git push` and `git pull` are usually enough.

## Daily Workflow

Before editing:

```powershell
git pull
```

After editing:

```powershell
git status
git diff
git add <files>
git commit -m "Short description of the change"
git push
```

## Useful Checks

Show connected remotes:

```powershell
git remote -v
```

Show recent history:

```powershell
git log --oneline -5
```

Show local branch and changed files:

```powershell
git status --short --branch
```

## Notes

- Do not commit large datasets, model checkpoints, or generated experiment folders unless they are intentionally small summaries.
- Keep code, configs, scripts, documentation, and compact result ledgers in Git.
- Put large artifacts in external storage and record their paths or download instructions in documentation.

