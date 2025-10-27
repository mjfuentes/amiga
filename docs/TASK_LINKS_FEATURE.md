# Task Links Feature

## Overview

Task IDs in chat messages are now automatically converted to clickable links that open the corresponding task in the monitoring dashboard.

## Implementation

### Pattern Recognition
- Detects pattern: `#task_<alphanumeric_id>`
- Examples: `#task_abc123`, `#task_20241027_test`, `#task_fix_bug`

### Link Behavior
- **Click**: Opens monitoring dashboard in new tab
- **URL**: `http://localhost:3000#task-<task_id>`
- **Visual**: Orange highlighting with hover effects

### Technical Details

**Files Modified**:
- `monitoring/dashboard/chat-frontend/src/components/ChatInterface.tsx`
  - Added `linkifyTaskIds()` function to process text and convert task IDs to links
  - Custom ReactMarkdown components for `p` and `text` nodes
  - User messages also processed for task links

- `monitoring/dashboard/chat-frontend/src/components/ChatInterface.css`
  - Added `.task-link` styles with orange theme
  - Hover effects and transitions

**Pattern Matching**:
```typescript
const taskIdRegex = /#(task_[a-zA-Z0-9_]+)/g;
```

**Link Generation**:
```typescript
<a
  href={`http://localhost:3000#task-${taskId}`}
  className="task-link"
  onClick={(e) => {
    e.preventDefault();
    window.open(`http://localhost:3000#task-${taskId}`, '_blank');
  }}
  title={`View task ${taskId} in monitoring dashboard`}
>
  #{taskId}
</a>
```

### Styling

**Colors**:
- Default: `#e07856` (orange)
- Hover: `#ff9472` (lighter orange)
- Background: `rgba(224, 120, 86, 0.1)` (subtle orange tint)

**Effects**:
- Subtle lift on hover (`translateY(-1px)`)
- Border-bottom accent
- Rounded corners for pill-like appearance

### Usage Examples

**In Assistant Messages**:
```
I've created task #task_abc123 to handle this request.
You can check the progress at #task_xyz789.
```

**In User Messages**:
```
What's the status of #task_abc123?
Please stop #task_xyz789.
```

### Testing

**Manual Test**:
1. Open chat: `http://localhost:3000/chat`
2. Send message with task ID: `Check #task_test123`
3. Verify link appears with orange styling
4. Click link to open dashboard

**Visual Verification**:
- Task links stand out from regular links (orange vs blue)
- Hover effect provides feedback
- Click opens dashboard in new tab

## Benefits

1. **Quick Navigation**: Jump directly to task details from chat
2. **Context Preservation**: Reference tasks without leaving chat
3. **Visual Distinction**: Task links clearly identifiable
4. **User Experience**: No need to copy-paste task IDs

## Future Enhancements

- [ ] Add tooltip with task status on hover
- [ ] Support shortened task IDs (e.g., `#task_abc` matches `#task_abc123`)
- [ ] Inline task status badges in chat
- [ ] Support for other ID patterns (e.g., session IDs)

---

**Deployed**: 2025-10-27
**Version**: chat-frontend build with `main.2e2aefa9.js`
