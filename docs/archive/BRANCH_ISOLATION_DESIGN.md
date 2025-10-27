# Branch Isolation Per Task - Design Document

## Problem Analysis

### Current State
Task #cb791e revealed critical gaps in branch isolation:

1. **Branch creation EXISTS** (`tasks.py:create_task_branch()`) but fails silently
2. **Workspace defaults to `/Users/matifuentes/Workspace`** - NOT a git repo
3. **No merge-on-completion** - branches left dangling
4. **Agents don't commit** - policy exists but not enforced

### Root Causes

#### Issue 1: Workspace Selection
```python
# main.py:1307
workspace = current_workspace or WORKSPACE_PATH
```

Problems:
- `current_workspace` may be None or non-git path
- `WORKSPACE_PATH` = `/Users/matifuentes/Workspace` (parent dir, not git repo)
- No validation that workspace IS a git repo
- Task proceeds even if branch creation fails

#### Issue 2: Silent Failure
```python
# tasks.py:46-47
if result.returncode != 0:
    logger.warning(f"Not a git repo: {workspace}")
    return False, "not_a_git_repo"

# main.py (caller)
success, branch_or_error = create_task_branch(task.id, Path(task.workspace))
if not success:
    logger.warning(f"Could not create task branch (reason: {branch_or_error}), continuing on current branch")
    # CONTINUES ANYWAY!
```

Task continues without isolation - defeats the purpose.

#### Issue 3: No Merge on Completion
- `merge_task_branch()` exists but never called
- Branches accumulate: `task/cb791e`, `task/abc123`, etc.
- Main branch doesn't get updates
- Requires manual cleanup

#### Issue 4: Agent Commit Policy Not Enforced
- `code_agent.md:14` says "Always commit after making code changes"
- `code-task.md:18,22,42` says "CRITICAL: Commit changes"
- **But agents don't comply** - cb791e made 5 Edit calls, NO git commit

## Solution Design

### Phase 1: Mandatory Branch Isolation

**Principle**: If we can't create isolated branch → FAIL task immediately.

#### 1.1 Smart Workspace Resolution

```python
def resolve_git_workspace(current_workspace: str | None, workspace_path: str, bot_repo: str) -> Path | None:
    """
    Resolve workspace to a valid git repository

    Priority:
    1. current_workspace if set and is git repo
    2. bot_repo (agentlab) if no workspace set
    3. None if no valid git repo found
    """
    candidates = []

    if current_workspace:
        candidates.append(Path(current_workspace))

    # Default to bot repo for bot-related tasks
    candidates.append(Path(bot_repo))

    # Never default to parent WORKSPACE_PATH unless it's actually a git repo
    workspace_parent = Path(workspace_path)
    if (workspace_parent / ".git").exists():
        candidates.append(workspace_parent)

    for candidate in candidates:
        if candidate.exists() and (candidate / ".git").exists():
            return candidate

    return None
```

**Usage in main.py:**
```python
workspace = resolve_git_workspace(current_workspace, WORKSPACE_PATH, BOT_REPOSITORY)
if workspace is None:
    await update.message.reply_text(
        "⚠️ Cannot create task: No git repository available. Use /workspace to set one."
    )
    return
```

#### 1.2 Fail Fast on Branch Creation Failure

```python
# In main.py after create_task():
success, branch_or_error = create_task_branch(task.id, Path(task.workspace))
if not success:
    # FAIL THE TASK - don't continue
    task_manager.update_task(
        task.id,
        status="failed",
        error=f"Failed to create isolated branch: {branch_or_error}"
    )
    await update.message.reply_text(
        f"❌ Task failed: Could not create isolated branch\n"
        f"Reason: {branch_or_error}\n\n"
        f"Please ensure {task.workspace} is a clean git repository."
    )
    return  # Don't submit to agent pool
```

### Phase 2: Auto-Merge on Completion

#### 2.1 Modify Task Completion Handler

```python
# In main.py execute_background_task() after agent completes:

if task.status == "completed":
    # Try to merge branch back to main
    success, message = merge_task_branch(task.id, Path(task.workspace), target_branch="main")

    if success:
        logger.info(f"Task {task.id}: Successfully merged branch to main")
        task_manager.update_task(
            task.id,
            result=f"{task.result}\n\n✅ Branch merged to main"
        )
    else:
        logger.warning(f"Task {task.id}: Failed to merge branch: {message}")
        # Don't fail the task, but warn user
        task_manager.update_task(
            task.id,
            result=f"{task.result}\n\n⚠️ Branch NOT merged (reason: {message})"
        )
```

#### 2.2 Enhanced merge_task_branch()

Current implementation (tasks.py:83-120) needs fixes:

**Problems:**
- Checks for uncommitted changes - but agents SHOULD commit!
- If agents don't commit → merge blocked
- Need to handle this gracefully

**Solution:**
```python
def merge_task_branch(task_id: str, workspace: Path, target_branch: str = "main") -> tuple[bool, str]:
    """
    Merge task branch back to target branch

    Behavior:
    - If uncommitted changes exist: Commit them automatically with task summary
    - Merge to target branch
    - Delete task branch after successful merge
    """
    try:
        branch_name = f"task/{task_id[:8]}"

        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(workspace)
        )

        if result.stdout.strip():
            logger.warning(f"Uncommitted changes in {branch_name}, auto-committing")

            # Auto-commit with task ID
            subprocess.run(
                ["git", "add", "."],
                capture_output=True,
                cwd=str(workspace)
            )

            commit_msg = f"Auto-commit for task {task_id}\n\nChanges left uncommitted by agent - committing before merge."
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                capture_output=True,
                cwd=str(workspace)
            )

        # Switch to target branch
        result = subprocess.run(
            ["git", "checkout", target_branch],
            capture_output=True,
            text=True,
            cwd=str(workspace)
        )
        if result.returncode != 0:
            return False, f"Failed to checkout {target_branch}: {result.stderr}"

        # Merge task branch
        result = subprocess.run(
            ["git", "merge", "--no-ff", branch_name, "-m", f"Merge task branch {branch_name}"],
            capture_output=True,
            text=True,
            cwd=str(workspace)
        )

        if result.returncode != 0:
            return False, f"Merge conflict or error: {result.stderr}"

        # Delete task branch
        subprocess.run(
            ["git", "branch", "-d", branch_name],
            capture_output=True,
            cwd=str(workspace)
        )

        logger.info(f"Successfully merged and deleted branch {branch_name}")
        return True, f"Merged {branch_name} to {target_branch}"

    except Exception as e:
        logger.error(f"Error merging task branch: {e}")
        return False, str(e)
```

### Phase 3: Enforce Agent Commit Policy

Current approach (documentation) doesn't work. Need enforcement mechanism.

#### 3.1 Post-Task Git Status Check

Add to workflow after agent completes:

```python
# In execute_background_task() after agent finishes:

# Check if agent left uncommitted changes
result = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    cwd=str(task.workspace)
)

if result.stdout.strip():
    logger.warning(f"Task {task.id}: Agent left uncommitted changes!")

    # Append warning to result
    files_changed = result.stdout.strip().split('\n')
    task_manager.update_task(
        task.id,
        result=f"{task.result}\n\n⚠️ WARNING: Agent did not commit {len(files_changed)} changed files"
    )
```

#### 3.2 Update Workflow Instructions

Modify `.claude/commands/workflows/code-task.md`:

**Add final step:**
```markdown
6. **Commit Verification** (automatic)
   - After implementation completes, run `git status`
   - If uncommitted changes exist, create commit with:
     - Descriptive message based on changes made
     - Standard co-authored footer
   - This is a SAFETY NET - agents SHOULD commit themselves
```

**Enhance agent prompts:**
```markdown
2. **Backend Implementation** (if needed)
   - Use Task tool with subagent_type="code_agent"
   - Prompt: "Implement backend task: $ARGUMENTS.

     CRITICAL REQUIREMENTS:
     1. After making changes, IMMEDIATELY commit them
     2. Use descriptive commit message: 'verb + what changed + why'
     3. Include standard footer (Claude Code attribution)
     4. Do NOT finish without committing - check git status before returning

     Follow AMIGA Python conventions (Black, isort, type hints)."
```

## Implementation Plan

### Step 1: Fix Workspace Resolution (5 min)
- [ ] Add `resolve_git_workspace()` function to main.py
- [ ] Replace all `workspace = current_workspace or WORKSPACE_PATH`
- [ ] Add validation: task creation fails if no git repo

### Step 2: Make Branch Creation Mandatory (5 min)
- [ ] Change branch creation failure from WARNING to FATAL
- [ ] Don't submit task to agent pool if branch creation fails
- [ ] Update user with clear error message

### Step 3: Implement Auto-Merge (10 min)
- [ ] Enhance `merge_task_branch()` to auto-commit if needed
- [ ] Call merge function in task completion handler
- [ ] Add merge status to task result

### Step 4: Add Commit Verification (5 min)
- [ ] Check git status after agent completes
- [ ] Log warning if uncommitted changes exist
- [ ] Append warning to task result

### Step 5: Update Workflow (5 min)
- [ ] Strengthen commit requirements in code-task.md
- [ ] Add commit verification step
- [ ] Update agent prompts with explicit commit checks

### Step 6: Test Complete Flow (10 min)
- [ ] Create test task
- [ ] Verify branch created
- [ ] Verify agent commits changes
- [ ] Verify branch auto-merged to main
- [ ] Verify branch cleaned up

**Total: ~40 minutes**

## Success Criteria

After implementation:

✅ **Branch Isolation**
- Every task gets isolated branch: `task/{id[:8]}`
- Branch created from current HEAD
- Task FAILS if branch can't be created

✅ **Workspace Validation**
- Tasks only run in valid git repositories
- Clear error if no git repo available
- Defaults to agentlab repo for bot tasks

✅ **Auto-Merge**
- Successful tasks auto-merge to main
- Branch deleted after merge
- Uncommitted changes auto-committed before merge

✅ **Commit Enforcement**
- Agents warned explicitly about commit requirement
- Post-task verification checks git status
- Uncommitted changes logged and warned

✅ **No Manual Cleanup**
- No orphaned branches
- Main branch always up-to-date
- Clear audit trail in git history

## Migration Notes

**Existing Branches:**
```bash
# Check for existing task branches
git branch | grep 'task/'

# Clean up manually if any exist
git branch -D task/cb791e  # etc
```

**Stashed Changes:**
System auto-stashes before creating branches. After migration:
```bash
git stash list  # Check for auto-stashes
# Manually review and apply/drop as needed
```

## Monitoring

Dashboard should show:
- ✅ Task branch: `task/abc123` (created)
- ✅ Commits: 3 commits made
- ✅ Merged to main (cleanup: branch deleted)

Or:
- ❌ Branch creation failed (not a git repo)
- ⚠️ Agent didn't commit (files modified but not committed)
- ⚠️ Merge failed (conflicts)

---

**Last Updated**: 2025-10-20
**Status**: Design Complete - Ready for Implementation
