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

def load_vertices_batch(g, vertices):
    """Load vertices with proper error handling"""
    try:
        debug_log("Loading vertices...")
        for vertex in vertices:
            try:
                # Using submit() instead of next() for client connection
                g.addV(vertex['label'])\
                    .property(T.id, vertex['id'])\
                    .toList()
                for k, v in vertex['properties'].items():
                    g.V(vertex['id'])\
                        .property(k, v)\
                        .toList()
            except Exception as e:
                debug_log(f"Error loading vertex {vertex['id']}: {str(e)}")
                continue
    except Exception as e:
        debug_log(f"Error in vertex loading batch: {str(e)}")
        raise

def load_edges_batch(g, edges, batch_size=BATCH_SIZE):
    """Load edges with proper relationship handling"""
    debug_log("Loading edges...")
    successful = 0
    failed = 0
    current_batch = []

    try:
        for edge in edges:
            current_batch.append(edge)
            if len(current_batch) >= batch_size:
                successful_batch, failed_batch = process_edge_batch(g, current_batch)
                successful += successful_batch
                failed += failed_batch
                current_batch = []

        if current_batch:
            successful_batch, failed_batch = process_edge_batch(g, current_batch)
            successful += successful_batch
            failed += failed_batch

        debug_log(f"Edge loading complete. Successful: {successful}, Failed: {failed}")
    except Exception as e:
        debug_log(f"Error in edge loading: {str(e)}")
        raise

def process_edge_batch(g, batch):
    """Process a batch of edges"""
    debug_log(f"Processing batch of {len(batch)} edges")
    successful = 0
    failed = 0

    try:
        for edge in batch:
            try:
                g.V(edge['from_vertex'])\
                    .addE(edge['label'])\
                    .to(g.V(edge['to_vertex']))\
                    .toList()
                successful += 1
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
        g = Graph().traversal().withRemote(conn)
        
        # Clear database before importing new data
        clear_neptune_database(g)

        load_vertices_batch(g, vertices)
        load_edges_batch(g, edges)

    except Exception as e:
        debug_log(f"Error in main execution: {str(e)}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    main()