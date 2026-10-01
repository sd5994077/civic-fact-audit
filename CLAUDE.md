@AGENTS.md

## Claude-specific notes

- This project had no CLAUDE.md before 2026-09-17 -- meaning Claude Code
  CLI sessions here were never actually reading AGENTS.md's rules. This
  file fixes that.
- Local Claude Code CLI sessions have a hook (`.claude/settings.json`)
  that flags destructive commands for confirmation and runs
  `scripts/Test-Project.ps1` (real pytest + Playwright commands) before a
  turn is allowed to end.
- Claude.ai / Cowork chat sessions do **not** have access to this local
  hook -- treat AGENTS.md's boundaries as advisory there, and ask before
  anything irreversible. This matters more than usual here: the working
  tree currently has ~150+ modified/untracked files on top of real commit
  history -- don't assume anything is safe to discard or reset past.
