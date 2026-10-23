# Does the frontend ignore an unknown frame type? (T047)

Read-only, 2026-10-23, `cuems-frontend` `feat/xml-refactor` (`HEAD` of the working checkout; no file edited):

- `src/app/services/websocket.service.ts:52` — `if (response && response.type === 'error') { … this.errors.next(errorPayload); … }`
- `src/app/services/websocket.service.ts:72` — otherwise `this.messages.next(response)`; `messages` is a `Subject<any>` (`:24`).
- Consumers match by `type`, e.g. `src/app/components/projects/project-show/project-show.component.ts:139`
  (`response.type === 'project_ready' && …`).

Conclusion: a `media_check_report` frame reaches the `messages` Subject and no component acts on it. The editor may land before the
frontend's reconciliation absorbs `media-check.service.ts` from `origin/dev`.
