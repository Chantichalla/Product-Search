"""
Unit Test: Memory & Query Rewriting Integration
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMemoryIntegration(unittest.TestCase):
    
    @patch('agent.single_agent.nodes.deep_memory')
    @patch('config.llm_config.get_query_planner_llm')
    def test_query_rewriter_integration(self, mock_get_llm, mock_memory):
        """Test if query_rewriter calls deep_memory.add_turn and search_context"""
        print("\nTesting query_rewriter_node integration...")
        from agent.single_agent.nodes import query_rewriter_node
        
        # Setup Mock LLM
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value.content = "Rewritten Query"
        mock_get_llm.return_value = mock_llm_instance
        
        # Setup Mock Memory
        mock_memory.search_context.return_value = [
            {"role": "user", "content": "I like red phones", "timestamp": 12345}
        ]
        
        state = {
            "query": "Which one is better?",
            "history": [{"role": "user", "content": "iPhone 15"}, {"role": "assistant", "content": "It is great."}],
            "step_count": 0
        }
        
        # Run Node
        try:
            result = query_rewriter_node(state)
        except Exception as e:
            self.fail(f"query_rewriter_node raised exception: {e}")
        
        # Assertions
        mock_memory.add_turn.assert_called_with("user", "Which one is better?")
        mock_memory.search_context.assert_called_with("Which one is better?", k=2, threshold=0.5)
        print("✅ Query Rewriter & Deep Memory Flow Verified")


if __name__ == "__main__":
    unittest.main()
