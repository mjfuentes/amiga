# Playwright MCP Migration - Manual Testing Guide

**Purpose**: Validate Playwright MCP server integration and ensure all browser automation capabilities work correctly.

**Created**: 2025-10-21
**Status**: Ready for testing
**Related**: Migration from deprecated `playwright` tool to `@mcp/playwright` server

---

## Prerequisites

### 1. Verify Playwright MCP Installation

```bash
# Check if MCP server is installed
npm list -g @modelcontextprotocol/server-playwright

# Expected output:
# /Users/matifuentes/.nvm/versions/node/v23.1.0/lib
# └── @modelcontextprotocol/server-playwright@0.6.2
```

If not installed:
```bash
npm install -g @modelcontextprotocol/server-playwright
```

### 2. Verify Claude Configuration

Check `~/.claude.json` contains Playwright MCP server:

```bash
cat ~/.claude.json | jq '.mcpServers.playwright'
```

Expected output:
```json
{
  "command": "npx",
  "args": [
    "-y",
    "@modelcontextprotocol/server-playwright@0.6.2"
  ]
}
```

### 3. Required Tools

- **Node.js**: v18+ (check: `node --version`)
- **npx**: Included with npm (check: `npx --version`)
- **jq**: JSON processor (check: `jq --version`)
- **Claude Code CLI**: Latest version

### 4. Environment Setup

```bash
# Navigate to test directory
cd /Users/matifuentes/Workspace/agentlab

# Ensure Claude session is active
claude --version
```

---

## Test Workflows

### Test 1: Navigation & Screenshots

**Objective**: Validate basic navigation and screenshot capture capabilities.

**Steps**:

1. **Start Claude Code session**
   ```bash
   claude
   ```

2. **Test navigation to example.com**

   Prompt to Claude:
   ```
   Use Playwright MCP to navigate to https://example.com and take a screenshot
   ```

3. **Test navigation to anthropic.com**

   Prompt to Claude:
   ```
   Use Playwright MCP to navigate to https://www.anthropic.com and take a screenshot
   ```

**Expected Results**:

| Step | Expected Output | Success Criteria |
|------|----------------|------------------|
| Tool discovery | Claude identifies `playwright_navigate` and `playwright_screenshot` tools | Tools listed in response |
| Navigation | Browser navigates to URL successfully | No error messages |
| Screenshot | Screenshot file created and displayed | Image shows correct webpage |
| File path | Screenshot saved to accessible location | Path provided in response |

**Success Indicators**:
- ✅ No "tool not found" errors
- ✅ Screenshot shows example.com with heading "Example Domain"
- ✅ Screenshot shows anthropic.com homepage
- ✅ File paths are absolute and valid

**Common Issues**:
- Browser fails to launch → Check Playwright browser installation
- Screenshot empty/blank → Check viewport settings
- MCP server timeout → Restart Claude session

---

### Test 2: Form Interaction

**Objective**: Validate form filling, clicking, and dynamic content interaction.

**Steps**:

1. **Navigate to Google**

   Prompt to Claude:
   ```
   Use Playwright MCP to navigate to https://www.google.com
   ```

2. **Fill search form and submit**

   Prompt to Claude:
   ```
   Use Playwright MCP to:
   1. Fill the search box with "Anthropic Claude"
   2. Click the search button
   3. Take a screenshot of the results
   ```

**Expected Results**:

| Action | Expected Output | Success Criteria |
|--------|----------------|------------------|
| Navigate | Google homepage loads | Search box visible |
| Fill form | Text entered in search box | Correct text visible |
| Click | Search executes | Results page loads |
| Screenshot | Results page captured | Shows search results for "Anthropic Claude" |

**Success Indicators**:
- ✅ Search box correctly identified and filled
- ✅ Search button clicked successfully
- ✅ Results page shows relevant results
- ✅ Screenshot clearly shows search results

**Common Issues**:
- Element not found → Check selector strategy
- Form not submitted → Verify click action executed
- CAPTCHA appears → Use different search term or site

---

### Test 3: Responsive Testing

**Objective**: Validate viewport manipulation for responsive design testing.

**Steps**:

1. **Test mobile viewport**

   Prompt to Claude:
   ```
   Use Playwright MCP to:
   1. Set viewport to mobile (375x667)
   2. Navigate to https://www.anthropic.com
   3. Take a screenshot labeled "mobile"
   ```

2. **Test tablet viewport**

   Prompt to Claude:
   ```
   Use Playwright MCP to:
   1. Set viewport to tablet (768x1024)
   2. Navigate to https://www.anthropic.com
   3. Take a screenshot labeled "tablet"
   ```

3. **Test desktop viewport**

   Prompt to Claude:
   ```
   Use Playwright MCP to:
   1. Set viewport to desktop (1920x1080)
   2. Navigate to https://www.anthropic.com
   3. Take a screenshot labeled "desktop"
   ```

**Expected Results**:

| Viewport | Dimensions | Expected Layout | Success Criteria |
|----------|-----------|-----------------|------------------|
| Mobile | 375x667 | Single column, hamburger menu | Mobile-optimized layout visible |
| Tablet | 768x1024 | Medium layout, possibly 2 columns | Tablet-optimized layout visible |
| Desktop | 1920x1080 | Full width, multiple columns | Desktop layout with all elements |

**Success Indicators**:
- ✅ Three distinct layouts captured
- ✅ Mobile shows hamburger menu
- ✅ Desktop shows full navigation
- ✅ Content adapts appropriately to each viewport

**Viewport Test Matrix**:

```
Device      | Width  | Height | Orientation | Expected UI Pattern
------------|--------|--------|-------------|--------------------
iPhone 12   | 390    | 844    | Portrait    | Stack layout, large touch targets
iPad        | 768    | 1024   | Portrait    | 2-column, medium spacing
Desktop FHD | 1920   | 1080   | Landscape   | Multi-column, full nav
```

---

### Test 4: Accessibility Tree Validation

**Objective**: Validate accessibility tree snapshot and DOM inspection capabilities.

**Steps**:

1. **Navigate to test site**

   Prompt to Claude:
   ```
   Use Playwright MCP to navigate to https://news.ycombinator.com
   ```

2. **Capture accessibility snapshot**

   Prompt to Claude:
   ```
   Use Playwright MCP to:
   1. Get the accessibility tree snapshot of the page
   2. Identify all heading elements
   3. Count the number of links on the page
   ```

3. **Inspect specific elements**

   Prompt to Claude:
   ```
   Use Playwright MCP to:
   1. Find the first article title
   2. Get its text content
   3. Check if it's a clickable link
   ```

**Expected Results**:

| Action | Expected Output | Success Criteria |
|--------|----------------|------------------|
| Accessibility snapshot | JSON tree with roles and labels | Tree structure returned |
| Heading identification | List of all `<h1>`, `<h2>`, etc. | Correct count and hierarchy |
| Link count | Total number of `<a>` tags | Reasonable count (50+) |
| Element inspection | Text content and attributes | Correct data extracted |

**Success Indicators**:
- ✅ Accessibility tree contains role information
- ✅ Headings properly identified with hierarchy
- ✅ Link count matches visual inspection
- ✅ Element text matches webpage content

**Accessibility Checklist**:
- [ ] Page has proper heading hierarchy (h1 → h2 → h3)
- [ ] Links have descriptive text (not "click here")
- [ ] Images have alt text attributes
- [ ] Form inputs have associated labels
- [ ] Interactive elements have proper ARIA roles

---

## Troubleshooting

### Error: MCP Server Not Found

**Symptom**: Claude reports "Tool not available" or "MCP server not found"

**Solutions**:

1. **Verify installation**:
   ```bash
   npm list -g @modelcontextprotocol/server-playwright
   ```

2. **Reinstall if needed**:
   ```bash
   npm uninstall -g @modelcontextprotocol/server-playwright
   npm install -g @modelcontextprotocol/server-playwright@0.6.2
   ```

3. **Check Claude config**:
   ```bash
   cat ~/.claude.json | jq '.mcpServers'
   ```

4. **Restart Claude session**:
   ```bash
   exit  # Exit current session
   claude  # Start new session
   ```

---

### Error: Browser Launch Failure

**Symptom**: "Failed to launch browser" or timeout errors

**Solutions**:

1. **Install Playwright browsers**:
   ```bash
   npx playwright install
   ```

2. **Install system dependencies** (Linux only):
   ```bash
   npx playwright install-deps
   ```

3. **Check browser binaries**:
   ```bash
   npx playwright install --dry-run
   ```

4. **Try specific browser**:
   ```bash
   npx playwright install chromium
   ```

---

### Error: Tool Execution Timeout

**Symptom**: MCP tool call hangs or times out

**Solutions**:

1. **Check network connectivity**:
   ```bash
   curl -I https://example.com
   ```

2. **Increase timeout** (if configurable in MCP server)

3. **Simplify test**:
   - Navigate to simpler page (example.com instead of complex SPA)
   - Reduce number of actions per prompt

4. **Check MCP server logs**:
   ```bash
   # Logs location varies, check npx output
   tail -f /tmp/mcp-playwright-*.log
   ```

---

### Error: Screenshot Not Displaying

**Symptom**: Screenshot created but not visible in Claude output

**Solutions**:

1. **Check file path**:
   - Ensure path is absolute
   - Verify file exists: `ls -lh <screenshot_path>`

2. **Check file permissions**:
   ```bash
   chmod 644 <screenshot_path>
   ```

3. **Verify file size**:
   ```bash
   du -h <screenshot_path>
   # Should be > 0 bytes
   ```

4. **Try alternative format**:
   - Request PNG instead of JPEG
   - Specify quality parameter

---

### Error: Element Not Found

**Symptom**: "No element found matching selector"

**Solutions**:

1. **Use more specific selector**:
   ```javascript
   // Instead of: input
   // Use: input[name="q"]
   ```

2. **Wait for element**:
   - Request explicit wait before interaction
   - Check if page uses dynamic loading

3. **Check page load state**:
   - Ensure page fully loaded
   - Wait for network idle

4. **Inspect page structure**:
   - Take screenshot first
   - Get accessibility tree to see available elements

---

## Validation Checklist

### Core Functionality

- [ ] **Test 1: Navigation & Screenshots**
  - [ ] Navigate to example.com successfully
  - [ ] Screenshot captured and displayed
  - [ ] Navigate to anthropic.com successfully
  - [ ] Screenshot shows correct page content

- [ ] **Test 2: Form Interaction**
  - [ ] Navigate to Google
  - [ ] Fill search box with text
  - [ ] Click search button
  - [ ] Results page loads and screenshot captured

- [ ] **Test 3: Responsive Testing**
  - [ ] Mobile viewport (375x667) screenshot
  - [ ] Tablet viewport (768x1024) screenshot
  - [ ] Desktop viewport (1920x1080) screenshot
  - [ ] Layouts differ appropriately

- [ ] **Test 4: Accessibility Tree**
  - [ ] Navigate to news.ycombinator.com
  - [ ] Accessibility tree snapshot retrieved
  - [ ] Headings identified correctly
  - [ ] Link count accurate
  - [ ] Element text extraction works

### Error Handling

- [ ] Graceful handling of navigation failures
- [ ] Clear error messages for invalid selectors
- [ ] Timeout errors properly reported
- [ ] File I/O errors handled

### Performance

- [ ] Navigation completes within 10 seconds
- [ ] Screenshot generation within 5 seconds
- [ ] Form interaction responsive
- [ ] No memory leaks after multiple tests

### Documentation

- [ ] All tests documented with expected results
- [ ] Troubleshooting section covers common issues
- [ ] Examples use realistic websites
- [ ] Code snippets tested and verified

---

## Sign-Off

### Test Execution

| Test Suite | Executed By | Date | Result | Notes |
|------------|-------------|------|--------|-------|
| Test 1: Navigation & Screenshots | | | ⬜ Pass / ⬜ Fail | |
| Test 2: Form Interaction | | | ⬜ Pass / ⬜ Fail | |
| Test 3: Responsive Testing | | | ⬜ Pass / ⬜ Fail | |
| Test 4: Accessibility Tree | | | ⬜ Pass / ⬜ Fail | |

### Overall Assessment

**Migration Status**: ⬜ Ready for Production / ⬜ Needs Fixes / ⬜ Blocked

**Issues Found**:
```
[List any issues discovered during testing]
```

**Recommendations**:
```
[List any recommendations for improvement]
```

**Approved By**: ___________________
**Date**: ___________________
**Signature**: ___________________

---

## Additional Resources

### Playwright MCP Documentation
- [MCP Server Playwright GitHub](https://github.com/modelcontextprotocol/servers/tree/main/src/playwright)
- [Playwright Official Docs](https://playwright.dev/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

### Test Sites
- **Simple HTML**: https://example.com
- **Corporate Site**: https://www.anthropic.com
- **Search Engine**: https://www.google.com
- **News Site**: https://news.ycombinator.com
- **Accessibility Test**: https://www.w3.org/WAI/demos/bad/

### Debugging Commands

```bash
# Check MCP server status
ps aux | grep playwright

# View npm global packages
npm list -g --depth=0

# Test npx directly
npx @modelcontextprotocol/server-playwright@0.6.2 --help

# Verify Playwright installation
npx playwright --version

# List installed browsers
npx playwright list
```

---

**End of Testing Guide**
