# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "boto3>=1.15.0",
#     "gremlin-python>=3.5.0",
#     "neptune-python-utils>=1.0.0",
# ]
# ///
import os
import json
import boto3
import argparse
from datetime import datetime
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T, P, Cardinality
from neptune_python_utils.endpoints import Endpoints
from neptune_python_utils.gremlin_utils import GremlinUtils

# Default configuration constants
DEFAULTS = {
    "REGION": "us-east-1",
    "NEPTUNE_ENDPOINT": "primarydbinstance-taijvcthrfqz.cyenjim10cpi.us-east-1.neptune.amazonaws.com",
    "NEPTUNE_PORT": "8182",
    "S3_BUCKET": "awssso-benfelip",
    "S3_PREFIX": "graph_data/",
    "BATCH_SIZE": 100
}

class ErrorLogger:
    def __init__(self):
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.error_file = f"neptune_errors_{self.timestamp}.log"
        self.debug_file = f"neptune_debug_{self.timestamp}.log"

    def log_error(self, message, data=None):
        with open(self.error_file, 'a') as f:
            f.write(f"\n{datetime.now().isoformat()}: {message}\n")
            if data:
                f.write(json.dumps(data, indent=2) + "\n")

    def log_debug(self, message, data=None):
        with open(self.debug_file, 'a') as f:
            f.write(f"\n{datetime.now().isoformat()}: {message}\n")
            if data:
                f.write(json.dumps(data, indent=2) + "\n")

def parse_arguments():
    parser = argparse.ArgumentParser(description='Load data into Neptune graph database')
    parser.add_argument('--clean', action='store_true', 
                       help='Clean existing graph data before loading')
    parser.add_argument('--debug', action='store_true',
                       help='Enable detailed debug logging')
    parser.add_argument('--region', default=DEFAULTS["REGION"],
                       help=f'AWS Region (default: {DEFAULTS["REGION"]})')
    parser.add_argument('--neptune-endpoint', default=DEFAULTS["NEPTUNE_ENDPOINT"],
                       help=f'Neptune endpoint (default: {DEFAULTS["NEPTUNE_ENDPOINT"]})')
    parser.add_argument('--s3-bucket', default=DEFAULTS["S3_BUCKET"],
                       help=f'S3 bucket name (default: {DEFAULTS["S3_BUCKET"]})')
    parser.add_argument('--s3-prefix', default=DEFAULTS["S3_PREFIX"],
                       help=f'S3 prefix path (default: {DEFAULTS["S3_PREFIX"]})')
    parser.add_argument('--batch-size', type=int, default=DEFAULTS["BATCH_SIZE"],
                       help=f'Batch size for loading (default: {DEFAULTS["BATCH_SIZE"]})')
    return parser.parse_args()

def connect_to_neptune(args):
    """Connect to Neptune using neptune-python-utils"""
    try:
        print(f"Connecting to Neptune at {args.neptune_endpoint}")
        
        session = boto3.Session(region_name=args.region)
        credentials = session.get_credentials()
        
        if not credentials:
            raise Exception("No AWS credentials found")
        
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        print(f"AWS Identity: {identity['Arn']}")
        
        endpoints = Endpoints(
            neptune_endpoint=args.neptune_endpoint,
            region_name=args.region,
            credentials=credentials
        )
        
        gremlin_utils = GremlinUtils(endpoints)
        conn = gremlin_utils.remote_connection()
        g = traversal().withRemote(conn)
        
        test = g.V().limit(1).count().next()
        print(f"Connection test successful. Found {test} vertices.")
        
        return g, conn
    except Exception as e:
        print(f"Failed to connect to Neptune: {str(e)}")
        raise

def load_json_from_s3(args):
    """Load JSON data from S3 bucket"""
    try:
        print("Loading JSON data from S3...")
        s3_key = [f"{args.s3_prefix}edges.json", f"{args.s3_prefix}vertices.json"]
        
        print(f"Using S3 bucket: {args.s3_bucket}, key: {s3_key}")
        
        s3_client = boto3.client('s3', region_name=args.region)
        vertices = []
        edges = []
        
        for key in s3_key:
            try:
                print(f"Loading from S3: {args.s3_bucket}/{key}")
                response = s3_client.get_object(Bucket=args.s3_bucket, Key=key)
                data = json.loads(response['Body'].read().decode('utf-8'))
                
                if 'vertices.json' in key:
                    vertices = data if isinstance(data, list) else data.get('vertices', [])
                    print(f"Loaded {len(vertices)} vertices")
                elif 'edges.json' in key:
                    edges = data if isinstance(data, list) else data.get('edges', [])
                    print(f"Loaded {len(edges)} edges")
            except Exception as e:
                print(f"Error loading {key}: {str(e)}")
        
        return vertices, edges
    except Exception as e:
        print(f"Error in load_json_from_s3: {str(e)}")
        return [], []

def load_vertices(g, vertices, error_logger):
    """Load vertices into Neptune"""
    print("\nLoading vertices...")
    successful = 0
    failed = 0
    vertex_patterns = {}  # Track ID patterns

    for vertex in vertices:
        try:
            vertex_type = vertex.get('properties', {}).get('type', '').upper()
            if not vertex_type:
                vertex_type = vertex.get('label', '').upper()
            
            vertex_id = vertex['id']
            props = vertex.get('properties', {})

            # Track ID patterns for debugging
            prefix = vertex_id.split('-')[0]
            vertex_patterns[prefix] = vertex_patterns.get(prefix, 0) + 1

            if vertex_type == 'USER':
                g.addV('User')\
                    .property('userId', props.get('userId', vertex_id.replace('USER_', '')))\
                    .property('userName', props.get('userName', ''))\
                    .property('email', props.get('email', ''))\
                    .next()
            
            elif vertex_type == 'GROUP':
                g.addV('Group')\
                    .property('groupId', props.get('groupId', vertex_id.replace('GROUP_', '')))\
                    .property('groupName', props.get('groupName', ''))\
                    .next()
            
            elif vertex_type == 'ACCOUNT':
                g.addV('Account')\
                    .property('accountId', props.get('accountId', vertex_id.replace('ACCOUNT_', '')))\
                    .property('accountName', props.get('accountName', ''))\
                    .next()
            
            elif vertex_type == 'PERMISSION_SET':
                g.addV('PermissionSet')\
                    .property('arn', props.get('arn', vertex_id.replace('PERMISSION_SET_', '')))\
                    .property('name', props.get('name', ''))\
                    .next()

            successful += 1
            if successful % 100 == 0:
                print(f"Successfully loaded {successful} vertices")

        except Exception as e:
            failed += 1
            error_logger.log_error(f"Error loading vertex:", {
                "vertex": vertex,
                "error": str(e)
            })

    # Log vertex pattern analysis
    error_logger.log_debug("Vertex ID patterns:", vertex_patterns)
    
    print(f"\nVertex loading summary:")
    print(f"Total successful: {successful}")
    print(f"Total failed: {failed}")
    return successful, failed

def clean_entity_id(entity_id, entity_type):
    """Clean entity IDs by removing prefixes and handling special cases"""
    if entity_type == 'User':
        # Handle the special case of IDs starting with '90676c734f-'
        cleaned_id = entity_id.replace('USER_', '')
        if cleaned_id.startswith('90676c734f-'):
            cleaned_id = cleaned_id.replace('90676c734f-', '')
        return cleaned_id
    elif entity_type == 'Group':
        return entity_id.replace('GROUP_', '')
    elif entity_type == 'Account':
        return entity_id.replace('ACCOUNT_', '')
    elif entity_type == 'PermissionSet':
        return entity_id.replace('PERMISSION_SET_', '')
    return entity_id

def load_edges_batch(g, edges, batch_size=DEFAULTS["BATCH_SIZE"], error_logger=None):
    """Load edges with proper relationship handling and deduplication"""
    if not edges:
        print("No edges to load!")
        return 0, 0
        
    print(f"\nLoading {len(edges)} edges...")
    successful = 0
    failed = 0
    
    # Track processed edges to avoid duplicates
    processed_edges = set()
    
    for i in range(0, len(edges), batch_size):
        batch = edges[i:i + batch_size]
        print(f"\nProcessing batch {i//batch_size + 1} of {len(edges)//batch_size + 1}")
        
        for edge in batch:
            try:
                label = edge['label']
                from_id = edge['from']
                to_id = edge['to']
                
                # Create unique edge identifier
                edge_key = f"{from_id}|{label}|{to_id}|{edge['properties'].get('permissionSetArn', '')}"
                
                # Skip if we've already processed this edge
                if edge_key in processed_edges:
                    continue
                
                # Clean IDs based on entity type
                if label == 'MEMBER_OF':
                    from_clean = clean_entity_id(from_id, 'User')
                    to_clean = clean_entity_id(to_id, 'Group')
                    
                    # Verify vertices exist before creating edge
                    from_exists = g.V().has('User', 'userId', from_clean).count().next() > 0
                    to_exists = g.V().has('Group', 'groupId', to_clean).count().next() > 0
                    
                    if not from_exists or not to_exists:
                        raise Exception(f"Missing vertices: User exists: {from_exists}, Group exists: {to_exists}")
                    
                    g.V().has('User', 'userId', from_clean)\
                        .addE(label)\
                        .to(__.V().has('Group', 'groupId', to_clean))\
                        .property('timestamp', edge['properties']['timestamp'])\
                        .next()
                
                elif label == 'HAS_ACCESS_TO':
                    from_clean = clean_entity_id(from_id, 'Group')
                    to_clean = clean_entity_id(to_id, 'Account')
                    
                    g.V().has('Group', 'groupId', from_clean)\
                        .addE(label)\
                        .to(__.V().has('Account', 'accountId', to_clean))\
                        .property('timestamp', edge['properties']['timestamp'])\
                        .property('permissionSetArn', edge['properties']['permissionSetArn'])\
                        .next()
                
                elif label == 'HAS_PERMISSION':
                    from_clean = clean_entity_id(from_id, 'Group')
                    to_clean = clean_entity_id(to_id, 'PermissionSet')
                    
                    g.V().has('Group', 'groupId', from_clean)\
                        .addE(label)\
                        .to(__.V().has('PermissionSet', 'arn', to_clean))\
                        .property('timestamp', edge['properties']['timestamp'])\
                        .next()
                
                processed_edges.add(edge_key)
                successful += 1
                debug_log(f"Successfully added edge from {edge['from_vertex']} to {edge['to_vertex']}")
            except Exception as e:
                debug_log(f"Error adding edge from {edge['from_vertex']} to {edge['to_vertex']}: {str(e)}")
                failed += 1
                if error_logger:
                    error_logger.log_error(f"Error in edge ({label}):", {
                        "edge": edge,
                        "error": str(e) if str(e) else "Vertex not found or other database error"
                    })
    
    print("\nEdge loading summary:")
    try:
        edge_counts = g.E().groupCount().by(T.label).next()
        for label, count in edge_counts.items():
            print(f"{label}: {count}")
    except Exception as e:
        print(f"Error getting edge counts: {str(e)}")
    
    print(f"\nTotal successful: {successful}")
    print(f"Total failed: {failed}")
    print(f"Duplicate edges skipped: {len(edges) - len(processed_edges)}")
    
    return successful, failed

def clean_graph(g):
    """Remove all vertices and edges from the graph"""
    print("\nCleaning existing graph data...")
    try:
        count = g.V().count().next()
        g.V().drop().iterate()
        print(f"Dropped {count} vertices and all associated edges")
        
        remaining = g.V().count().next()
        if remaining == 0:
            print("Graph successfully cleaned")
        else:
            print(f"WARNING: {remaining} vertices still remain")
    except Exception as e:
        print(f"Error cleaning graph: {str(e)}")
        raise

def main():
    args = parse_arguments()
    conn = None
    error_logger = ErrorLogger()
    
    try:
        print("Connecting to Neptune...")
        g, conn = connect_to_neptune(args)
        
        if args.clean:
            clean_graph(g)
        
        vertices, edges = load_json_from_s3(args)
        vertex_load_success, vertex_load_failed = load_vertices(g, vertices, error_logger)
        edge_load_success, edge_load_failed = load_edges_batch(g, edges, args.batch_size, error_logger)
        
        print("\nProcessing complete!")
        print(f"Error log: {error_logger.error_file}")
        print(f"Debug log: {error_logger.debug_file}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        error_logger.log_error("Fatal error:", str(e))
        raise
    finally:
        if conn:
            conn.close()
            print("\nConnection closed")

if __name__ == "__main__":
    main()
