# 4. Git Worktree Isolation

Date: 2025-01-15 (Updated: 2025-10-22)

## Status

Accepted (Implementation evolved - see update below)

## Context

Multiple Claude Code sessions need to work on code changes concurrently:

1. **Concurrent tasks**: User A working on feature X while User B fixes bug Y
2. **File conflicts**: Both tasks modifying same files simultaneously
3. **Branch isolation**: Each task needs its own branch without interference
4. **Clean workspace**: Tasks should start from clean state (main branch)
5. **Merge safety**: Need to prevent losing work when tasks complete

**Without isolation:**
- Tasks modify same working directory → file corruption
- Git conflicts and uncommitted changes block other tasks
- Can't have multiple Claude Code sessions in same repo
- Risk of losing work if task interrupted

**Git worktrees** solve this by creating isolated working directories that share .git history.

## Decision

Use **git worktrees for task isolation**, with explicit workflow control.

**Original approach** (deprecated):
- `WorktreeManager` automatically created/cleaned worktrees
- Invisible to workflows, managed by session pool

**Current approach** (since 2025-10-22):
- **Workflows explicitly manage worktrees** via `git-worktree` agent
- Step 0: Create worktree (`/workflows:code-task` calls `git-worktree create-worktree`)
- Step N: Merge to main (`git-merge` agent)
- Cleanup: Manual via `git-worktree cleanup-worktree` (disabled by default for debugging)

**Architecture:**

```bash
/tmp/agentlab-worktrees/
  ├── task_abc123/        # Worktree for task abc123
  │   └── .git → /main/repo/.git
  ├── task_def456/        # Worktree for task def456
  │   └── .git → /main/repo/.git
```

Each worktree:
- Is a complete working directory with its own files
- Has its own branch: `task/{task_id}`
- Shares .git database with main repo (efficient)
- Can be worked on independently without conflicts

**Workflow integration** (`.claude/agents/git-worktree.md`):
1. Workflow creates worktree in `/tmp/agentlab-worktrees/{task_id}`
2. Agent works in worktree, commits to `task/{task_id}` branch
3. Agent merges to main before completing
4. Worktree preserved in /tmp for debugging (auto-cleanup on system restart)

## Consequences

### Positive

- **True isolation**: Tasks can't interfere with each other's files
- **Parallel execution**: Multiple Claude Code sessions work simultaneously
- **Clean workspaces**: Each task starts from fresh main branch state
- **Efficient**: Worktrees share .git database (no duplication)
- **Debugging friendly**: Preserved worktrees allow post-task inspection
- **Safe merging**: Explicit merge step prevents losing work
- **Temporary storage**: /tmp auto-cleanup on system restart

### Negative

- **Disk space**: Each worktree duplicates working directory files (~10-50 MB per task)
- **Manual cleanup**: Worktrees persist until manual cleanup or restart
- **Complexity**: Workflows must explicitly manage worktree lifecycle
- **Merge responsibility**: Agent must remember to merge (enforced by git-merge agent)
- **Path management**: Need to track which path corresponds to which task

## Alternatives Considered

1. **Git Stash + Single Directory**
   - Rejected: Stash doesn't provide true isolation
   - Can't run multiple sessions concurrently
   - Complex stash management with many tasks

2. **Clone Repository Per Task**
   - Rejected: Wasteful (full .git history per task = 100+ MB each)
   - Slow to clone for each task
   - More disk space required

3. **Docker Containers Per Task**
   - Rejected: Overkill for simple isolation
   - Slower startup time
   - Added infrastructure complexity
   - Doesn't solve git state isolation

4. **File Locking**
   - Rejected: Doesn't prevent git state conflicts
   - Complex lock management
   - Doesn't allow true parallel work

5. **Branch Per Task (No Worktree)**
   - Rejected: Still share working directory
   - Can't work on multiple branches simultaneously
   - Frequent branch switching is slow and error-prone

6. **Automatic Worktree Cleanup**
   - Previous approach: WorktreeManager auto-cleanup after task
   - Changed: Preserve for debugging, manual cleanup only
   - Rationale: Better debugging, /tmp auto-cleans anyway

## References

- Deprecated manager: `utils/worktree.py:62-428` (marked DEPRECATED)
- Git-worktree agent: `.claude/agents/git-worktree.md`
- Worktree base path: `/tmp/agentlab-worktrees/` (see `utils/worktree.py:71`)
- Merge responsibility: ADR 0004 notes, `utils/worktree.py:34-49`
- Workflow integration: `.claude/workflows/` (various workflow files)
- CLAUDE.md: Worktree section (lines 200-250)
