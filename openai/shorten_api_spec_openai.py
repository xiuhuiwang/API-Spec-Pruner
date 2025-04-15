import yaml


def collect_referenced_components(api_spec, extracted_paths):
    """
    Collect all components that are referenced in the extracted paths.
    
    Args:
        api_spec (dict): The complete API specification
        extracted_paths (dict): The subset of paths to include
        
    Returns:
        dict: Referenced components organized by type
    """
    components = api_spec.get('components', {})
    referenced_components = {'schemas': {}, 'parameters': {}, 'responses': {}, 'requestBodies': {}}
    processed_refs = set()  # Track processed references to avoid infinite recursion
    
    def process_ref(ref):
        """Process a single reference and add it to referenced_components."""
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
        """Recursively find all $ref occurrences in an object."""
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

    # Collect direct references from extracted paths
    for path, methods in extracted_paths.items():
        find_refs_in_object(methods)

    # Clean up empty components and sort
    for component_type in list(referenced_components.keys()):
        if not referenced_components[component_type]:
            referenced_components.pop(component_type)
        else:
            referenced_components[component_type] = dict(sorted(referenced_components[component_type].items()))

    return referenced_components


def extract_paths(api_spec, required_paths_methods):
    """
    Extract only the specified paths and methods from the API spec.
    
    Args:
        api_spec (dict): The complete API specification
        required_paths_methods (dict): Mapping of paths to required HTTP methods
        
    Returns:
        dict: The extracted paths with only the required methods
    """
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
                
    return extracted_paths


def filter_tags(api_spec, required_tags):
    """
    Filter the tags to only include those specified in required_tags.
    
    Args:
        api_spec (dict): The complete API specification
        required_tags (list): List of tag names to keep
        
    Returns:
        list: Filtered list of tag objects
    """
    filtered_tags = []
    
    for tag in api_spec.get('tags', []):
        if tag.get('name') in required_tags:
            filtered_tags.append(tag)
            
    return filtered_tags


def remove_component_properties(referenced_components, properties_to_remove):
    """
    Remove specified properties from components.
    
    Args:
        referenced_components (dict): The referenced components
        properties_to_remove (dict): Mapping of component names to lists of properties to remove
    """
    for component_name, properties in properties_to_remove.items():
        # Look for the component in different component types (schemas, parameters, etc.)
        for component_type, components in referenced_components.items():
            if component_name in components:
                component = components[component_name]
                # check if the property is in the component itself
                for prop in properties:
                    if prop in component:
                        del component[prop]
                # Check if the component has properties
                if 'properties' in component:
                    for prop in properties:
                        if prop in component['properties']:
                            del component['properties'][prop]
                # For components with allOf, check each item
                elif 'allOf' in component:
                    for item in component['allOf']:
                        if isinstance(item, dict) and 'properties' in item:
                            for prop in properties:
                                if prop in item['properties']:
                                    del item['properties'][prop]

def create_new_spec(api_spec, extracted_paths, referenced_components, required_tags):
    """
    Create a new API specification with only the extracted paths, components, and filtered tags.
    
    Args:
        api_spec (dict): The complete API specification
        extracted_paths (dict): The subset of paths to include
        referenced_components (dict): The referenced components to include
        required_tags (list): List of tag names to keep
        
    Returns:
        dict: The new API specification
    """
    # Filter tags to only include required ones
    filtered_tags = filter_tags(api_spec, required_tags)
    
    new_api_spec = {
        'openapi': api_spec['openapi'],
        'info': api_spec['info'],
        'servers': api_spec['servers'],
        'tags': filtered_tags,
        'paths': extracted_paths
    }
    
    # Only add 'components' if there are any
    if referenced_components:
        new_api_spec['components'] = referenced_components
        
    return new_api_spec


def shorten_api_spec(spec_filename, required_paths_methods, required_tags, output_filename, properties_to_remove=None):
    """
    Create a shortened version of an API specification with only the specified paths, methods, and tags.
    
    Args:
        spec_filename (str): Path to the input API specification file
        required_paths_methods (dict): Mapping of paths to required HTTP methods
        required_tags (list): List of tag names to keep
        output_filename (str): Path to save the shortened API specification
        properties_to_remove (dict, optional): Mapping of component names to lists of properties to remove
    """
    # Read the full API specification from a YAML file
    with open(spec_filename, 'r') as file:
        api_spec = yaml.safe_load(file)

    # Extract the specified paths with only the required methods
    extracted_paths = extract_paths(api_spec, required_paths_methods)

    # Collect referenced components, including nested ones
    referenced_components = collect_referenced_components(api_spec, extracted_paths)
    
    # Remove specified properties from components if provided
    if properties_to_remove:
        remove_component_properties(referenced_components, properties_to_remove)

    # Create a new API specification with only the extracted paths, components, and filtered tags
    new_api_spec = create_new_spec(api_spec, extracted_paths, referenced_components, required_tags)

    # Output the shortened API specification as a YAML file
    with open(output_filename, 'w') as file:
        yaml.dump(new_api_spec, file, default_flow_style=False, sort_keys=False)


def main():
    """Entry point for the script."""
    input_spec_filename = 'openai_api.yaml'
    output_spec_filename = 'openai_shortened_api.yaml'
    
    # Define the paths and methods to include in the shortened specification
    required_paths = {
        "/models": ["get"],
        "/chat/completions": ["post"],
        "/embeddings": ["post"],
        "/files": ["get", "post"],
        "/files/{file_id}": ["delete"],
        "/vector_stores": ["get", "post"],
        "/vector_stores/{vector_store_id}/files": ["get", "post"],
        "/vector_stores/{vector_store_id}/files/{file_id}": ["delete"],
        "/assistants": ["get"],
        "/threads": ["post"],
        "/threads/{thread_id}/messages": ["get", "post"],
        "/threads/runs": ["post"],
        "/threads/{thread_id}/runs": ["get", "post"],
        "/threads/{thread_id}/runs/{run_id}": ["get"],
        "/threads/{thread_id}/runs/{run_id}/submit_tool_outputs": ["post"]
    }
    
    # Define the tags to keep in the shortened specification
    required_tags = ["Assistants", "Chat", "Completions", "Embeddings", "Files", "Models"]
    
    # Define properties to remove from specific components
    properties_to_remove = {
        # the seed contains a large integer that leads to error in MongoDB
        "CreateChatCompletionRequest": ["seed"],
        # these two properties are not legal in openapi 3.0
        "VectorStoreFileAttributes": ["additionalProperties", "propertyNames"]
    }
    
    shorten_api_spec(input_spec_filename, required_paths, required_tags, output_spec_filename, properties_to_remove)


if __name__ == "__main__":
    main()