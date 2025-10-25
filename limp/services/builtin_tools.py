"""
Builtin tools for LIMP.
These tools provide core functionality that doesn't require external API calls.
"""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LimpBuiltinTool:
    """Base class for builtin tools."""
    
    def execute(self, arguments: str) -> Dict[str, Any]:
        """Execute the builtin tool with error handling."""
        try:
            return self._execute(arguments)
        except Exception as e:
            logger.error(f"Error executing builtin tool {self.__class__.__name__}: {e}")
            return {
                "success": False,
                "error": f"Failed to execute tool: {str(e)}"
            }
    
    def _execute(self, arguments: str) -> Dict[str, Any]:
        """Execute the builtin tool implementation."""
        raise NotImplementedError("Subclasses must implement _execute method")


class LimpBuiltinStartOver(LimpBuiltinTool):
    """Builtin tool to start a new conversation."""
    
    def _execute(self, arguments: str) -> Dict[str, Any]:
        """Execute the start over tool."""
        # Parse arguments if provided, ignore JSON errors
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            # Ignore JSON parsing errors for this tool
            args = {}
        
        # Return success result
        return {
            "success": True,
            "result": "New conversation successfully started",
            "action": "start_over"
        }
