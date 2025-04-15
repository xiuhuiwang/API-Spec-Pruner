import yaml

def collect_referenced_components(api_spec, extracted_paths):
    components = api_spec.get('components', {})
    referenced_components = {'schemas': {}, 'parameters': {}, 'responses': {}, 'requestBodies': {}}
    processed_refs = set()  # Track processed references to avoid infinite recursion

    def process_ref(ref):
        if ref in processed_refs:
            return
        
        processed_refs.add(ref)
        parts = ref.split('/')
        if len(parts) >= 4 and parts[1] == 'components':
            component_type = parts[2]
            component_name = parts[3]
            
            if component_type in components and component_name in components[component_type]:
                # Add the component if not already added
                if component_type not in referenced_components:
                    referenced_components[component_type] = {}
                referenced_components[component_type][component_name] = components[component_type][component_name]
                
                # Recursively process any nested references in this component
                find_refs_in_object(components[component_type][component_name])

    def find_refs_in_object(obj):
        if not isinstance(obj, (dict, list)):
            return
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == '$ref' and isinstance(value, str):
                    process_ref(value)
                else:
                    find_refs_in_object(value)
        elif isinstance(obj, list):
            for item in obj:
                find_refs_in_object(item)

    # First, collect direct references from extracted paths
    for path, methods in extracted_paths.items():
        find_refs_in_object(methods)

    # Clean up empty components and sort
    for component_type in list(referenced_components.keys()):
        if not referenced_components[component_type]:
            referenced_components.pop(component_type)
        else:
            referenced_components[component_type] = dict(sorted(referenced_components[component_type].items()))

    return referenced_components

def remove_field(obj, field_name):
    """Remove field from API objects recursively."""
    if isinstance(obj, dict):
        # Remove x-ms-examples if present
        if field_name in obj:
            del obj[field_name]
        
        # Process all nested dictionaries
        for key, value in list(obj.items()):
            if isinstance(value, (dict, list)):
                remove_field(value, field_name)
    elif isinstance(obj, list):
        # Process all items in the list
        for item in obj:
            if isinstance(item, (dict, list)):
                remove_field(item, field_name)
    
    return obj

def shorten_api_spec(spec_filename, required_paths_methods, output_filename='shortened_api_spec.json'):
    # Read the full API specification from a YAML file
    with open(spec_filename, 'r') as file:
        api_spec = yaml.safe_load(file)

    # Extract the specified paths with only the required methods
    extracted_paths = {}
    for path, methods in required_paths_methods.items():
        if path in api_spec['paths']:
            path_data = {}
            for method in methods:
                method = method.lower()  # Convert to lowercase (e.g., GET -> get)
                if method in api_spec['paths'][path]:
                    path_data[method] = api_spec['paths'][path][method]
            if path_data:  # Only add the path if we found at least one method
                extracted_paths[path] = path_data
    
    # # Remove x-ms-examples from each path item
    remove_field(extracted_paths, 'x-ms-examples')

    # Collect referenced components, including nested ones
    referenced_components = collect_referenced_components(api_spec, extracted_paths)

    new_api_spec = dict()
    if 'openapi' in api_spec:
        new_api_spec['openapi'] = api_spec['openapi']
    elif 'swagger' in api_spec:
        print("Please use OpenAPI 3.0 specification format")
        return
    
    if 'info' in api_spec:
        new_api_spec['info'] = api_spec['info']
    if 'servers' in api_spec:
        new_api_spec['servers'] = api_spec['servers']
    if 'tags' in api_spec:
        new_api_spec['tags'] = api_spec['tags']
    if 'paths' in api_spec:
        new_api_spec['paths'] = extracted_paths

    # Only add components if there are any
    if referenced_components:
        new_api_spec['components'] = referenced_components

    # Output the shortened API specification as a YAML file
    with open(output_filename, 'w') as file:
        yaml.dump(new_api_spec, file, default_flow_style=False, sort_keys=False)


# -----------Extract Azure OpenAI API specification Stable------------
filename = 'authoring_stable_3_0'
spec_filename = filename + '.yaml'
output_filename = filename + '_shortened.yaml'
required_paths = {
    "/models": ["get"],
    "/files": ["get", "post"],
    "/files/{file_id}": ["delete"]
}
shorten_api_spec(spec_filename, required_paths, output_filename)

# -----------Extract Azure OpenAI API specification Preview------------
# spec_filename = 'azure_openai/inference_preview_2502.yaml'
# required_paths = {
#     "/deployments/{deployment-id}/chat/completions": ["post"],
#     "/deployments/{deployment-id}/embeddings": ["post"],
#     "/vector_stores": ["get", "post"],
#     "/vector_stores/{vector_store_id}/files": ["get", "post"],
#     "/vector_stores/{vector_store_id}/files/{file_id}": ["delete"],
#     "/assistants": ["get"],
#     "/threads": ["post"],
#     "/threads/{thread_id}/messages": ["get", "post"],
#     "/threads/runs": ["post"],
#     "/threads/{thread_id}/runs": ["get", "post"],
#     "/threads/{thread_id}/runs/{run_id}": ["get"],
#     "/threads/{thread_id}/runs/{run_id}/submit_tool_outputs": ["post"]
# }
# shorten_api_spec(spec_filename, required_paths)