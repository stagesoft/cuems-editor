# Stray sweep — 2026-10-23

Command: git rev-list --no-merges <ref> ^HEAD ^origin/debian/bookworm

| Ref | Unique commits | Verdict |
|---|---|---|
| origin/debian/869fat84r-utils-floor | 0 | none needed: no unique commits |
| origin/docker | 10 | exclude: abandoned container experiments (2025-03) |
| origin/engine | 2 | exclude: historic (2020) |
| origin/export | 0 | none needed: no unique commits |
| origin/feat/869fat84r-media-dimensions | 0 | none needed: no unique commits |
| origin/feat/node-identity | 0 | none needed: no unique commits |
| origin/feat/nodelist-adoption-api | 0 | none needed: no unique commits |
| origin/feature/gh-pages | 0 | none needed: no unique commits |
| origin/feature/pynng | 0 | none needed: no unique commits |
| origin/fix/ctimecode-migration | 0 | none needed: no unique commits |
| origin/fix/media-duration-extraction | 0 | none needed: no unique commits |
| origin/fix/media-upload-trash-name-collision | 0 | none needed: no unique commits |
| origin/fix/mtc-bias-compensation | 0 | none needed: no unique commits |
| origin/gh-pages | 1 | exclude: MkDocs deploy output |
| origin/integ/rc1-5-node-adoption | 1 | exclude: 0.1.0rc1-5+nodeadopt2 rig build, not a release; content shipped in rc1-7 |
| origin/main | 0 | none needed: no unique commits |
| origin/master | 0 | none needed: no unique commits |
| origin/media_duration_hack | 1 | exclude: pre-src/ layout, duration work already an ancestor via fix/media-duration-extraction |
| origin/mising_media_refs | 0 | none needed: no unique commits |
| origin/old-docker | 12 | exclude: abandoned container experiments (2025-03) |
| origin/pre_release_1 | 0 | none needed: no unique commits |
| origin/proto-node | 0 | none needed: no unique commits |
| origin/rc1 | 0 | none needed: no unique commits |
| origin/release/0.1.0rc1-4 | 0 | none needed: no unique commits |
| origin/release/0.1.0rc1-5 | 0 | none needed: no unique commits |
| origin/release/0.1.0rc1-7 | 0 | none needed: no unique commits |
| origin/server | 0 | none needed: no unique commits |
| origin/sessions | 0 | none needed: no unique commits |
| origin/subprocess | 0 | none needed: no unique commits |
| origin/thread | 0 | none needed: no unique commits |

## Released headers over every branch and tag

```
cuems-editor (0.1.0rc1-1)
cuems-editor (0.1.0rc1-2)
cuems-editor (0.1.0rc1-3)
cuems-editor (0.1.0rc1-4)
cuems-editor (0.1.0rc1-5)
cuems-editor (0.1.0rc1-5+nodeadopt2)
cuems-editor (0.1.0rc1-6)
cuems-editor (0.1.0rc1-7)
cuems-editor (0.1.1-1)
```

Union: 0.1.0rc1-1..-7 released; 0.1.0rc1-5+nodeadopt2 (rig build, excluded); 0.1.1-1. No hotfix line with released entries on neither branch.

Tags: img_a1 post_mtc_fix pre_mtc_fix pre-*-merge: rollback markers, not releases. v0.1.0rc1-4..-7 are ancestors of bookworm.
