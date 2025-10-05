"""
Tools service for OpenAPI integration.
"""

import requests
import json
import yaml
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class ToolsService:
    """Tools service for OpenAPI integration."""
    
    def __init__(self):
        self.openapi_specs = {}  # Cache for loaded OpenAPI specs
    
    def load_openapi_spec(self, spec_url: str) -> Dict[str, Any]:
        """Load OpenAPI specification from JSON or YAML format."""
        try:
            if spec_url.startswith("http"):
                response = requests.get(spec_url)
                response.raise_for_status()
                content = response.text
                
                # Try to determine format from content-type header or file extension
                content_type = response.headers.get('content-type', '').lower()
                if 'yaml' in content_type or 'yml' in content_type or spec_url.lower().endswith(('.yaml', '.yml')):
                    spec = yaml.safe_load(content)
                else:
                    # Default to JSON, but try YAML if JSON fails
                    try:
                        spec = json.loads(content)
                    except json.JSONDecodeError:
                        spec = yaml.safe_load(content)
            else:
                # For local files, determine format by file extension
                if spec_url.lower().endswith(('.yaml', '.yml')):
                    with open(spec_url, 'r') as f:
                        spec = yaml.safe_load(f)
                else:
                    # Default to JSON, but try YAML if JSON fails
                    with open(spec_url, 'r') as f:
                        content = f.read()
                        try:
                            spec = json.loads(content)
                        except json.JSONDecodeError:
                            spec = yaml.safe_load(content)
            
            return spec
        except Exception as e:
            logger.error(f"Failed to load OpenAPI spec from {spec_url}: {e}")
            raise
    
    def _get_or_load_spec(self, spec_url: str) -> Dict[str, Any]:
        """Get cached OpenAPI spec or load it if not cached."""
        if spec_url not in self.openapi_specs:
            self.openapi_specs[spec_url] = self.load_openapi_spec(spec_url)
        return self.openapi_specs[spec_url]
    
    def convert_to_openai_tools(self, openapi_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert OpenAPI spec to OpenAI tools format."""
        tools = []
        
        for path, methods in openapi_spec.get("paths", {}).items():
            for method, operation in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue
                
                # Build comprehensive description
                description_parts = []
                
                # Add summary if available
                if operation.get("summary"):
                    description_parts.append(operation["summary"])
                
                # Add detailed description if available
                if operation.get("description"):
                    description_parts.append(operation["description"])
                
                # Add tags for context
                if operation.get("tags"):
                    tags_str = ", ".join(operation["tags"])
                    description_parts.append(f"Tags: {tags_str}")
                
                # Combine all description parts
                full_description = "\n\n".join(description_parts) if description_parts else ""
                
                tool = {
                    "type": "function",
                    "function": {
                        "name": operation.get("operationId", f"{method}_{path}"),
                        "description": full_description,
                        "parameters": self._convert_parameters(operation.get("parameters", []))
                    }
                }
                tools.append(tool)
        
        return tools
    
    def execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        system_config: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute tool call against external system."""
        try:
            # Parse tool call arguments
            arguments = json.loads(tool_call["function"]["arguments"])
            
            # Get cached OpenAPI spec (should already be loaded)
            openapi_spec = self._get_or_load_spec(system_config["openapi_spec"])
            
            # Find the operation in OpenAPI spec
            operation = self._find_operation(openapi_spec, tool_call["function"]["name"])
            if not operation:
                return {"error": f"Operation {tool_call['function']['name']} not found"}
            
            # Build request
            method = operation["method"].upper()
            url = f"{system_config['base_url']}{operation['path']}"
            
            headers = {"Content-Type": "application/json"}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            
            # Execute request
            if method == "GET":
                response = requests.get(url, params=arguments, headers=headers)
            elif method == "POST":
                response = requests.post(url, json=arguments, headers=headers)
            elif method == "PUT":
                response = requests.put(url, json=arguments, headers=headers)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers)
            else:
                return {"error": f"Unsupported method: {method}"}
            
            response.raise_for_status()
            
            return {
                "success": True,
                "data": response.json() if response.content else None,
                "status_code": response.status_code
            }
            
        except requests.RequestException as e:
            logger.error(f"Tool call failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            }
        except Exception as e:
            logger.error(f"Tool call execution error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _convert_parameters(self, parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert OpenAPI parameters to JSON schema."""
        properties = {}
        required = []
        
        for param in parameters:
            param_name = param["name"]
            param_schema = param.get("schema", {})
            
            # Build comprehensive property schema
            property_schema = {
                "type": param_schema.get("type", "string"),
                "description": param.get("description", "")
            }
            
            # Add format information if available
            if param_schema.get("format"):
                property_schema["format"] = param_schema["format"]
            
            # Add enum values if available
            if param_schema.get("enum"):
                property_schema["enum"] = param_schema["enum"]
            
            # Add minimum/maximum for numeric types
            if param_schema.get("minimum") is not None:
                property_schema["minimum"] = param_schema["minimum"]
            if param_schema.get("maximum") is not None:
                property_schema["maximum"] = param_schema["maximum"]
            
            # Add pattern for string types
            if param_schema.get("pattern"):
                property_schema["pattern"] = param_schema["pattern"]
            
            # Handle array types - add items specification
            if param_schema.get("type") == "array":
                items_schema = param_schema.get("items", {})
                property_schema["items"] = {
                    "type": items_schema.get("type", "string")
                }
                # Add format to array items if available
                if items_schema.get("format"):
                    property_schema["items"]["format"] = items_schema["format"]
                # Add enum to array items if available
                if items_schema.get("enum"):
                    property_schema["items"]["enum"] = items_schema["enum"]
            
            # Add parameter location context to description
            param_in = param.get("in", "query")
            if param_in != "query":
                location_context = {
                    "path": "URL path parameter",
                    "header": "HTTP header parameter", 
                    "cookie": "HTTP cookie parameter"
                }.get(param_in, f"{param_in} parameter")
                if property_schema["description"]:
                    property_schema["description"] = f"{property_schema['description']} ({location_context})"
                else:
                    property_schema["description"] = location_context
            
            properties[param_name] = property_schema
            
            if param.get("required", False):
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    def _find_operation(self, openapi_spec: Dict[str, Any], operation_id: str) -> Optional[Dict[str, Any]]:
        """Find operation by operationId in OpenAPI spec."""
        for path, methods in openapi_spec.get("paths", {}).items():
            for method, operation in methods.items():
                if operation.get("operationId") == operation_id:
                    return {
                        "method": method,
                        "path": path,
                        "operation": operation
                    }
        return None
    
    def get_available_tools(self, system_configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get all available tools from system configurations."""
        all_tools = []
        
        for system_config in system_configs:
            try:
                # Load and cache the spec
                spec = self._get_or_load_spec(system_config["openapi_spec"])
                tools = self.convert_to_openai_tools(spec)
                
                # Add system context to each tool for internal tracking
                for tool in tools:
                    tool["system"] = system_config["name"]
                
                all_tools.extend(tools)

                logger.debug(f"Loaded tools for system {system_config['name']}: {tools}")
            except Exception as e:
                logger.error(f"Failed to load tools for system {system_config['name']}: {e}")
        
        return all_tools
    
    def get_cleaned_tools_for_openai(self, system_configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get tools cleaned for OpenAI API (without system field)."""
        tools = self.get_available_tools(system_configs)
        return self._clean_tools_for_openai(tools)
    
    def _clean_tools_for_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove system-specific fields from tools for OpenAI API."""
        cleaned_tools = []
        for tool in tools:
            # Create a copy without the system field
            cleaned_tool = {
                "type": tool["type"],
                "function": tool["function"]
            }
            cleaned_tools.append(cleaned_tool)
        return cleaned_tools
    
    def get_system_name_for_tool(self, tool_name: str, system_configs: List[Dict[str, Any]]) -> str:
        """Get system name for a specific tool."""
        # Get all tools with system information
        all_tools = self.get_available_tools(system_configs)
        
        # Find the tool and return its system
        for tool in all_tools:
            if tool["function"]["name"] == tool_name:
                return tool["system"]
        
        # Fallback to first system if not found
        return system_configs[0]["name"] if system_configs else "default"

