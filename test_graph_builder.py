#!/usr/bin/env python3
"""
Simple function to call build_graph_from_repo
"""

import sys
import os

# Add the codegraph directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'codegraph'))

from codegraph.graph_builder import build_graph_from_repo
from codegraph.exporters import export_json
from codegraph.manual_queries import slice_controllers


def call_build_graph_from_repo(repo_path: str, lang: str = "auto"):
    """Simple function to call build_graph_from_repo"""
    return build_graph_from_repo(repo_path, lang)


# Usage examples:
if __name__ == "__main__":
    # Example 1: Build graph from current directory
    print("Building graph from current directory...")
    graph = call_build_graph_from_repo("/Users/saichaitanyadarla/Documents/java")
    print(f"Graph has {len(graph.g.nodes)} nodes and {len(graph.g.nodes)} edges")
    
    # Get controllers slice
    print("Extracting controllers...")
    controllers_graph = slice_controllers(graph, neighbors=1)
    print(f"Controllers graph has {len(controllers_graph.g.nodes)} nodes")
    
    # Export to JSON
    print("Exporting graph to JSON...")
    export_json(graph, "code_graph.json")
    print("Graph exported to code_graph.json")
    
    # Export controllers to JSON
    export_json(controllers_graph, "controllers_graph.json")
    print("Controllers graph exported to controllers_graph.json")
    
    # Example 2: Build graph for specific language
    print("\nBuilding Java-only graph...")
    java_graph = call_build_graph_from_repo("/Users/saichaitanyadarla/Documents/java", lang="java")
    print(f"Java graph has {len(java_graph.g.nodes)} nodes")
    
    # Get Java controllers
    java_controllers = slice_controllers(java_graph, neighbors=1)
    print(f"Java controllers graph has {len(java_controllers.g.nodes)} nodes")
    
    # Export Java graph to JSON
    export_json(java_graph, "java_graph.json")
    print("Java graph exported to java_graph.json")
    
    # Export Java controllers to JSON
    export_json(java_controllers, "java_controllers.json")
    print("Java controllers exported to java_controllers.json")
    
    # Example 3: Build graph from specific path
    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
        lang = sys.argv[2] if len(sys.argv) > 2 else "auto"
        print(f"\nBuilding graph from {repo_path} with language {lang}...")
        custom_graph = call_build_graph_from_repo(repo_path, lang)
        print(f"Custom graph has {len(custom_graph.g.nodes)} nodes")
        
        # Get custom controllers
        custom_controllers = slice_controllers(custom_graph, neighbors=1)
        print(f"Custom controllers graph has {len(custom_controllers.g.nodes)} nodes")
        
        # Export custom graph to JSON
        export_json(custom_graph, f"custom_graph_{lang}.json")
        print(f"Custom graph exported to custom_graph_{lang}.json")
        
        # Export custom controllers to JSON
        export_json(custom_controllers, f"custom_controllers_{lang}.json")
        print(f"Custom controllers exported to custom_controllers_{lang}.json")
    
