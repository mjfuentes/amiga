# /create-pr - Streamlined Pull Request Creation

Creates a well-structured PR with comprehensive description and test plan.

## Usage
`/create-pr` - Creates PR from current branch to main

## Workflow
1. Analyze all commits in branch
2. Generate comprehensive PR description
3. Create actionable test plan
4. Push and create PR via GitHub CLI

Based on awesome-claude-code community patterns

---

Create a pull request from the current branch:

1. Check git status and uncommitted changes
2. Analyze ALL commits in the branch (not just the latest)
3. Generate PR title and description covering:
   - Summary of changes
   - Technical approach
   - Testing performed
   - Breaking changes (if any)
4. Create test plan checklist
5. Push to remote and create PR using `gh pr create`

IMPORTANT: Include ALL commits in the analysis, not just the latest one