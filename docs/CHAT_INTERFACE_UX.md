# Chat Interface UX Pattern

> **Last Updated**: 2025-10-28
> **For**: frontend_agent, ui-comprehensive-tester, and future frontend developers

## Overview

The AMIGA chat interface implements a **progressive reveal** UX pattern where the full interface (sidebars, chat history) appears only after the user engages with the input box.

## Navigation States

### State 1: Landing Page (Home Screen)

**When**: First load or after `/clear` command

**Visible Elements**:
- ✅ AMIGA logo (centered, large)
- ✅ Input box (centered, glowing animation)
- ✅ Command autocomplete (if user types `/`)
- ❌ TaskSidebar (hidden)
- ❌ SessionsSidebar (hidden)
- ❌ Chat history (no messages)
- ❌ Chat header (no top bar)

**Trigger to Next State**: User types anything into input box

**Code Location**: `ChatInterface.tsx` lines 606-617

```tsx
if (messages.length === 0 && !chatViewActive) {
  return (
    <div className="chat-interface landing">
      {/* Clean centered layout */}
    </div>
  );
}
```

### State 2: Full Chat Interface

**When**: User has typed anything OR messages exist

**Visible Elements**:
- ✅ Chat header with small AMIGA logo (clickable)
- ✅ TaskSidebar (left side, tasks list)
- ✅ SessionsSidebar (right side, sessions list)
- ✅ Chat history (message list)
- ✅ Input box (bottom, compact)

**Return to Landing**: User sends `/clear` command

**Code Location**: `ChatInterface.tsx` lines 619-879 (full chat UI)

## Sidebar Visibility Logic

### Control Point: `App.tsx`

```tsx
// Sidebars shown when ANY of these conditions are true:
const showSidebar = chatViewActive || messages.length > 0;

return (
  <div className="App">
    <TaskSidebar visible={showSidebar} />
    <ChatInterface ... chatViewActive={chatViewActive} setChatViewActive={setChatViewActive} />
    <SessionsSidebar visible={showSidebar} />
  </div>
);
```

**Visibility Conditions** (OR logic):
1. `chatViewActive === true`: User typed anything into input
2. `messages.length > 0`: User sent at least one message

### State Management: `chatViewActive`

**Initial State**: `false` (landing page)

**Set to `true`**:
- User types anything and presses Enter (even empty string)
- Happens in `ChatInterface.handleSend()` (lines 451-469)

**Set to `false`**:
- User sends `/clear` command
- Resets to landing page after animation (lines 479-480)

## User Flow Examples

### Example 1: First Interaction

1. **Load page** → Landing page (no sidebars)
2. **User types** "Hello" → Still landing (waiting for Enter)
3. **User presses Enter** → `chatViewActive = true` → Sidebars appear + message sent
4. **Assistant responds** → Full chat interface visible

### Example 2: Empty Enter on Landing

1. **Load page** → Landing page (no sidebars)
2. **User presses Enter** (empty input) → `chatViewActive = true` → Sidebars appear
3. **No message sent** → User sees full interface without any chat history

### Example 3: Clear Chat

1. **Full chat interface** visible (messages exist)
2. **User types** `/clear` → Command sent
3. **After animation** → `chatViewActive = false` + `messages = []`
4. **Result** → Back to landing page (sidebars hidden)

## Implementation Details

### Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `App.tsx` | Sidebar visibility control | 10-34 |
| `ChatInterface.tsx` | Landing vs chat rendering | 606-879 |
| `ChatInterface.tsx` | Navigation trigger (handleSend) | 451-516 |
| `ChatInterface.css` | Landing page styles | 32-120 |
| `App.css` | Layout and sidebar positioning | 14-19 |

### CSS Classes

- `.chat-interface.landing`: Landing page layout (centered, no sidebars)
- `.landing-container`: Centering wrapper
- `.landing-logo`: Large centered AMIGA logo
- `.landing-input-wrapper`: Input box container with glowing effect

### Animation Effects

**Landing Input Glow**:
```css
animation: inputGlow 2s ease-in-out infinite;
```

**Shutdown Animation** (when clearing):
```css
animation: shutdownFade 0.6s ease-out forwards;
```

## Design Rationale

### Why Progressive Reveal?

1. **Focus**: Landing page focuses user attention on single action (type to start)
2. **Clean**: No visual clutter on first load (professional, minimal)
3. **Discovery**: Sidebars appear naturally when needed (after engagement)
4. **Return**: `/clear` returns to clean state (matches initial experience)

### Why Not Always Show Sidebars?

- Sidebars are contextual (tasks and sessions only matter during conversation)
- Landing page serves as "reset point" after clearing conversation
- Reveals interface progressively (reduces cognitive load)

## Testing Checklist

When modifying chat interface, verify:

- [ ] Landing page shows ONLY logo + input (no sidebars)
- [ ] Typing + Enter shows sidebars immediately
- [ ] Empty Enter on landing shows sidebars (no message sent)
- [ ] `/clear` returns to landing page (sidebars hide)
- [ ] Page reload shows landing (no persisted state)
- [ ] Sidebar visibility matches `showSidebar` logic in `App.tsx`
- [ ] Animations smooth (input glow, shutdown fade)

## Browser Testing

Use Playwright MCP to validate:

```typescript
// Navigate to chat
browser_navigate("http://localhost:3000")

// Take screenshot of landing page
browser_take_screenshot({ format: "jpeg", quality: 80, filename: "landing.jpg" })

// Type message
browser_type({ element: "input", ref: ".cs-message-input", text: "hello" })

// Submit
browser_press_key({ key: "Enter" })

// Wait for sidebars to appear
browser_wait_for({ time: 1 })

// Take screenshot of full interface
browser_take_screenshot({ format: "jpeg", quality: 80, filename: "chat-full.jpg" })

// Verify sidebars visible
browser_snapshot() // Check for TaskSidebar and SessionsSidebar elements
```

## Common Issues

### Issue: Sidebars don't appear after typing

**Cause**: `chatViewActive` not set to `true`

**Fix**: Check `handleSend()` in `ChatInterface.tsx` (line 466-468)

### Issue: Sidebars visible on landing page

**Cause**: `showSidebar` logic broken in `App.tsx`

**Fix**: Verify conditions: `chatViewActive || messages.length > 0` (line 34)

### Issue: `/clear` doesn't return to landing

**Cause**: `setChatViewActive(false)` not called after clear

**Fix**: Check `/clear` handler in `handleSend()` (line 479-480)

## Future Considerations

### Persistent State (Not Implemented)

Currently, the interface does NOT persist state across page reloads:
- Always shows landing page on load
- No localStorage for `chatViewActive` or messages

**If implementing persistence**:
- Store `chatViewActive` in localStorage
- Restore on mount in `App.tsx`
- Consider UX: Should users always see landing first?

### Mobile Responsiveness

Landing page is responsive, but sidebar behavior on mobile may need adjustment:
- Consider collapsible sidebars on small screens
- Touch-friendly input on landing page
- Verify glow animation performance on mobile

---

**For Questions**: Contact frontend_agent or refer to CLAUDE.md (Playwright MCP Integration section)
