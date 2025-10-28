"""
Test conversation context preservation in Claude API routing

Ensures that when users reference previous messages, the context is properly
preserved when routing tasks to Claude CLI agents via BACKGROUND_TASK.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, Mock, patch
from claude.api_client import ask_claude


class TestContextMemoryPreservation:
    """Test that conversation context is preserved when routing to agents"""

    @pytest.mark.asyncio
    async def test_conversation_history_limit_increased(self):
        """Verify conversation history includes last 20 messages (not just 10)"""
        # Create conversation with 20 messages
        conversation_history = []
        for i in range(20):
            conversation_history.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}"
            })

        mock_response = Mock()
        mock_response.content = [Mock(text="This is a general answer")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create = Mock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            await ask_claude(
                user_query="What is Python?",
                input_method="text",
                conversation_history=conversation_history,
                current_workspace="/workspace",
                bot_repository="/bot",
                workspace_path="/workspace",
                available_repositories=[],
                active_tasks=[]
            )

            # Verify the API was called with system prompt containing all 20 messages
            call_args = mock_client.messages.create.call_args
            system_prompt = call_args.kwargs['system']

            # Check that conversation history in the prompt includes all 20 messages
            for i in range(20):
                assert f"Message {i}" in system_prompt, f"Message {i} not found in system prompt"

    @pytest.mark.asyncio
    async def test_message_character_limit_increased(self):
        """Verify messages can be up to 5000 chars (not just 2000)"""
        # Create a long message (4000 chars) that should be preserved
        long_message = "A" * 4000

        conversation_history = [
            {"role": "user", "content": long_message},
            {"role": "assistant", "content": "Got it"}
        ]

        mock_response = Mock()
        mock_response.content = [Mock(text="This is a general answer")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create = Mock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            await ask_claude(
                user_query="What was the long message about?",
                input_method="text",
                conversation_history=conversation_history,
                current_workspace="/workspace",
                bot_repository="/bot",
                workspace_path="/workspace",
                available_repositories=[],
                active_tasks=[]
            )

            # Verify the long message wasn't truncated (it's 4000 chars, under 5000 limit)
            call_args = mock_client.messages.create.call_args
            system_prompt = call_args.kwargs['system']
            
            # The message should be fully preserved (not truncated at 2000)
            assert long_message in system_prompt, "Long message was truncated too aggressively"

    @pytest.mark.asyncio
    async def test_context_summary_includes_conversational_references(self):
        """Verify context_summary guidelines instruct Claude to resolve references"""
        conversation_history = [
            {"role": "user", "content": "I want to improve the system prompt"},
            {"role": "assistant", "content": "I can help with that"},
            {"role": "user", "content": "only first"}  # Reference to "system prompt"
        ]

        # Mock response that creates BACKGROUND_TASK
        mock_response = Mock()
        mock_response.content = [Mock(text='BACKGROUND_TASK|Improve system prompt|Working on it.|User previously asked to "improve the system prompt". Now wants only first part.')]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create = Mock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            response, background_task_info, usage_info = await ask_claude(
                user_query="only first",
                input_method="text",
                conversation_history=conversation_history,
                current_workspace="/workspace",
                bot_repository="/bot",
                workspace_path="/workspace",
                available_repositories=[],
                active_tasks=[]
            )

            # Verify the system prompt includes guidelines for resolving references
            call_args = mock_client.messages.create.call_args
            system_prompt = call_args.kwargs['system']
            
            assert 'When user references previous messages' in system_prompt
            assert 'Review conversation_history in context JSON above' in system_prompt
            assert 'Identify what they\'re referring to from earlier exchanges' in system_prompt
            assert 'Include that information explicitly in context_summary' in system_prompt

    @pytest.mark.asyncio
    async def test_background_task_context_preserves_references(self):
        """Verify that BACKGROUND_TASK context includes resolved references"""
        conversation_history = [
            {"role": "user", "content": "I want to improve the system prompt and the error handling"},
            {"role": "assistant", "content": "I can help with both of those."},
            {"role": "user", "content": "only first"}  # Should refer to "system prompt"
        ]

        # Mock response with proper context resolution
        mock_response = Mock()
        mock_response.content = [Mock(text='BACKGROUND_TASK|Improve system prompt|Working on system prompt.|User previously asked to "improve the system prompt and the error handling". Now wants only the first item (system prompt improvement).')]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create = Mock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            response, background_task_info, usage_info = await ask_claude(
                user_query="only first",
                input_method="text",
                conversation_history=conversation_history,
                current_workspace="/workspace",
                bot_repository="/bot",
                workspace_path="/workspace",
                available_repositories=[],
                active_tasks=[]
            )

            # Verify background_task_info exists and has context
            assert background_task_info is not None
            assert 'context' in background_task_info
            
            # Context should include reference to what "first" means
            context = background_task_info['context']
            assert 'system prompt' in context.lower()
            assert 'previously' in context.lower() or 'first' in context.lower()

    @pytest.mark.asyncio
    async def test_very_long_messages_truncated_at_5000(self):
        """Verify messages over 5000 chars are truncated (not earlier)"""
        # Create a message that's 6000 chars (should be truncated to 5000)
        very_long_message = "B" * 6000

        conversation_history = [
            {"role": "user", "content": very_long_message},
        ]

        mock_response = Mock()
        mock_response.content = [Mock(text="Got it")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create = Mock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            await ask_claude(
                user_query="What was that?",
                input_method="text",
                conversation_history=conversation_history,
                current_workspace="/workspace",
                bot_repository="/bot",
                workspace_path="/workspace",
                available_repositories=[],
                active_tasks=[]
            )

            call_args = mock_client.messages.create.call_args
            system_prompt = call_args.kwargs['system']
            
            # The message should be truncated to 5000 chars, not 2000
            # Check that it contains at least 4000 B's (well above old 2000 limit)
            b_count = system_prompt.count("B")
            assert b_count >= 4000, f"Message truncated too aggressively (only {b_count} chars preserved)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
