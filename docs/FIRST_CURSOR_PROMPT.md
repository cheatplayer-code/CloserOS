# First Cursor Prompt

Paste the prompt below into Cursor Agent while the `CloserOS` project root is open.

```text
You are working in the CloserOS repository.

Before doing anything:
1. Read AGENTS.md.
2. Read PROJECT_STATUS.md.
3. Read TASKS.md.
4. Read docs/ARCHITECTURE.md, docs/SECURITY_COMPLIANCE.md,
   docs/DEVELOPMENT_WORKFLOW.md, and docs/DEFINITION_OF_DONE.md.
5. Inspect the entire current repository.

Work only on task CLS-001: Initialize monorepo.

First produce a concrete plan. Do not write code until the plan includes:
- exact directory structure;
- pinned Python and Node versions;
- package/dependency management choices;
- root commands;
- formatting, linting, type-checking, and test tools;
- CI implications;
- security and secret-handling implications;
- acceptance criteria mapped to checks.

Constraints:
- modular monolith;
- apps/web uses Next.js + TypeScript strict mode;
- apps/api and apps/worker use Python 3.12+, FastAPI/Pydantic-compatible structure;
- do not implement product features;
- do not add PostgreSQL or Redis yet; that is CLS-002;
- do not use microservices or Kubernetes;
- do not add paid services;
- never create or commit secrets;
- keep the initial scaffold minimal and executable.

After I approve the plan:
- implement CLS-001;
- run every available check;
- fix failures;
- update PROJECT_STATUS.md;
- report changed files, commands run, results, and remaining risks.

Do not claim production readiness.
```

## Prompt after CLS-001 passes

```text
Read AGENTS.md and the current project status.
Work only on CLS-002.
Inspect the repository first, produce a plan with acceptance criteria,
wait for approval, then implement and test it.
Do not modify unrelated architecture or begin product features.
```
