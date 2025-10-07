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
                
                # Skip generic return descriptions to save prompt space
                # Response schema info will be injected dynamically when tool is called
                
                # Add request body information for POST/PUT operations
                if method.upper() in ["POST", "PUT", "PATCH"]:
                    request_body_info = self._extract_request_body_info(operation, openapi_spec)
                    if request_body_info:
                        description_parts.append(f"Request body: {request_body_info}")
                
                # Add tags for context
                if operation.get("tags"):
                    tags_str = ", ".join(operation["tags"])
                    description_parts.append(f"Tags: {tags_str}")
                
                # Combine all description parts
                full_description = "\n\n".join(description_parts) if description_parts else ""
                
                # Convert parameters including request body
                parameters = self._convert_parameters(operation.get("parameters", []))
                if method.upper() in ["POST", "PUT", "PATCH"]:
                    request_body_params = self._convert_request_body(operation, openapi_spec)
                    if request_body_params:
                        parameters["properties"].update(request_body_params["properties"])
                        parameters["required"].extend(request_body_params["required"])
                
                tool = {
                    "type": "function",
                    "function": {
                        "name": operation.get("operationId", f"{method}_{path}"),
                        "description": full_description,
                        "parameters": parameters
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

            logger.info(f"Executing tool call: {method} {url} with headers: {headers} and arguments: {arguments}")
            
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

            logger.info(f"Tool call response: {response.json()}")
            
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
    
    def _extract_response_info(self, operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Extract response schema information for description."""
        responses = operation.get("responses", {})
        if not responses:
            return ""
        
        # Look for 200/201 success responses first
        success_codes = ["200", "201", "202"]
        response_schema = None
        
        for code in success_codes:
            if code in responses:
                response = responses[code]
                content = response.get("content", {})
                if "application/json" in content:
                    response_schema = content["application/json"].get("schema")
                    break
        
        if not response_schema:
            # Fallback to any response with JSON content
            for code, response in responses.items():
                content = response.get("content", {})
                if "application/json" in content:
                    response_schema = content["application/json"].get("schema")
                    break
        
        if not response_schema:
            return ""
        
        return self._describe_schema(response_schema, openapi_spec)
    
    def _extract_request_body_info(self, operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Extract request body schema information for description."""
        request_body = operation.get("requestBody")
        if not request_body:
            return ""
        
        content = request_body.get("content", {})
        if "application/json" in content:
            schema = content["application/json"].get("schema")
            if schema:
                return self._describe_schema(schema, openapi_spec)
        
        return ""
    
    def _describe_schema(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Generate a human-readable description of a schema."""
        if not schema:
            return ""
        
        # Handle $ref references
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/"):
                # Local reference
                ref_parts = ref_path[2:].split("/")
                ref_schema = openapi_spec
                for part in ref_parts:
                    ref_schema = ref_schema.get(part, {})
                return self._describe_schema(ref_schema, openapi_spec)
            return "Referenced object"
        
        schema_type = schema.get("type", "object")
        
        if schema_type == "array":
            items = schema.get("items", {})
            if "$ref" in items:
                # Try to get the referenced schema name
                ref_name = items["$ref"].split("/")[-1]
                return f"Array of {ref_name}"
            else:
                item_type = items.get("type", "object")
                return f"Array of {item_type}s"
        
        elif schema_type == "object":
            properties = schema.get("properties", {})
            if not properties:
                return "Object"
            
            # Get a summary of the object structure
            prop_descriptions = []
            for prop_name, prop_schema in list(properties.items())[:5]:  # Limit to first 5 properties
                prop_type = prop_schema.get("type", "object")
                if "$ref" in prop_schema:
                    ref_name = prop_schema["$ref"].split("/")[-1]
                    prop_descriptions.append(f"{prop_name} ({ref_name})")
                else:
                    prop_descriptions.append(f"{prop_name} ({prop_type})")
            
            description = f"Object with {', '.join(prop_descriptions)}"
            if len(properties) > 5:
                description += f" and {len(properties) - 5} more fields"
            
            return description
        
        elif schema_type in ["string", "integer", "number", "boolean"]:
            return schema_type
        
        return "Object"
    
    def _convert_request_body(self, operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Convert request body schema to parameters."""
        request_body = operation.get("requestBody")
        if not request_body:
            return {"properties": {}, "required": []}
        
        content = request_body.get("content", {})
        if "application/json" not in content:
            return {"properties": {}, "required": []}
        
        schema = content["application/json"].get("schema")
        if not schema:
            return {"properties": {}, "required": []}
        
        # Handle $ref references
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/"):
                ref_parts = ref_path[2:].split("/")
                ref_schema = openapi_spec
                for part in ref_parts:
                    ref_schema = ref_schema.get(part, {})
                schema = ref_schema
        
        return self._convert_schema_to_parameters(schema, openapi_spec)
    
    def _convert_schema_to_parameters(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a schema to parameter format."""
        properties = {}
        required = []
        
        if schema.get("type") == "object":
            schema_properties = schema.get("properties", {})
            schema_required = schema.get("required", [])
            
            for prop_name, prop_schema in schema_properties.items():
                # Handle $ref in properties
                if "$ref" in prop_schema:
                    ref_path = prop_schema["$ref"]
                    if ref_path.startswith("#/"):
                        ref_parts = ref_path[2:].split("/")
                        ref_schema = openapi_spec
                        for part in ref_parts:
                            ref_schema = ref_schema.get(part, {})
                        prop_schema = ref_schema
                
                # Convert property schema
                property_schema = {
                    "type": prop_schema.get("type", "string"),
                    "description": prop_schema.get("description", "")
                }
                
                # Add additional schema properties
                for key in ["format", "enum", "minimum", "maximum", "pattern"]:
                    if key in prop_schema:
                        property_schema[key] = prop_schema[key]
                
                # Handle array items
                if prop_schema.get("type") == "array":
                    items = prop_schema.get("items", {})
                    if "$ref" in items:
                        ref_name = items["$ref"].split("/")[-1]
                        property_schema["items"] = {"type": "object", "description": f"Reference to {ref_name}"}
                    else:
                        property_schema["items"] = {"type": items.get("type", "string")}
                
                properties[prop_name] = property_schema
                
                if prop_name in schema_required:
                    required.append(prop_name)
        
        return {
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
    
    def generate_schema_prompts(self, openapi_spec: Dict[str, Any]) -> List[str]:
        """Generate system prompts from OpenAPI response schemas."""
        prompts = []
        
        # Extract all unique schemas from responses
        schemas = self._extract_response_schemas(openapi_spec)
        
        # Generate prompts for each schema
        for schema_name, schema_info in schemas.items():
            prompt = self._generate_schema_prompt(schema_name, schema_info, openapi_spec)
            if prompt:
                prompts.append(prompt)
        
        # Generate endpoint-specific prompts
        endpoint_prompts = self._generate_endpoint_prompts(openapi_spec)
        prompts.extend(endpoint_prompts)
        
        return prompts
    
    def generate_tool_system_prompts(self, openapi_spec: Dict[str, Any]) -> Dict[str, str]:
        """Generate per-tool system prompts for dynamic injection."""
        tool_prompts = {}
        
        for path, methods in openapi_spec.get("paths", {}).items():
            for method, operation in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue
                
                operation_id = operation.get("operationId")
                if not operation_id:
                    continue
                
                # Get comprehensive response schema information for this specific tool
                response_schema = self._get_endpoint_response_schema(operation, openapi_spec)
                
                if response_schema:
                    # Generate detailed schema description including all referenced types
                    schema_description = self._generate_comprehensive_schema_description(response_schema, openapi_spec)
                    
                    if schema_description:
                        prompt = f"""Tool Output Schema for {operation_id}:

{schema_description}

This describes the complete structure of data returned by the {operation_id} tool, including all nested object types and their properties."""
                        tool_prompts[operation_id] = prompt
        
        return tool_prompts
    
    def _extract_response_schemas(self, openapi_spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract all unique response schemas from the OpenAPI spec."""
        schemas = {}
        
        for path, methods in openapi_spec.get("paths", {}).items():
            for method, operation in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue
                
                responses = operation.get("responses", {})
                for status_code, response in responses.items():
                    content = response.get("content", {})
                    if "application/json" in content:
                        schema = content["application/json"].get("schema")
                        if schema:
                            schema_name = self._get_schema_name(schema, openapi_spec)
                            if schema_name and schema_name not in schemas:
                                schemas[schema_name] = {
                                    "schema": schema,
                                    "endpoints": []
                                }
                            
                            if schema_name in schemas:
                                schemas[schema_name]["endpoints"].append({
                                    "path": path,
                                    "method": method,
                                    "operation_id": operation.get("operationId"),
                                    "status_code": status_code
                                })
        
        return schemas
    
    def _get_schema_name(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Get the name of a schema, handling $ref references."""
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/"):
                return ref_path.split("/")[-1]
        
        # For inline schemas, try to infer a name from the context
        if schema.get("type") == "object":
            properties = schema.get("properties", {})
            if "data" in properties:
                # This looks like a wrapper object with a data field
                items = properties["data"].get("items", {})
                if "$ref" in items:
                    return f"{items['$ref'].split('/')[-1]}Response"
                elif items.get("type") == "array":
                    return "ArrayResponse"
        
        return None
    
    def _generate_schema_prompt(self, schema_name: str, schema_info: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Generate a system prompt for a specific schema."""
        schema = schema_info["schema"]
        endpoints = schema_info["endpoints"]
        
        # Resolve schema if it's a $ref
        resolved_schema = self._resolve_schema_reference(schema, openapi_spec)
        
        # Generate schema description
        schema_description = self._describe_schema_structure(resolved_schema, openapi_spec)
        
        # Generate endpoint list
        endpoint_list = []
        for endpoint in endpoints:
            endpoint_list.append(f"- {endpoint['method'].upper()} {endpoint['path']} → {schema_name}")
        
        prompt = f"""API Response Schema: {schema_name}

{schema_description}

Used by endpoints:
{chr(10).join(endpoint_list)}"""
        
        return prompt
    
    def _generate_endpoint_prompts(self, openapi_spec: Dict[str, Any]) -> List[str]:
        """Generate endpoint-specific prompts with response information."""
        prompts = []
        
        for path, methods in openapi_spec.get("paths", {}).items():
            for method, operation in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue
                
                operation_id = operation.get("operationId")
                if not operation_id:
                    continue
                
                # Get response schema information
                response_info = self._get_endpoint_response_info(operation, openapi_spec)
                
                if response_info:
                    prompt = f"""API Endpoint: {operation_id}
Method: {method.upper()} {path}
Response: {response_info}"""
                    prompts.append(prompt)
        
        return prompts
    
    def _get_endpoint_response_info(self, operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Get response information for a specific endpoint."""
        responses = operation.get("responses", {})
        
        # Look for success responses first
        success_codes = ["200", "201", "202"]
        for code in success_codes:
            if code in responses:
                response = responses[code]
                content = response.get("content", {})
                if "application/json" in content:
                    schema = content["application/json"].get("schema")
                    if schema:
                        return self._describe_response_schema(schema, openapi_spec)
        
        # Fallback to any response
        for code, response in responses.items():
            content = response.get("content", {})
            if "application/json" in content:
                schema = content["application/json"].get("schema")
                if schema:
                    return self._describe_response_schema(schema, openapi_spec)
        
        return "No structured response"
    
    def _describe_response_schema(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Describe a response schema in a concise format."""
        resolved_schema = self._resolve_schema_reference(schema, openapi_spec)
        
        if not resolved_schema:
            return "Unknown response format"
        
        schema_type = resolved_schema.get("type", "object")
        
        if schema_type == "array":
            items = resolved_schema.get("items", {})
            if "$ref" in items:
                ref_name = items["$ref"].split("/")[-1]
                return f"Array of {ref_name}"
            else:
                item_type = items.get("type", "object")
                return f"Array of {item_type}s"
        
        elif schema_type == "object":
            properties = resolved_schema.get("properties", {})
            if not properties:
                return "Object"
            
            # Check if it's a wrapper with data field
            if "data" in properties and properties["data"].get("type") == "array":
                items = properties["data"].get("items", {})
                if "$ref" in items:
                    ref_name = items["$ref"].split("/")[-1]
                    return f"{{ data: {ref_name}[] }}"
                else:
                    return "{{ data: array }}"
            
            # Describe object structure
            prop_descriptions = []
            for prop_name, prop_schema in list(properties.items())[:5]:
                prop_type = prop_schema.get("type", "object")
                if "$ref" in prop_schema:
                    ref_name = prop_schema["$ref"].split("/")[-1]
                    prop_descriptions.append(f"{prop_name}: {ref_name}")
                else:
                    prop_descriptions.append(f"{prop_name}: {prop_type}")
            
            description = f"{{ {', '.join(prop_descriptions)}"
            if len(properties) > 5:
                description += f", ...{len(properties) - 5} more fields"
            description += " }"
            
            return description
        
        return schema_type
    
    def _describe_schema_structure(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Generate a detailed description of a schema structure."""
        if not schema:
            return "Unknown schema"
        
        schema_type = schema.get("type", "object")
        
        if schema_type == "object":
            properties = schema.get("properties", {})
            if not properties:
                return "Empty object"
            
            # Generate field descriptions
            field_descriptions = []
            for prop_name, prop_schema in properties.items():
                prop_type = prop_schema.get("type", "object")
                prop_desc = prop_schema.get("description", "")
                
                if "$ref" in prop_schema:
                    ref_name = prop_schema["$ref"].split("/")[-1]
                    field_desc = f"- {prop_name}: {ref_name}"
                elif prop_type == "array":
                    items = prop_schema.get("items", {})
                    if "$ref" in items:
                        ref_name = items["$ref"].split("/")[-1]
                        field_desc = f"- {prop_name}: {ref_name}[]"
                    else:
                        item_type = items.get("type", "object")
                        field_desc = f"- {prop_name}: {item_type}[]"
                else:
                    field_desc = f"- {prop_name}: {prop_type}"
                
                if prop_desc:
                    field_desc += f" ({prop_desc})"
                
                field_descriptions.append(field_desc)
            
            return f"Schema structure:\n{chr(10).join(field_descriptions)}"
        
        elif schema_type == "array":
            items = schema.get("items", {})
            if "$ref" in items:
                ref_name = items["$ref"].split("/")[-1]
                return f"Array of {ref_name} objects"
            else:
                item_type = items.get("type", "object")
                return f"Array of {item_type} objects"
        
        return f"Simple {schema_type} value"
    
    def _resolve_schema_reference(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve $ref references in schemas."""
        if "$ref" not in schema:
            return schema
        
        ref_path = schema["$ref"]
        if not ref_path.startswith("#/"):
            return schema
        
        # Navigate to the referenced schema
        ref_parts = ref_path[2:].split("/")
        ref_schema = openapi_spec
        for part in ref_parts:
            ref_schema = ref_schema.get(part, {})
        
        return ref_schema
    
    def _get_endpoint_response_schema(self, operation: Dict[str, Any], openapi_spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get the response schema for a specific endpoint."""
        responses = operation.get("responses", {})
        
        # Look for success responses first
        success_codes = ["200", "201", "202"]
        for code in success_codes:
            if code in responses:
                response = responses[code]
                content = response.get("content", {})
                if "application/json" in content:
                    schema = content["application/json"].get("schema")
                    if schema:
                        return schema
        
        # Fallback to any response
        for code, response in responses.items():
            content = response.get("content", {})
            if "application/json" in content:
                schema = content["application/json"].get("schema")
                if schema:
                    return schema
        
        return None
    
    def _generate_comprehensive_schema_description(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any]) -> str:
        """Generate a comprehensive description of a schema including all referenced types."""
        if not schema:
            return ""
        
        # Resolve the main schema
        resolved_schema = self._resolve_schema_reference(schema, openapi_spec)
        if not resolved_schema:
            return ""
        
        # Collect all referenced schemas that need to be described
        referenced_schemas = set()
        self._collect_referenced_schemas(resolved_schema, openapi_spec, referenced_schemas)
        
        # Generate description for the main schema
        main_description = self._describe_schema_structure(resolved_schema, openapi_spec)
        
        # Generate descriptions for all referenced schemas
        referenced_descriptions = []
        for schema_name in sorted(referenced_schemas):
            if schema_name in openapi_spec.get("components", {}).get("schemas", {}):
                ref_schema = openapi_spec["components"]["schemas"][schema_name]
                ref_description = self._describe_schema_structure(ref_schema, openapi_spec)
                if ref_description:
                    referenced_descriptions.append(f"\n{schema_name} Schema:\n{ref_description}")
        
        # Combine main description with referenced schemas
        full_description = main_description
        if referenced_descriptions:
            full_description += "\n\nReferenced Types:" + "".join(referenced_descriptions)
        
        return full_description
    
    def _collect_referenced_schemas(self, schema: Dict[str, Any], openapi_spec: Dict[str, Any], referenced: set) -> None:
        """Recursively collect all schema references from a schema."""
        if not schema:
            return
        
        # Handle $ref
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/"):
                schema_name = ref_path.split("/")[-1]
                referenced.add(schema_name)
                # Get the referenced schema and collect its references too
                if "components" in openapi_spec and "schemas" in openapi_spec["components"]:
                    if schema_name in openapi_spec["components"]["schemas"]:
                        ref_schema = openapi_spec["components"]["schemas"][schema_name]
                        self._collect_referenced_schemas(ref_schema, openapi_spec, referenced)
            return
        
        # Handle object properties
        if schema.get("type") == "object":
            properties = schema.get("properties", {})
            for prop_schema in properties.values():
                self._collect_referenced_schemas(prop_schema, openapi_spec, referenced)
        
        # Handle array items
        if schema.get("type") == "array":
            items = schema.get("items", {})
            self._collect_referenced_schemas(items, openapi_spec, referenced)
        
        # Handle oneOf, anyOf, allOf
        for union_type in ["oneOf", "anyOf", "allOf"]:
            if union_type in schema:
                for sub_schema in schema[union_type]:
                    self._collect_referenced_schemas(sub_schema, openapi_spec, referenced)

