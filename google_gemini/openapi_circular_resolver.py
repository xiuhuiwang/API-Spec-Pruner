import json
import yaml
import copy
import argparse
from collections import defaultdict

def load_openapi_spec(file_path):
    """Load an OpenAPI specification from a file."""
    with open(file_path, 'r') as file:
        if file_path.endswith('.json'):
            return json.load(file)
        elif file_path.endswith(('.yaml', '.yml')):
            return yaml.safe_load(file)
        else:
            raise ValueError("Unsupported file format. Use .json, .yaml, or .yml")

def save_openapi_spec(spec, output_file):
    """Save an OpenAPI specification to a file."""
    with open(output_file, 'w') as file:
        if output_file.endswith('.json'):
            json.dump(spec, file, indent=2)
        elif output_file.endswith(('.yaml', '.yml')):
            yaml.dump(spec, file, sort_keys=False)
        else:
            raise ValueError("Unsupported file format. Use .json, .yaml, or .yml")

def build_reference_graph(spec, context="#/components/schemas/"):
    """Build a graph of references between schemas."""
    graph = defaultdict(set)
    locations = defaultdict(set)
    schemas = spec.get("components", {}).get("schemas", {})
    
    def extract_refs(obj, current_schema=None, path=""):
        if isinstance(obj, dict):
            if "$ref" in obj and obj["$ref"].startswith(context):
                ref_name = obj["$ref"][len(context):]
                if current_schema:
                    graph[current_schema].add(ref_name)
                    # Store the path to this reference for later use
                    location_key = f"{current_schema} -> {ref_name}"
                    locations[location_key].add(path)
            
            # Use list() to create a copy of items to avoid modification during iteration
            for key, value in list(obj.items()):
                new_path = f"{path}/{key}" if path else key
                extract_refs(value, current_schema, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}/{i}" if path else str(i)
                extract_refs(item, current_schema, new_path)
    
    # Build the graph and collect reference locations
    for schema_name, schema_def in schemas.items():
        extract_refs(schema_def, schema_name)
    
    return graph, locations

def detect_cycles(graph):
    """Detect cycles in the reference graph using DFS."""
    cycles = []
    # Make a copy of the graph keys to avoid the "dictionary changed size during iteration" error
    nodes = list(graph.keys())
    
    def dfs(node, visited=None, path=None):
        if visited is None:
            visited = set()
        if path is None:
            path = []
            
        if node in path:
            cycle_start = path.index(node)
            current_cycle = path[cycle_start:] + [node]
            cycles.append(current_cycle)
            return
        
        if node in visited:
            return
        
        visited.add(node)
        path.append(node)
        
        # Use a copy of neighbors to avoid modification issues
        neighbors = list(graph.get(node, []))
        for neighbor in neighbors:
            # Create a new copy of the path for each recursive call
            new_path = path.copy()
            dfs(neighbor, visited.copy(), new_path)
    
    for node in nodes:
        dfs(node)
    
    # Remove duplicate cycles
    unique_cycles = []
    seen_cycles = set()
    
    for cycle in cycles:
        # Convert cycle to a hashable representation for deduplication
        cycle_tuple = tuple(cycle)
        if cycle_tuple not in seen_cycles:
            seen_cycles.add(cycle_tuple)
            unique_cycles.append(cycle)
    
    return unique_cycles

def find_breaking_points(cycles, locations):
    """Find optimal points to break each cycle based on usage patterns."""
    breaking_points = []
    
    for cycle in cycles:
        # Create a list of all reference pairs in this cycle
        cycle_edges = []
        for i in range(len(cycle) - 1):
            cycle_edges.append((cycle[i], cycle[i+1]))
        
        # Count references for each edge in the cycle
        edge_counts = {}
        for edge in cycle_edges:
            src, dst = edge
            location_key = f"{src} -> {dst}"
            edge_counts[edge] = len(locations.get(location_key, set()))
        
        # Find edge with minimum references to break
        if edge_counts:
            min_edge = min(edge_counts.items(), key=lambda x: x[1])[0]
            breaking_points.append({
                'cycle': cycle,
                'break_edge': min_edge,
                'reference_count': edge_counts[min_edge],
                'locations': list(locations.get(f"{min_edge[0]} -> {min_edge[1]}", set()))
            })
    
    return breaking_points

def remove_circular_references(spec, breaking_points):
    """Remove circular references identified by breaking points."""
    result = copy.deepcopy(spec)
    schemas = result.get("components", {}).get("schemas", {})
    removed_refs = []
    
    # Function to remove a specific reference
    def remove_ref(obj, src_schema, dst_schema, ref_path):
        try:
            if not ref_path:
                return False
            
            path_parts = ref_path.strip('/').split('/')
            current = obj
            
            # Navigate to the parent of the reference
            for i in range(len(path_parts) - 1):
                key = path_parts[i]
                # Handle array indices
                if key.isdigit():
                    key = int(key)
                if isinstance(current, dict) and key in current:
                    current = current[key]
                elif isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
                    current = current[key]
                else:
                    return False
            
            # Remove or modify the reference
            last_key = path_parts[-1]
            if last_key.isdigit():
                last_key = int(last_key)
                
            if isinstance(current, dict) and last_key in current:
                if isinstance(current[last_key], dict) and "$ref" in current[last_key] and \
                current[last_key]["$ref"] == f"#/components/schemas/{dst_schema}":
                    # Add metadata about the removed reference
                    current[last_key] = {
                        "x-removed-circular-ref": f"#/components/schemas/{dst_schema}",
                        "type": "object",
                        "description": f"Circular reference to {dst_schema} was removed"
                    }
                    return True
            elif isinstance(current, list) and isinstance(last_key, int) and 0 <= last_key < len(current):
                if isinstance(current[last_key], dict) and "$ref" in current[last_key] and \
                current[last_key]["$ref"] == f"#/components/schemas/{dst_schema}":
                    # Add metadata about the removed reference
                    current[last_key] = {
                        "x-removed-circular-ref": f"#/components/schemas/{dst_schema}",
                        "type": "object",
                        "description": f"Circular reference to {dst_schema} was removed"
                    }
                    return True
            
            return False
        except Exception as e:
            print(f"Error removing reference {ref_path} from {src_schema} to {dst_schema}: {e}")
            return False
    
    for point in breaking_points:
        src_schema, dst_schema = point['break_edge']
        
        # Make a copy of the locations to avoid modification during iteration
        locations = list(point['locations'])
        for location in locations:
            if remove_ref(schemas[src_schema], src_schema, dst_schema, location):
                removed_refs.append({
                    'source_schema': src_schema,
                    'target_schema': dst_schema,
                    'path': location
                })
    
    return result, removed_refs

def generate_report(cycles, breaking_points, removed_refs, output_report):
    """Generate a detailed report about circular references and modifications."""
    report = {
        "detected_cycles": [{"cycle": " -> ".join(cycle)} for cycle in cycles],
        "breaking_points": [
            {
                "cycle": " -> ".join(point["cycle"]),
                "broken_edge": f"{point['break_edge'][0]} -> {point['break_edge'][1]}",
                "reference_count": point["reference_count"],
                "locations": list(point["locations"])
            } 
            for point in breaking_points
        ],
        "removed_references": removed_refs
    }
    
    with open(output_report, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report

def resolve_openapi_circular_refs(input_file, output_file, report_file):
    """Main function to resolve circular references in an OpenAPI spec."""
    spec = load_openapi_spec(input_file)
    
    # Build the reference graph and collect locations
    graph, locations = build_reference_graph(spec)
    
    # Detect cycles
    cycles = detect_cycles(graph)
    
    if cycles:
        print(f"Detected {len(cycles)} circular reference cycles:")
        for i, cycle in enumerate(cycles):
            print(f"Cycle {i+1}: {' -> '.join(cycle)}")
        
        # Find optimal breaking points
        breaking_points = find_breaking_points(cycles, locations)
        
        # Remove circular references
        modified_spec, removed_refs = remove_circular_references(spec, breaking_points)
        
        # Generate report
        report = generate_report(cycles, breaking_points, removed_refs, report_file)
        
        # Print summary
        print(f"\nRemoved {len(removed_refs)} circular references")
        print(f"Complete report saved to {report_file}")
        
        # Save the modified specification
        save_openapi_spec(modified_spec, output_file)
        print(f"Modified OpenAPI spec saved to {output_file}")
        
    else:
        print("No circular references detected")
        save_openapi_spec(spec, output_file)
        # Create an empty report
        generate_report([], [], [], report_file)

if __name__ == "__main__":
    # python openapi_circular_resolver.py openai_shortened_api.yaml resolved_openai.yaml --report circular_ref_report.json
    parser = argparse.ArgumentParser(description="Resolve circular references in OpenAPI 3.0 specifications")
    parser.add_argument("input_file", help="Path to the input OpenAPI specification file (.json, .yaml, or .yml)")
    parser.add_argument("output_file", help="Path to save the modified OpenAPI specification")
    parser.add_argument("--report", default="circular_references_report.json", 
                        help="Path to save the detailed report of circular references")
    
    args = parser.parse_args()
    
    resolve_openapi_circular_refs(args.input_file, args.output_file, args.report)
