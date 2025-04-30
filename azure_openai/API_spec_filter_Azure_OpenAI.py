import yaml
import openapi_circular_resolver
import os

# Core component handling functions
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

# Path extraction functions
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

# Cleanup functions
def remove_required_fields_by_path(api_spec, field_paths):
    """
    Remove specific fields from the OpenAPI spec, given a list of hierarchical paths.
    
    Args:
        api_spec (dict): The OpenAPI specification as a dictionary.
        field_paths (list of str): List of paths in the format
            'components-schemas-<SchemaName>-required'
            or 'components-schemas-<SchemaName>-required-<field_name>'
            describing the full path to the field to remove.
    """
    for path in field_paths:
        parts = path.split('-')
        try:
            # Navigate to the parent object
            obj = api_spec
            current_path = []
            
            for part in parts[:-1]:
                current_path.append(part)
                if isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                else:
                    obj = None
                    break
            
            if obj is None:
                continue
                
            last_part = parts[-1]
            
            # Check if we're removing a specific field from the required array
            if len(parts) >= 2 and parts[-2] == "required":
                # We're removing a specific field from a required array
                required_key = parts[-2]
                field_to_remove = parts[-1]
                
                if isinstance(obj, list):
                    # If obj is already the required array
                    if field_to_remove in obj:
                        obj.remove(field_to_remove)
                elif isinstance(obj, dict) and required_key in obj and isinstance(obj[required_key], list):
                    # If obj is the parent dictionary containing the required array
                    if field_to_remove in obj[required_key]:
                        obj[required_key].remove(field_to_remove)
            
            # Check if we're removing the entire required field
            elif last_part == "required":
                # We're removing the entire required field
                if isinstance(obj, dict):
                    obj.pop("required", None)
                    
        except Exception as e:
            # Skip malformed paths or if structure doesn't match
            continue

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

# Spec creation function
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
    
    # Create the new API spec with standard info
    new_api_spec = {
        'openapi': api_spec['openapi'],
        'info': {
            'title': "Integrated Azure OpenAI API",
            'description': "This specification is derived from several Azure OpenAI API specifications and consolidated into a single document. The APIs defined herein are actively utilized within the Azure Snap Pack.",
            'version': "1.0.0"
        },
        'servers': [
            {
                'url': 'https://{endpoint}/openai'
            }
        ],
        'paths': extracted_paths
    }
    
    # Only add 'components' if there are any
    if referenced_components:
        new_api_spec['components'] = referenced_components
    
    # Remove all x-ms-examples fields
    new_api_spec = remove_x_ms_examples(new_api_spec)
        
    return new_api_spec

# Multi-spec processing function
def process_combined_specs(input_filenames, required_paths, invalid_required_fields, output_filename):
    """
    Process multiple API specs and combine them into a single output spec.
    
    Args:
        input_filenames (list): List of input spec filenames
        required_paths (dict): Mapping of paths to required HTTP methods
        invalid_required_fields (list): List of field paths to remove from the combined spec
    
    Returns:
        str: Path to the final output file
    """
    # Load all input specs
    specs = []
    for filename in input_filenames:
        with open(filename, "r") as f:
            spec = yaml.safe_load(f)
            specs.append({"filename": filename, "spec": spec})

    # Prepare combined output
    combined_paths = {}
    combined_components = {}

    # Use the first spec as the "base" for openapi version
    base_spec = specs[0]["spec"] if specs else None

    # For each required path, find which spec contains it, and which methods are available
    for path, methods in required_paths.items():
        found = False
        for s in specs:
            spec_paths = s["spec"].get("paths", {})
            if path in spec_paths:
                # Only include methods that actually exist in this spec for this path
                available_methods = [m for m in methods if m.lower() in spec_paths[path]]
                if available_methods:
                    # Extract the path/methods
                    extracted = extract_paths(s["spec"], {path: available_methods})
                    combined_paths.update(extracted)
                    # Collect referenced components for this path
                    referenced = collect_referenced_components(s["spec"], extracted)
                    # Merge referenced components into combined_components
                    for ctype, cdict in referenced.items():
                        if ctype not in combined_components:
                            combined_components[ctype] = {}
                        combined_components[ctype].update(cdict)
                    found = True
                    break  # Stop at the first spec that contains this path
        if not found:
            print(f"Warning: Path '{path}' not found in any input spec.")

    # Compose the combined spec
    if base_spec is not None:
        # Use the create_new_spec function with standardized values
        combined_api_spec = create_new_spec(
            base_spec,
            combined_paths, 
            combined_components
        )
        
        # Remove invalid required fields
        remove_required_fields_by_path(combined_api_spec, invalid_required_fields)

        # Write to temporary output file
        temp_filename = "temp_combined_apis.yaml"
        with open(temp_filename, "w") as f:
            yaml.dump(combined_api_spec, f, default_flow_style=False, sort_keys=False)
        
        # Resolve circular references
        circular_report_filename = "azure_openai-circular_report.json"
        openapi_circular_resolver.resolve_openapi_circular_refs(
            temp_filename, output_filename, circular_report_filename
        )
        
        # Clean up temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
        print(f"Combined simplified spec written to: {output_filename}")
        return output_filename
    else:
        print("No input specs provided.")
        return None

def main():
    """
    Entry point for the script.
    Processes multiple API specs to create a combined, simplified version.
    """
    # Input specifications
    input_spec_filenames = [
        "authoring_stable_3_0.yaml",
        "inference_preview_2024_08_01.yaml",
        "inference_stable_2024_02_01.yaml"
    ]

    # Define the paths and methods to include in the combined specification
    required_paths = {
        "/deployments": ["get"],
        "/models": ["get"],
        "/files": ["get", "post"],
        "/files/{file-id}": ["delete"],
        "/assistants": ["get"],
        "/threads": ["post"],
        "/threads/{thread_id}/messages": ["get", "post"],
        "/threads/runs": ["post"],
        "/threads/{thread_id}/runs": ["get", "post"],
        "/threads/{thread_id}/runs/{run_id}": ["get"],
        "/threads/{thread_id}/runs/{run_id}/submit_tool_outputs": ["post"],
        "/vector_stores": ["get", "post"],
        "/vector_stores/{vector_store_id}/files": ["get", "post"],
        "/vector_stores/{vector_store_id}/files/{file_id}": ["delete"],
        "/deployments/{deployment-id}/chat/completions": ["post"],
        "/deployments/{deployment-id}/embeddings": ["post"]
    }

    # Fields to remove from the combined spec
    invalid_required_fields = [
        "components-schemas-createThreadAndRunRequest-required-thread_id",
        "components-schemas-createRunRequest-required-thread_id",
        "components-schemas-vectorStoreObject-required-bytes",
        "components-schemas-contentFilterDetectedWithCitationResult-required",
        "components-schemas-contentFilterIdResult-required",
        "components-schemas-contentFilterSeverityResult-required-filtered",
        "components-schemas-retrievedDocument-required",
        "components-schemas-contentFilterDetailedResults-required",
        "components-schemas-contentFilterDetectedResult-required",
        "components-schemas-contentFilterSeverityResult-required"
    ]

    # Name of the output file
    output_filename = "combined_azure_apis_simplified.yaml"

    # Process and combine all specs
    process_combined_specs(input_spec_filenames, required_paths, invalid_required_fields, output_filename)

if __name__ == "__main__":
    main()