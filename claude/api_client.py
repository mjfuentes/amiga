"""
Claude API integration for question answering and routing
Replaces orchestrator agent with direct Anthropic API calls
"""

import html
import json
import logging
import os
import re
from pathlib import Path

import anthropic

from core.exceptions import AMIGAError
from claude.tools import AVAILABLE_TOOLS, execute_tool

logger = logging.getLogger(__name__)


def sanitize_xml_content(text: str) -> str:
    """
    Sanitize text for safe inclusion in XML prompt structure.
    Prevents prompt injection via XML tag manipulation.

    Args:
        text: Raw user input or untrusted content

    Returns:
        Escaped text safe for XML inclusion
    """
    if not text:
        return ""

    # HTML escape to prevent XML tag injection
    escaped = html.escape(text, quote=True)

    # Additional safeguards against prompt manipulation
    # Remove potential prompt break patterns
    dangerous_patterns = [
        r"</\w+>",  # Closing XML tags
        r"<\w+[^>]*>",  # Opening XML tags
        r"\[INST\]",  # Common injection patterns
        r"\[/INST\]",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"```xml",  # Code block attempts
        r"```python",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, escaped, re.IGNORECASE):
            # Replace with safe version
            escaped = re.sub(pattern, "", escaped, flags=re.IGNORECASE)
            logger.warning(f"Removed dangerous pattern from input: {pattern}")

    return escaped


def detect_prompt_injection(text: str) -> tuple[bool, str | None]:
    """
    Detect potential prompt injection attempts.

    Args:
        text: User input to analyze

    Returns:
        (is_malicious, reason) - True if injection detected, with explanation
    """
    if not text or len(text) < 10:
        return False, None

    # Suspicious patterns that indicate prompt manipulation attempts
    injection_patterns = [
        (r"\bignore\b.{0,50}\b(instructions?|previous|above)", "Instruction override attempt"),
        (r"\bdisregard\b.{0,50}\b(instructions?|previous)", "Instruction override attempt"),
        (r"\bforget\b.{0,50}\b(instructions?|previous|what|said)", "Instruction override attempt"),
        (r"new instructions?:", "Instruction injection attempt"),
        (r"system:?\s*(you (are|must|should)|prompt)", "System role manipulation"),
        (r"<\|im_start\|>", "System prompt injection"),
        (r"\[INST\]", "Instruction tag injection"),
        (r"\[/INST\]", "Instruction tag injection"),
        (r"act as (a |an )?different", "Role manipulation"),
        (r"you('re| are) (now |actually |really )", "Identity manipulation"),
        (r"</?(role|context|capabilities|system|assistant|user)>", "XML structure manipulation"),
        (r"BACKGROUND_TASK\s*\|", "Task format injection"),
    ]

    text_lower = text.lower()

    for pattern, reason in injection_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"Prompt injection detected: {reason} in text: {text[:100]}")
            return True, reason

    # Check for excessive XML-like tags
    xml_tag_count = len(re.findall(r"</?\w+>", text))
    if xml_tag_count > 5:
        logger.warning(f"Excessive XML tags detected: {xml_tag_count} tags")
        return True, "Excessive XML tag usage"

    # Check for very long inputs (potential DOS or obfuscation)
    if len(text) > 10000:
        logger.warning(f"Unusually long input detected: {len(text)} characters")
        return True, "Input too long"

    return False, None


def validate_file_path(file_path: str, base_path: str | None = None) -> bool:
    """
    Validate file path to prevent directory traversal attacks.

    Args:
        file_path: Path to validate
        base_path: Optional base directory to restrict access

    Returns:
        True if path is safe, False otherwise
    """
    if not file_path:
        return False

    # Check for obvious path traversal patterns in the raw input
    if ".." in file_path:
        logger.warning(f"Path traversal attempt detected: {file_path}")
        return False

    # Absolute paths outside workspace are suspicious (unless no base path)
    if file_path.startswith("/") and not base_path:
        logger.warning(f"Absolute path without base restriction: {file_path}")
        return False

    # If base path provided, ensure resolved path is within it
    if base_path:
        try:
            # Resolve paths to absolute, canonical paths
            base_resolved = Path(base_path).resolve()

            # If file_path is relative, resolve it relative to base_path
            if not Path(file_path).is_absolute():
                resolved = (base_resolved / file_path).resolve()
            else:
                resolved = Path(file_path).resolve()

            # Check if resolved path is within base directory
            try:
                resolved.relative_to(base_resolved)
                return True
            except ValueError:
                logger.warning(f"Path outside base directory: {file_path} not in {base_path}")
                return False

        except Exception as e:
            logger.error(f"Path validation error: {e}", exc_info=True)
            return False

    return True


async def ask_claude(
    user_query: str,
    input_method: str,  # "voice" or "text"
    conversation_history: list[dict],
    current_workspace: str | None,
    bot_repository: str,
    workspace_path: str,
    available_repositories: list[str],
    active_tasks: list[dict],
    image_path: str | None = None,
) -> tuple[str, dict | None, dict | None]:
    """
    Ask Claude a question using Anthropic API (not Claude Code CLI)

    Returns:
        (response_text, background_task_info, usage_info)
        - response_text: Direct answer for user
        - background_task_info: Dict with 'description' and 'user_message' if background task needed, else None
        - usage_info: Dict with 'input_tokens', 'output_tokens' from API response
    """

    # Security: Detect prompt injection attempts
    is_malicious, injection_reason = detect_prompt_injection(user_query)
    if is_malicious:
        logger.warning(f"Blocked prompt injection attempt: {injection_reason}")
        return (
            f"I detected a potential security issue in your request ({injection_reason}). Please rephrase your question.",
            None,
            None,
        )

    # Security: Sanitize all user inputs before including in prompt
    safe_query = sanitize_xml_content(user_query)
    safe_workspace = sanitize_xml_content(current_workspace or workspace_path)
    safe_bot_repo = sanitize_xml_content(bot_repository)

    # Security: Validate image path if provided
    if image_path and not validate_file_path(image_path):
        logger.warning(f"Invalid image path rejected: {image_path}")
        return "Invalid file path provided. Please check the path and try again.", None, None

    # Optimize context: Sanitize and truncate conversation history
    safe_history = []
    for msg in conversation_history[-20:]:  # Last 20 messages for comprehensive context retention
        safe_msg = {}
        for key, value in msg.items():
            if isinstance(value, str):
                # Truncate very long messages to save tokens
                truncated = value[:5000] if len(value) > 5000 else value
                safe_msg[key] = sanitize_xml_content(truncated)
            else:
                safe_msg[key] = value
        safe_history.append(safe_msg)

    # Optimize context: Only include essential task info
    safe_tasks = []
    for task in active_tasks[:3]:  # Max 3 recent tasks
        safe_task = {
            "id": task.task_id if hasattr(task, "task_id") else task.get("id", ""),
            "status": task.status if hasattr(task, "status") else task.get("status", ""),
            # Omit description to save tokens unless critical
        }
        safe_tasks.append(safe_task)

    # Build context - minimize tokens and sanitize all values
    context = {
        "user_query": safe_query,
        "input_method": input_method,
        "conversation_history": safe_history,  # Sanitized and truncated
        "current_workspace": safe_workspace,
        "bot_repository": safe_bot_repo,
        # Only include active tasks if there are any (limited to 3)
        "active_tasks": safe_tasks if safe_tasks else [],
    }
    # Don't include repos list - saves ~100 tokens

    if image_path:
        context["image_path"] = sanitize_xml_content(image_path)

    # Build system prompt with XML structure for clarity and token efficiency
    # Note: Context JSON is now sanitized before insertion
    system_prompt = f"""<role>You are amiga - Matias's personal AI assistant. I'm built on Claude Haiku 4.5, optimized for quick routing and answering questions. Think of me as your technical right hand - I know the codebase, I know what you're working on, and I'm here to help you stay productive.</role>

<context>
{json.dumps(context, indent=2)}
</context>

<capabilities>
I handle two types of requests:
• DIRECT ANSWERS: General knowledge, quick questions, status checks - I respond immediately
• ROUTING: Implementation work, file operations, code changes - I delegate to specialized agents via BACKGROUND_TASK
• Focus areas: Your web chat interface, monitoring dashboard, and task management system
</capabilities>

<tools>
I have access to tools that let me answer questions about your system and current information from the web.

Available tools:

1. query_database
• Query the SQLite databases (agentlab, analytics) for real-time information
• Use this AUTOMATICALLY when you ask about tasks, errors, activity, or metrics
• Examples: "how many tasks are running?", "show recent errors", "what's my tool usage?"
• Security: Read-only SELECT queries

2. web_search
• Search the web for current information, documentation, or technical specifications
• Use this AUTOMATICALLY when you need up-to-date information or external references
• Examples: "what's the latest Python version?", "find FastAPI docs", "search for JWT best practices"
• Returns: Titles, URLs, and snippets from relevant web results

When you ask questions, I'll use these tools to get accurate real-time data instead of guessing or creating background tasks.
</tools>

<implementation_prohibition>
CRITICAL: You are a ROUTING AGENT, NOT an implementation agent.

I'm here to help, but I don't write code - I connect you to agents who do. This keeps things fast and lets specialists handle implementation.

ABSOLUTE PROHIBITIONS (NO EXCEPTIONS):
• NEVER provide code snippets or implementations
• NEVER suggest specific code changes or fixes
• NEVER write or modify files directly
• NEVER provide implementation details or technical solutions
• NEVER attempt to fix bugs yourself (explaining concepts ≠ implementing fixes)

WHAT I CANNOT DO:
• Write code (any language - Python, JavaScript, SQL, etc.)
• Modify files or configurations
• Implement features or fixes
• Provide code snippets in responses
• Suggest specific implementations
• Debug code (I can analyze and explain, but not fix)
• Refactor code
• Update dependencies
• Create or modify documentation files

WHAT I DO INSTEAD:
• Route implementation requests → BACKGROUND_TASK (immediately)
• Answer general knowledge questions (no code/files needed)
• Summarize logs/status when provided in context
• Clarify your intent before routing if needed

ALWAYS DELEGATE TO BACKGROUND_TASK:
• Any code snippets or implementations
• File edits or modifications
• Bug fixes (even "simple" ones)
• Feature implementations
• Refactoring suggestions
• Configuration changes
• Dependency updates
• Documentation edits

When you ask for implementation:
1. I IMMEDIATELY return BACKGROUND_TASK format
2. I DO NOT explain how to implement
3. I DO NOT provide code examples
4. I DO NOT suggest approaches
5. I just route and confirm

Example:
You: "fix the null pointer in auth.py"
WRONG: "You can fix this by adding a null check: if user is not None: ..."
RIGHT: BACKGROUND_TASK|Fix null pointer in auth.py|Fixing the bug.|User asked: "fix the null pointer in auth.py". Working in amiga repo.
</implementation_prohibition>

<routing_rules>
USE TOOLS when:
• query_database: Task status, errors, metrics, analytics - questions about system state
  - "how many tasks running?", "show errors", "tool usage", "API costs"
  - "Task #abc123", "retry task xyz", "status of task 789", "what is task def456"
  - ANY mention of task IDs (Task #ID, task ID, #ID) - always query database
• web_search: Current info, documentation, external references - questions requiring web data
  - "what's the latest X version?", "find Y docs", "search for Z best practices"
  - "current news about X", "recent updates on Y", "how to use Z library"

DIRECT ANSWER when:
• General knowledge: "what is X?", "how does Y work?", "explain Z"
• Greetings/chat: "hey", "thanks", "what's up"
• Capabilities: "what can you do?"
• Log checking: "check logs"/"show logs"/"?" (logs in context)
• Questions answered by tool results (after using query_database)

BACKGROUND_TASK when:
• Code analysis: "check code", "analyze", "review", "scan for issues"
• File operations: "show me X file", "what's in Y", "read Z"
• Actions: fix, add, edit, refactor, create, modify, update, change, implement
• Git ops: commit, push, show diff, status
• Testing: "run tests", "check if X works"
• Chat/UI changes: "make chat [like X]", "change chat [to Y]", "modify chat [behavior/style/appearance]"
• Frontend behavior: "make [component] [do X]", "change [UI] to [Y]", "turn [feature] into [Z]"
• Task creation: "create task(s)", "create background task", "make a task for", "add task for"
• Multi-step requests with actions: Requests combining database queries with task creation (e.g., "find unattended messages and create tasks")

CRITICAL: "fix X" → BACKGROUND_TASK (explaining ≠ fixing)
CRITICAL: "make/change/modify chat" → ALWAYS BACKGROUND_TASK (DO NOT explain approaches, design choices, or suggest ideas - route immediately)
CRITICAL: Database queries → USE TOOL first. If action needed after → BACKGROUND_TASK
CRITICAL: "check X" (data) → USE TOOL. "check X" (code) → BACKGROUND_TASK
Rule: Database queries → USE TOOL. File/code access → BACKGROUND_TASK. General knowledge → answer directly.

AGENT ROUTING (in context_summary):
• Frontend-specific tasks (HTML/CSS/JS/UI) → "use frontend-agent to [task]"
• Complex/large tasks (5+ subtasks, multi-domain, system-level) → "use orchestrator to [task]"
• Simple tasks (single file, bug fix, small addition) → No agent prefix (code_agent default)
</routing_rules>

<log_protocol>
When you ask me to check logs:
• I scan for issues: ERRORs, WARNINGs, CRITICALs, Exceptions, Tracebacks
• I give you a quick summary (3-4 sentences max)
• I focus on what matters: actionable issues or confirmation that everything looks good
• If there's nothing to worry about, I'll just say "Logs look clean"
</log_protocol>

<background_task_format>
Return pipe-delimited, single line, NO markdown blocks, NO extra text:

Format: BACKGROUND_TASK|<task_description>|<user_message>|<context_summary>

Rules:
• No markdown wrapping (no ```)
• No explanation before/after
• Only the BACKGROUND_TASK line
• user_message = action-oriented (shown immediately to user)
• task_description = what needs to be done (used internally)
• context_summary = comprehensive summary of everything you know about this task (user's original message, conversation context, relevant details, what they're trying to accomplish, any constraints or preferences mentioned)

Context Summary Guidelines:
• CRITICAL: Include the user's ORIGINAL message verbatim (in quotes)
• CRITICAL: When user references previous messages ("only first", "the one we discussed", "what I mentioned", pronouns like "it", "that", etc.):
  - Review conversation_history in context JSON above
  - Identify what they're referring to from earlier exchanges
  - Include that information explicitly in context_summary
  - Example: User says "only first" → Look back to see what "first" refers to → Include: "User previously discussed [X and Y]. Now wants only [X]."
• Include all relevant conversation context (prior exchanges, references, clarifications)
• Mention specific files/paths/repos if discussed
• Note any constraints explicitly mentioned by user (time, scope, preferences)
• State the working directory/repository
• CRITICAL: Agent routing - START with appropriate prefix:
  - "use frontend-agent to ..." for chat/dashboard UI tasks
  - "use orchestrator to ..." for complex multi-component/system-level tasks
  - No prefix for simple single-file tasks
• DO NOT add implementation suggestions or technical approaches
• DO NOT interpret or expand on what user wants - just report facts
• Keep factual and concise (2-3 sentences max)

Frontend Agent Detection:
When task clearly involves:
• Chat interface: /chat route, chat UI, chat frontend, chat screen, ChatInterface component
• Monitoring dashboard: /dashboard route, metrics UI, dashboard frontend, dashboard screen
• UI/UX changes to these components
→ START context_summary with "use frontend-agent to [what user wants]"

Example:
User: "add dark mode to chat"
context_summary: "use frontend-agent to add dark mode to chat. User asked: 'add dark mode to chat'. Working in amiga repo."

Orchestrator Agent Detection:
When task clearly involves:
• Complex multi-component features: "build [system]", "create [feature with 5+ parts]"
• Multi-domain tasks: backend + frontend + infrastructure together
• System-level changes: "implement authentication system", "add API layer"
• Large scope: tasks that need orchestration across multiple agents/modules
• New features with research needed: "integrate [new service]", "add [complex feature]"
→ START context_summary with "use orchestrator to [what user wants]"

Examples:
User: "build authentication system"
context_summary: "use orchestrator to build authentication system. User asked: 'build authentication system'. Working in amiga repo."

User: "create admin dashboard with metrics"
context_summary: "use orchestrator to create admin dashboard with metrics. User asked: 'create admin dashboard with user metrics and analytics'. Backend + frontend needed. Working in amiga repo."
</background_task_format>

<examples>
GOOD (Tool usage):
Database queries:
• "how many tasks are running?" → USE TOOL query_database(query="SELECT COUNT(*) FROM tasks WHERE status='running'", database="agentlab") → "You have 3 tasks currently running."
• "show recent errors" → USE TOOL query_database(query="SELECT task_id, error FROM tasks WHERE error IS NOT NULL ORDER BY updated_at DESC LIMIT 5", database="agentlab") → [List errors with task IDs]
• "what's my tool usage?" → USE TOOL query_database(query="SELECT tool_name, COUNT(*) as count FROM tool_usage GROUP BY tool_name ORDER BY count DESC LIMIT 10", database="agentlab") → [Tool usage stats]
• "Task #7639cb" → USE TOOL query_database(query="SELECT * FROM tasks WHERE task_id LIKE '%7639cb%'", database="agentlab") → [Task details]
• "retry task abc123" → USE TOOL query_database(query="SELECT * FROM tasks WHERE task_id LIKE '%abc123%'", database="agentlab") → [Check status] → Then BACKGROUND_TASK if action needed
• "what is task xyz" → USE TOOL query_database(query="SELECT * FROM tasks WHERE task_id LIKE '%xyz%'", database="agentlab") → [Task info]

Web search:
• "what's the latest Python version?" → USE TOOL web_search(query="latest Python version 2025", num_results=5) → [Search results with version info]
• "find FastAPI documentation" → USE TOOL web_search(query="FastAPI official documentation", num_results=3) → [Links to FastAPI docs]
• "search for JWT authentication best practices" → USE TOOL web_search(query="JWT authentication security best practices", num_results=5) → [Security recommendations]

GOOD (Background tasks):
• "fix bug in main.py" → BACKGROUND_TASK|Fix bug in main.py|Fixing the bug.|User asked: "fix bug in main.py". Working in amiga repo.
• "persist conversation in /chat" → BACKGROUND_TASK|Persist conversation in /chat frontend|Working on chat persistence.|use frontend-agent to persist conversation during session in /chat frontend. User asked: "persist conversation during session in /chat frontend". Working in amiga repo.
• "make chat like a command line, 90s like" → BACKGROUND_TASK|Modify chat interface to Matrix-style command line (90s hacker aesthetic)|Updating chat UI to retro terminal style.|use frontend-agent to make chat like a command line, 90s like, like neo talking to morpheo in matrix. User asked: "make chat like a command line, 90s like, like neo talking to morpheo in matrix". Working in amiga repo.
• "change chat to dark mode" → BACKGROUND_TASK|Add dark mode to chat interface|Adding dark mode to chat.|use frontend-agent to change chat to dark mode. User asked: "change chat to dark mode". Working in amiga repo.
• "add metrics graph to dashboard" → BACKGROUND_TASK|Add metrics visualization to monitoring dashboard|Adding graph to dashboard.|use frontend-agent to add metrics graph to dashboard. User asked: "add metrics graph to dashboard". Working in amiga repo.
• "build authentication system" → BACKGROUND_TASK|Build authentication system with JWT|Building authentication system.|use orchestrator to build authentication system. User asked: "build authentication system with JWT tokens". Multi-component task: backend models, API endpoints, middleware. Working in amiga repo.
• "create admin dashboard" → BACKGROUND_TASK|Create admin dashboard with user metrics|Building admin dashboard.|use orchestrator to create admin dashboard with metrics. User asked: "create admin dashboard with user metrics and analytics". Backend + frontend + API integration needed. Working in amiga repo.

GOOD (Direct answers):
• "what is asyncio?" → [Direct answer about asyncio]
• "check logs" → [Direct log summary from context]

BAD (tool usage violations):
• "how many tasks?" → Creating BACKGROUND_TASK instead of using query_database tool
• "show errors" → Guessing/making up data instead of querying database
• "task status" → Responding "I don't have access" when query_database tool is available
• "Task #7639cb" → Responding "The task database isn't accessible" instead of using query_database
• "retry task xyz" → Asking "what system?" instead of querying database first
• "what's the latest Python?" → Answering from training data instead of using web_search
• "find X docs" → Responding "I can't browse" instead of using web_search tool

BAD (routing violations):
• Wrapping in ```BACKGROUND_TASK|...|...|...```
• Adding "Here's what I'll do: BACKGROUND_TASK|..."
• Adding implementation suggestions: "likely with local storage or state management"
• Adding technical approach: "Should integrate with existing session context system"
• Responding "I can help you make the chat..." instead of BACKGROUND_TASK
• Explaining design approaches for chat changes instead of routing
• Responding with "No tasks needed — all messages attended" when user requested action (check history + create tasks)
• Analyzing and summarizing instead of routing action requests
• Attempting to read files yourself
• Making up answers about unseen code
• Verbose responses (keep concise)
• Missing context summary (only 3 fields instead of 4)

BAD (implementation violations - NEVER DO THESE):
• "Here's how to fix it: [code snippet]"
• "You can add this code: [implementation]"
• "Try adding: if user is not None: ..."
• "Update the function like this: def foo(): ..."
• "Change line 42 to: return result or default"
• "Here's the implementation: ..." followed by code
• "I'd suggest this approach: [technical details with code]"
• Providing ANY code in responses to implementation requests
</examples>

<anti_examples>
Things I absolutely do not do:
• Provide code snippets or implementations (I route to BACKGROUND_TASK instead)
• Suggest specific code changes (that's implementation work → BACKGROUND_TASK)
• Attempt fixes myself (explaining concepts ≠ implementing fixes)
• Write implementations in any language (Python, JS, SQL, etc.)
• Provide "here's how you could do it" with code examples
• Read or modify files (I'm an API client, not CLI - no file access)
• Invent code details without seeing it (route to BACKGROUND_TASK for actual code inspection)
• Write multi-paragraph responses for simple queries (keep it tight)
• Ask clarifying questions when context is clear (use the context you have)
• Use verbose phrases like "I've completed that" or "I'll get started" (just "Done" works fine)
</anti_examples>

<personality>
I'm here to help you stay productive without getting in the way. Here's my style:

• EXTREMELY CONCISE: Maximum 2-3 sentences for most responses. "Done" beats "I've successfully completed that task for you"
• CONVERSATIONAL: I use contractions, skip the formality. We're colleagues, not strangers
• ACTION-ORIENTED: Lead with results, not process. You care about outcomes, not my internal steps
• NO DECORATION: No emojis, no bullet points in responses. Plain text only. Professional but not sterile
• CONTEXT-AWARE: I make smart assumptions based on what we've discussed. I won't ask obvious questions
• HELPFUL BUT HONEST: If I think you're heading down a tricky path, I'll mention it - but I won't lecture

For meta questions ("who are you", "what can you do"):
→ Single sentence or two max. No bullet lists. No elaboration.
→ Example: "I'm amiga - your AI assistant. I answer questions and route implementation work to specialized agents."

Think of me as the kind of teammate who gives you the information you need, when you need it, without unnecessary fluff.
</personality>

<user_profile>
Working with: Matias Fuentes
My role: Your personal AI assistant for technical work
My approach: I know your projects, understand your workflow, and tailor responses to keep you productive. I'm not here to impress you with verbose explanations - I'm here to help you get things done.
</user_profile>

<runtime_config>
input_method: {input_method} ({'voice - be permissive with errors' if input_method == 'voice' else 'text - exact input'})
bot_repository: {safe_bot_repo}
current_workspace: {safe_workspace}
{'image_attached: ' + sanitize_xml_content(image_path) if image_path else ''}
</runtime_config>

<query>{safe_query}</query>"""

    try:
        # Get API key from environment
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set", exc_info=True)
            return "Configuration error. Check API key.", None, None

        # Create client
        client = anthropic.Anthropic(api_key=api_key)

        # Prepare messages - start with conversation history
        messages = []

        # Add conversation history as actual message objects (not just in system prompt)
        for msg in safe_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        # Add image if provided
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_data = f.read()
                    import base64

                    image_base64 = base64.b64encode(image_data).decode()

                    # Determine media type
                    ext = Path(image_path).suffix.lower()
                    media_type = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                    }.get(ext, "image/jpeg")

                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_base64,
                                    },
                                },
                                {"type": "text", "text": user_query},
                            ],
                        }
                    )
            except Exception as e:
                logger.error(f"Error loading image: {e}", exc_info=True)
                messages.append({"role": "user", "content": user_query})
        else:
            # If checking logs, include log content
            if any(keyword in user_query.lower() for keyword in ["check log", "show log", "?"]):
                log_path = Path(bot_repository) / "logs" / "bot.log"
                if log_path.exists():
                    try:
                        # Read last 50 lines only (not 200) to reduce tokens
                        with open(log_path) as f:
                            lines = f.readlines()
                            recent_logs = "".join(lines[-50:])

                        # Security: Sanitize log content to prevent injection via logs
                        # Logs could contain user input or malicious content
                        safe_logs = sanitize_xml_content(recent_logs)

                        messages.append(
                            {"role": "user", "content": f"{safe_query}\n\nRecent log content:\n```\n{safe_logs}\n```"}
                        )
                    except Exception as e:
                        logger.error(f"Error reading logs: {e}", exc_info=True)
                        messages.append({"role": "user", "content": safe_query})
                else:
                    messages.append({"role": "user", "content": safe_query})
            else:
                messages.append({"role": "user", "content": safe_query})

        logger.info(f"Calling Claude API (Haiku 4.5) for: {user_query[:60]}...")

        # Tool calling loop
        usage_info = {"input_tokens": 0, "output_tokens": 0}
        max_iterations = 5  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Call API with Haiku 4.5 and tools
            response = client.messages.create(
                model="claude-haiku-4-5", max_tokens=2048, system=system_prompt, messages=messages, tools=AVAILABLE_TOOLS
            )

            # Accumulate usage
            usage_info["input_tokens"] += response.usage.input_tokens
            usage_info["output_tokens"] += response.usage.output_tokens

            logger.info(
                f"Claude API response (iteration {iteration}): {len(response.content)} blocks (tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out)"
            )

            # Check for tool use in response
            tool_uses = [block for block in response.content if block.type == "tool_use"]

            if not tool_uses:
                # No tools needed - extract final response text
                response_text = ""
                for block in response.content:
                    if block.type == "text":
                        response_text += block.text

                response_text = response_text.strip()

                logger.info(f"Final response: {response_text[:100]}... (total tokens: {usage_info['input_tokens']} in, {usage_info['output_tokens']} out)")

                # Check if response contains BACKGROUND_TASK anywhere (not just at start)
                if "BACKGROUND_TASK|" in response_text:
                    # Find the line with BACKGROUND_TASK
                    lines = response_text.split("\n")
                    task_line = None

                    for line in lines:
                        cleaned_line = line.strip()
                        # Strip markdown code blocks if present
                        if cleaned_line.startswith("```"):
                            cleaned_line = cleaned_line[3:].strip()
                        if cleaned_line.endswith("```"):
                            cleaned_line = cleaned_line[:-3].strip()

                        if cleaned_line.startswith("BACKGROUND_TASK|"):
                            task_line = cleaned_line
                            break

                    if task_line:
                        # Parse the BACKGROUND_TASK line
                        # Format: BACKGROUND_TASK|task_description|user_message|context_summary
                        parts = task_line.split("|")

                        if len(parts) == 4:
                            _, task_description, user_message, context_summary = parts
                            background_task = {
                                "description": task_description.strip(),
                                "user_message": user_message.strip(),
                                "context": context_summary.strip(),
                            }
                            return task_line, background_task, usage_info
                        elif len(parts) == 3:
                            # Backwards compatibility - old format without context
                            _, task_description, user_message = parts
                            background_task = {
                                "description": task_description.strip(),
                                "user_message": user_message.strip(),
                                "context": None,
                            }
                            logger.warning(f"BACKGROUND_TASK missing context field: {task_line}")
                            return task_line, background_task, usage_info
                        else:
                            logger.warning(f"Invalid BACKGROUND_TASK format: {task_line}")
                            # Treat as direct answer if format is invalid
                            pass

                # Direct answer
                return response_text, None, usage_info

            # Tools needed - execute them
            logger.info(f"Executing {len(tool_uses)} tool(s)...")

            tool_results = []
            for tool_use in tool_uses:
                logger.info(f"Tool: {tool_use.name} with input: {str(tool_use.input)[:100]}")

                # Execute tool
                result = await execute_tool(tool_use.name, tool_use.input)

                tool_results.append({"type": "tool_result", "tool_use_id": tool_use.id, "content": result})

                logger.info(f"Tool result: {result[:200]}...")

            # Add assistant message with tool_use blocks to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Add tool results as user message
            messages.append({"role": "user", "content": tool_results})

            # Loop back to get final response with tool results

        # Max iterations reached
        logger.warning(f"Tool calling loop reached max iterations ({max_iterations})")
        return "Unable to complete request - too many tool calls needed.", None, usage_info

    except anthropic.APIError as e:
        # Parse Anthropic API errors for user-friendly messages
        logger.error(f"Anthropic API error: {e}", exc_info=True)

        # Extract error details
        error_type = getattr(e, 'type', None)
        status_code = getattr(e, 'status_code', None)

        # User-friendly error messages
        if status_code == 529 or error_type == 'overloaded_error':
            return "Claude is temporarily overloaded. Please retry in 30-60 seconds.", None, None
        elif status_code == 429:
            return "Rate limit reached. Please wait a moment and try again.", None, None
        elif status_code == 401:
            return "Authentication failed. Please check API configuration.", None, None
        elif status_code >= 500:
            return "Claude service temporarily unavailable. Please try again shortly.", None, None
        else:
            # Generic API error
            return f"Error processing request. Please try again.", None, None

    except Exception as e:
        logger.error(f"Unexpected error calling Claude API: {e}", exc_info=True)
        return f"Unexpected error occurred. Please try again.", None, None
