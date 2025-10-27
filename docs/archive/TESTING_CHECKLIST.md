# TodoWrite Integration Testing Checklist

## Pre-Test Setup

- [ ] Monitoring server is running on port 5001
- [ ] At least one task with TodoWrite usage exists in logs
- [ ] Browser console is open for debugging (F12)

## Backend Tests

### API Endpoint
- [ ] Endpoint exists: `/api/tasks/<task_id>/todowrite-details`
- [ ] Returns 404 for non-existent task
- [ ] Returns empty array for tasks without TodoWrite
- [ ] Returns proper JSON structure with todos array
- [ ] Each todo has: content, status, activeForm fields

### Manual API Test
```bash
# Find a task ID with TodoWrite usage
curl http://localhost:5001/api/tasks/YOUR_TASK_ID/todowrite-details

# Expected response:
{
  "task_id": "YOUR_TASK_ID",
  "todowrite_calls": [
    {
      "timestamp": "2025-10-20T23:45:12.123456",
      "todos": [
        {
          "content": "Task description",
          "status": "completed",
          "activeForm": "Completing task..."
        }
      ],
      "status": "completed"
    }
  ]
}
```

## Frontend Tests

### Visual Elements
- [ ] TodoWrite entries have "Click to view" text
- [ ] TodoWrite entries show arrow indicator (▸)
- [ ] TodoWrite entries have clickable cursor on hover
- [ ] No copy button on TodoWrite entries (intentional)

### Click Interaction
- [ ] Clicking TodoWrite entry expands details
- [ ] Arrow changes to ▾ when expanded
- [ ] Loading message appears briefly
- [ ] Todos render with proper styling
- [ ] Status icons are correct (○ ◐ ●)

### Todo Display
- [ ] Pending todos have gray border
- [ ] In-progress todos have blue border
- [ ] Completed todos have green border
- [ ] ActiveForm text shows for in-progress items
- [ ] Completed items are slightly faded
- [ ] Summary statistics are accurate

### Collapse Behavior
- [ ] Clicking again collapses the details
- [ ] Arrow changes back to ▸
- [ ] Details section is hidden
- [ ] No API call on collapse (uses cache)

### Performance
- [ ] First expansion fetches from API
- [ ] Second expansion uses cached data (check Network tab)
- [ ] Multiple TodoWrite entries can be expanded independently
- [ ] Cache is cleared when closing task modal

### Error Handling
- [ ] API errors show error message in red
- [ ] Missing todos show "No todo details available"
- [ ] Network failures handled gracefully

## Cross-Browser Testing

- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari

## Edge Cases

- [ ] Task with single TodoWrite call
- [ ] Task with multiple TodoWrite calls
- [ ] TodoWrite with 0 items (edge case)
- [ ] TodoWrite with 20+ items (scroll test)
- [ ] Very long todo content (text wrapping)
- [ ] Unicode characters in todo content

## Regression Tests

### Existing Functionality
- [ ] Other tool entries still work (Read, Write, Bash, etc.)
- [ ] Copy buttons work on non-TodoWrite entries
- [ ] Tool filters still work
- [ ] Auto-scroll toggle works
- [ ] Task modal opens/closes properly
- [ ] Activity log displays correctly

### Task Modal
- [ ] Switching between tasks clears TodoWrite cache
- [ ] Opening different tasks works correctly
- [ ] Session view still works

## Documentation

- [ ] Integration summary document created
- [ ] Flow diagram available
- [ ] Code comments are clear
- [ ] API endpoint documented

## Deployment Checklist

- [ ] No JavaScript syntax errors in console
- [ ] No Python exceptions in server logs
- [ ] No broken CSS (inspect visually)
- [ ] Mobile responsive (test on narrow viewport)

## Success Criteria

✅ **Must Have:**
- TodoWrite entries are clickable
- Todos display with correct status styling
- API endpoint returns correct data
- No errors in browser console

✅ **Nice to Have:**
- Smooth animations
- Proper caching behavior
- Error messages are helpful
- Mobile-friendly layout

## Known Limitations

1. **Real-time updates:** TodoWrite details are static once loaded (not live-updated)
2. **Diff view:** No visual diff between consecutive TodoWrite calls
3. **Search:** Cannot search within todo content
4. **Export:** No export functionality for todos
5. **Timeline:** No timeline view of todo progression

## Future Improvements

1. Add WebSocket support for real-time todo updates
2. Implement timeline visualization
3. Add diff highlighting between TodoWrite calls
4. Support todo search across all tasks
5. Add CSV/JSON export for todo history
