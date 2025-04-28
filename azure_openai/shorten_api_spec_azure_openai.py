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
            
def update_dates_format(obj):
    """
    Recursively traverse through the API spec and update dates in format yyyy-mm-dd to "yyyy-mm-dd".
    
    Args:
        obj: The object to traverse (dict, list, or scalar value)
        
    Returns:
        The updated object with quoted dates
    """
    import re
    
    date_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})$')
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            obj[key] = update_dates_format(value)
        return obj
    elif isinstance(obj, list):
        return [update_dates_format(item) for item in obj]
    elif isinstance(obj, str):
        # Check if the string matches the yyyy-mm-dd pattern
        if date_pattern.match(obj):
            return f'"{obj}"'
        return obj
    else:
        return obj
    
def remove_x_ms_examples(obj):
    """
    Recursively traverse through the API spec and remove all x-ms-examples fields.
    
    Args:
        obj: The object to traverse (dict, list, or scalar value)
        
    Returns:
        The updated object with x-ms-examples removed
    """
    if isinstance(obj, dict):
        # Remove x-ms-examples if it exists in this dictionary
        if 'x-ms-examples' in obj:
            del obj['x-ms-examples']
        
        # Process all remaining key-value pairs
        for key, value in list(obj.items()):
            obj[key] = remove_x_ms_examples(value)
        return obj
    elif isinstance(obj, list):
        return [remove_x_ms_examples(item) for item in obj]
    else:
        return obj

def create_new_spec(api_spec, extracted_paths, referenced_components):
    """
    Create a new API specification with only the extracted paths, and components.
    
    Args:
        api_spec (dict): The complete API specification
        extracted_paths (dict): The subset of paths to include
        referenced_components (dict): The referenced components to include
        
    Returns:
        dict: The new API specification
    """
    
    new_api_spec = {
        'openapi': api_spec['openapi'],
        'info': api_spec['info'],
        'servers': api_spec['servers'],
        'paths': extracted_paths
    }
    
    # Only add 'components' if there are any
    if referenced_components:
        new_api_spec['components'] = referenced_components
    
    # Remove all x-ms-examples fields
    new_api_spec = remove_x_ms_examples(new_api_spec)

    # Update dates format in the new API spec from yyyy-mm-dd to "yyyy-mm-dd"
    new_api_spec = update_dates_format(new_api_spec)
        
    return new_api_spec


def shorten_api_spec(spec_filename, required_paths_methods, output_filename, properties_to_remove=None):
    """
    Create a shortened version of an API specification with only the specified paths, and methods.
    
    Args:
        spec_filename (str): Path to the input API specification file
        required_paths_methods (dict): Mapping of paths to required HTTP methods
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

    # Create a new API specification with only the extracted paths, and components
    new_api_spec = create_new_spec(api_spec, extracted_paths, referenced_components)

    # Output the shortened API specification as a YAML file
    with open(output_filename, 'w') as file:
        yaml.dump(new_api_spec, file, default_flow_style=False, sort_keys=False)


def main():
    """Entry point for the script."""
    # input_spec_filename = 'authoring_stable_3_0.yaml'
    # output_spec_filename = 'authoring_stable_3_0_simplified.yaml'

    # input_spec_filename = 'inference_2024_08_01.yaml'
    # output_spec_filename = 'inference_2024_08_01_simplified.yaml'

    input_spec_filename = 'inference_stable_2024_02_01.yaml'
    output_spec_filename = 'inference_stable_2024_02_01_simplified.yaml'
    
    # Define the paths and methods to include in the shortened specification
    required_paths = {
        # "/deployments": ["get"],
        # "/models": ["get"],
        # "/files": ["get", "post"],
        # "/files/{file-id}": ["delete"],
        #------------------------------
        # "/assistants": ["get"],
        # "/threads": ["post"],
        # "/threads/{thread_id}/messages": ["get", "post"],
        # "/threads/runs": ["post"],
        # "/threads/{thread_id}/runs": ["get", "post"],
        # "/threads/{thread_id}/runs/{run_id}": ["get"],
        # "/threads/{thread_id}/runs/{run_id}/submit_tool_outputs": ["post"],
        # "/vector_stores": ["get", "post"],
        # "/vector_stores/{vector_store_id}/files": ["get", "post"],
        # "/vector_stores/{vector_store_id}/files/{file_id}": ["delete"]
        #------------------------------
        "/deployments/{deployment-id}/chat/completions": ["post"],
        "/deployments/{deployment-id}/embeddings": ["post"]
    }
    
    
    # # Define properties to remove from specific components
    # properties_to_remove = {
    #     # the seed contains a large integer that leads to error in MongoDB
    #     "CreateChatCompletionRequest": ["seed"],
    #     # these two properties are not legal in openapi 3.0
    #     "VectorStoreFileAttributes": ["additionalProperties", "propertyNames"]
    # }
    
    shorten_api_spec(input_spec_filename, required_paths, output_spec_filename)


if __name__ == "__main__":
    main()