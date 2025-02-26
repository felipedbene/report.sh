import boto3
import json
import os
from gremlin_python.process.traversal import T
from gremlin_python.structure.graph import Graph
from neptune_utils import get_neptune_auth_headers, BATCH_SIZE, debug_log, S3_BUCKET, clear_neptune_database
from neptune_connection import create_neptune_connection

def load_json_from_s3():
    """Load graph data from S3 bucket"""
    try:
        debug_log("Loading data from S3...")
        s3 = boto3.client('s3')
        vertices = []
        edges = []

        # Load vertices
        vertices_obj = s3.get_object(Bucket=S3_BUCKET, Key='graph_data/vertices.json')
        vertices_data = json.loads(vertices_obj['Body'].read().decode('utf-8'))
        vertices.extend(vertices_data)

        # Load edges
        edges_obj = s3.get_object(Bucket=S3_BUCKET, Key='graph_data/edges.json')
        edges_data = json.loads(edges_obj['Body'].read().decode('utf-8'))
        edges.extend(edges_data)
        
        debug_log(f"Loaded {len(vertices)} vertices and {len(edges)} edges from S3")
        return vertices, edges
    except Exception as e:
        debug_log(f"Error loading data from S3: {str(e)}")
        raise

def load_vertices_batch(conn, vertices):
    """Load vertices with proper error handling"""
    try:
        debug_log("Loading vertices...")
        for vertex in vertices:
            try:
                # Use a different approach that avoids traversers attribute
                query = f"g.addV('{vertex['label']}').property('id', '{vertex['id']}')"
                future = conn.submitAsync(query)
                # Just wait for completion without accessing traversers
                future.result()
                
                # Add properties
                for k, v in vertex['properties'].items():
                    # Escape string values with quotes
                    if isinstance(v, str):
                        value_str = f"'{v}'"
                    else:
                        value_str = str(v)
                    prop_query = f"g.V('{vertex['id']}').property('{k}', {value_str})"
                    future = conn.submitAsync(prop_query)
                    # Just wait for completion without accessing traversers
                    future.result()
                        
                debug_log(f"Successfully loaded vertex {vertex['id']}")
            except Exception as e:
                debug_log(f"Error loading vertex {vertex['id']}: {str(e)}")
                continue
    except Exception as e:
        debug_log(f"Error in vertex loading batch: {str(e)}")
        raise

def load_edges_batch(conn, edges, batch_size=BATCH_SIZE):
    """Load edges with proper relationship handling"""
    debug_log("Loading edges...")
    successful = 0
    failed = 0
    current_batch = []

    try:
        for edge in edges:
            current_batch.append(edge)
            if len(current_batch) >= batch_size:
                successful_batch, failed_batch = process_edge_batch(conn, current_batch)
                successful += successful_batch
                failed += failed_batch
                current_batch = []

        if current_batch:
            successful_batch, failed_batch = process_edge_batch(conn, current_batch)
            successful += successful_batch
            failed += failed_batch

        debug_log(f"Edge loading complete. Successful: {successful}, Failed: {failed}")
    except Exception as e:
        debug_log(f"Error in edge loading: {str(e)}")
        raise

def process_edge_batch(conn, batch):
    """Process a batch of edges using direct connection"""
    debug_log(f"Processing batch of {len(batch)} edges")
    successful = 0
    failed = 0

    try:
        for edge in batch:
            try:
                # Use direct connection with submitAsync
                query = f"g.V('{edge['from_vertex']}').addE('{edge['label']}').to(g.V('{edge['to_vertex']}'))"
                future = conn.submitAsync(query)
                # Just wait for completion without accessing traversers
                future.result()
                
                # Add edge properties if any
                if 'properties' in edge and edge['properties']:
                    for k, v in edge['properties'].items():
                        # Escape string values with quotes
                        if isinstance(v, str):
                            value_str = f"'{v}'"
                        else:
                            value_str = str(v)
                        
                        # Query to add property to the edge
                        prop_query = f"g.E().hasLabel('{edge['label']}').where(" + \
                                    f"__.outV().hasId('{edge['from_vertex']}').and_().inV().hasId('{edge['to_vertex']}'))" + \
                                    f".property('{k}', {value_str})"
                        future = conn.submitAsync(prop_query)
                        # Just wait for completion without accessing traversers
                        future.result()
                
                successful += 1
                debug_log(f"Successfully added edge from {edge['from_vertex']} to {edge['to_vertex']}")
            except Exception as e:
                debug_log(f"Error adding edge from {edge['from_vertex']} to {edge['to_vertex']}: {str(e)}")
                failed += 1
                continue
    except Exception as e:
        debug_log(f"Batch processing error: {str(e)}")
        raise

    return successful, failed

def main():
    """Main execution function"""
    try:
        vertices, edges = load_json_from_s3()
        conn = create_neptune_connection()
        
        # Check if connection was successfully created
        if conn is None:
            debug_log("Failed to create Neptune connection - connection object is None")
            raise ConnectionError("Failed to establish Neptune database connection")
            
        g = Graph().traversal().withRemote(conn)
        
        # Clear database before importing new data
        try:
            debug_log("Attempting to clear database...")
            from neptune_utils import safe_clear_neptune_database
            safe_clear_neptune_database(g)
        except Exception as clear_error:
            debug_log(f"Error during safe clear: {str(clear_error)}")
            # Try alternate approach using the connection directly
            try:
                debug_log("Trying direct connection approach...")
                if conn is not None:
                    future = conn.submitAsync("g.V().drop()")
                    # Just wait for completion without accessing traversers
                    future.result()
                    debug_log("Successfully cleared database using direct connection")
                else:
                    debug_log("Cannot clear database - connection object is None")
                    raise ConnectionError("Neptune connection is None")
            except Exception as conn_error:
                debug_log(f"Failed to clear database: {str(conn_error)}")
                raise

        # Use the connection directly for both vertex and edge loading
        load_vertices_batch(conn, vertices)
        load_edges_batch(conn, edges)

    except Exception as e:
        debug_log(f"Error in main execution: {str(e)}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    main()