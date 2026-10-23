# CI gate (T068, T069)

**Status: BLOCKED on a maintainer act.** `workflow_dispatch` runs only workflows present on the default branch, and `main`
(`45e6cba`, 2021-05-20) has no `.github/` at all (`gh api repos/stagesoft/cuems-editor/contents/.github/workflows?ref=main` → 404).

## The request (T068)

Land **only** `.github/workflows/ci.yml`, byte for byte as on the branch `003-release-line-reconciliation` (commit
`1a2fdc1` or later), on `main`, for example:

```bash
git switch main && git checkout 003-release-line-reconciliation -- .github/workflows/ci.yml
git commit -S -m "ci: the pre-publication gate (workflow_dispatch)" && git push origin main
```

(`main` is unprotected and has no open PRs; a PR is equally fine.) Nothing else from the branch goes to `main`.

## Then (T069)

```bash
gh workflow run ci.yml --ref 003-release-line-reconciliation -f cuemsutils_ref=xml-refactor-merge-candidate
gh run watch
```

Record here: the run URL, the editor SHA, `cuemsutils_ref` and its resolved commit, the `gate-summary` text, and the strict-xfail
list. A second run on the post-merge `feat/xml-refactor` head with the cuems-utils **re-cut** tag is the maintainer's
pre-publication gate; it turns the five strict xfails XPASS (red) and the markers are removed (CLAUDE.md).

| Field | Value |
|---|---|
| Run URL | _not yet run_ |
