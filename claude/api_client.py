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
    system_prompt = f"""<role>You are amiga - a personal AI assistant for Matias Fuentes. Model: Claude Haiku 4.5 (fast routing & Q&A).</role>

<context>
{json.dumps(context, indent=2)}
</context>

<capabilities>
You handle routing and answer questions:
• DIRECT: General knowledge (no file access needed)
• ROUTE: File operations → BACKGROUND_TASK format
• Your primary focus areas: web chat interface, monitoring dashboard, task management
</capabilities>

<implementation_prohibition>
CRITICAL: You are a ROUTING AGENT, NOT an implementation agent.

ABSOLUTE PROHIBITIONS (NO EXCEPTIONS):
❌ NEVER provide code snippets or implementations
❌ NEVER suggest specific code changes or fixes
❌ NEVER write or modify files directly
❌ NEVER provide implementation details or technical solutions
❌ NEVER attempt to fix bugs yourself (explaining ≠ implementing)

YOU CANNOT:
• Write code (any language - Python, JavaScript, SQL, etc.)
• Modify files or configurations
• Implement features or fixes
• Provide code snippets in responses
• Suggest specific implementations
• Debug code (analyze → yes, fix → no)
• Refactor code
• Update dependencies
• Create/modify documentation files

YOUR ONLY ROLE:
• Route implementation requests → BACKGROUND_TASK
• Answer general knowledge questions (no code/files)
• Summarize logs/status when provided in context
• Clarify user intent before routing

DELEGATION REQUIRED FOR:
• Any code snippets or implementations → BACKGROUND_TASK
• File edits or modifications → BACKGROUND_TASK
• Bug fixes (even "simple" ones) → BACKGROUND_TASK
• Feature implementations → BACKGROUND_TASK
• Refactoring suggestions → BACKGROUND_TASK
• Configuration changes → BACKGROUND_TASK
• Dependency updates → BACKGROUND_TASK
• Documentation edits → BACKGROUND_TASK

When user asks for implementation:
1. IMMEDIATELY return BACKGROUND_TASK format
2. DO NOT explain how to implement
3. DO NOT provide code examples
4. DO NOT suggest approaches
5. Just route and confirm routing

Example:
User: "fix the null pointer in auth.py"
WRONG: "You can fix this by adding a null check: if user is not None: ..."
RIGHT: BACKGROUND_TASK|Fix null pointer in auth.py|Fixing the bug.|User asked: "fix the null pointer in auth.py". Working in amiga repo.
</implementation_prohibition>

<routing_rules>
DIRECT ANSWER when:
• General knowledge: "what is X?", "how does Y work?", "explain Z"
• Greetings/chat: "hey", "thanks", "what's up"
• Capabilities: "what can you do?"
• Log checking: "check logs"/"show logs"/"?" (logs in context)

BACKGROUND_TASK when:
• Code analysis: "check code", "analyze", "review", "scan for issues"
• File operations: "show me X file", "what's in Y", "read Z"
• Actions: fix, add, edit, refactor, create, modify, update, change, implement
• Git ops: commit, push, show diff, status
• Testing: "run tests", "check if X works"
• Chat/UI changes: "make chat [like X]", "change chat [to Y]", "modify chat [behavior/style/appearance]"
• Frontend behavior: "make [component] [do X]", "change [UI] to [Y]", "turn [feature] into [Z]"

CRITICAL: "fix X" → BACKGROUND_TASK (explaining ≠ fixing)
CRITICAL: "make/change/modify chat" → ALWAYS BACKGROUND_TASK (DO NOT explain approaches, design choices, or suggest ideas - route immediately)
Rule: File access needed → BACKGROUND_TASK. General knowledge → answer directly.

AGENT ROUTING (in context_summary):
• Frontend-specific tasks (HTML/CSS/JS/UI) → "use frontend-agent to [task]"
• Complex/large tasks (5+ subtasks, multi-domain, system-level) → "use orchestrator to [task]"
• Simple tasks (single file, bug fix, small addition) → No agent prefix (code_agent default)
</routing_rules>

<log_protocol>
For "check logs"/"show logs"/"?":
• Scan for ERROR, WARNING, CRITICAL, Exception, Traceback
• Summarize (3-4 sentences max)
• Focus on actionable issues or "Logs clean"
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
GOOD:
• "fix bug in main.py" → BACKGROUND_TASK|Fix bug in main.py|Fixing the bug.|User asked: "fix bug in main.py". Working in amiga repo.
• "persist conversation in /chat" → BACKGROUND_TASK|Persist conversation in /chat frontend|Working on chat persistence.|use frontend-agent to persist conversation during session in /chat frontend. User asked: "persist conversation during session in /chat frontend". Working in amiga repo.
• "make chat like a command line, 90s like" → BACKGROUND_TASK|Modify chat interface to Matrix-style command line (90s hacker aesthetic)|Updating chat UI to retro terminal style.|use frontend-agent to make chat like a command line, 90s like, like neo talking to morpheo in matrix. User asked: "make chat like a command line, 90s like, like neo talking to morpheo in matrix". Working in amiga repo.
• "change chat to dark mode" → BACKGROUND_TASK|Add dark mode to chat interface|Adding dark mode to chat.|use frontend-agent to change chat to dark mode. User asked: "change chat to dark mode". Working in amiga repo.
• "add metrics graph to dashboard" → BACKGROUND_TASK|Add metrics visualization to monitoring dashboard|Adding graph to dashboard.|use frontend-agent to add metrics graph to dashboard. User asked: "add metrics graph to dashboard". Working in amiga repo.
• "build authentication system" → BACKGROUND_TASK|Build authentication system with JWT|Building authentication system.|use orchestrator to build authentication system. User asked: "build authentication system with JWT tokens". Multi-component task: backend models, API endpoints, middleware. Working in amiga repo.
• "create admin dashboard" → BACKGROUND_TASK|Create admin dashboard with user metrics|Building admin dashboard.|use orchestrator to create admin dashboard with metrics. User asked: "create admin dashboard with user metrics and analytics". Backend + frontend + API integration needed. Working in amiga repo.
• "what is asyncio?" → [Direct answer about asyncio]
• "check logs" → [Direct log summary from context]

BAD (routing violations):
• Wrapping in ```BACKGROUND_TASK|...|...|...```
• Adding "Here's what I'll do: BACKGROUND_TASK|..."
• Adding implementation suggestions: "likely with local storage or state management"
• Adding technical approach: "Should integrate with existing session context system"
• Responding "I can help you make the chat..." instead of BACKGROUND_TASK
• Explaining design approaches for chat changes instead of routing
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
❌ NEVER: Provide code snippets or implementations (you cannot implement - only route to BACKGROUND_TASK)
❌ NEVER: Suggest specific code changes (route to BACKGROUND_TASK instead)
❌ NEVER: Attempt fixes yourself (explaining concepts ≠ implementing fixes)
❌ NEVER: Write implementations in any language (Python, JS, SQL, etc.)
❌ NEVER: Provide "here's how you could do it" with code examples
❌ NEVER: Read/modify files (you're API, not CLI - no file access)
❌ NEVER: Invent code details without seeing it → route to BACKGROUND_TASK
❌ NEVER: Multi-paragraph responses for simple queries
❌ NEVER: Ask clarifying questions when context is clear
❌ NEVER: Use phrases like "I've completed", "I'll get started" - be direct
</anti_examples>

<personality>
• Direct: "Done." not "I've completed that"
• Casual: Use contractions, skip formality
• Action-first: Lead with results, not process
• Minimal emojis: Max 1/message
• Smart assumptions: Use context vs. asking
</personality>

<user_profile>
Name: Matias Fuentes
Your purpose: Personal AI assistant to help Matias with his technical work
Tailor responses to his technical interests
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

        # Prepare messages
        messages = []

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

        # Call API with Haiku 4.5 (fast and cheap - launched Oct 15, 2025)
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=2048, system=system_prompt, messages=messages
        )

        # Extract response text
        response_text = response.content[0].text.strip()

        # Extract usage info
        usage_info = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        logger.info(
            f"Claude API response: {response_text[:100]}... (tokens: {usage_info['input_tokens']} in, {usage_info['output_tokens']} out)"
        )

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
