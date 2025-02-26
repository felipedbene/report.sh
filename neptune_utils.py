"""Shared utilities for Neptune database operations and configuration."""
import boto3
import os
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Configuration Constants
REGION = os.getenv('AWS_REGION', 'us-east-1')
NEPTUNE_ENDPOINT = os.getenv('NEPTUNE_ENDPOINT', 
    'db-neptune-12.cluster-cyenjim10cpi.us-east-1.neptune.amazonaws.com')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '100'))
S3_BUCKET = os.getenv('S3_BUCKET', 'awssso-benfelip')
GRAPH_DATA_DIR = os.getenv('GRAPH_DATA_DIR', 'graph_data')

# Environment classification
ENVIRONMENTS = {
    'production': ['prod'],
    'non_production': ['dev', 'test', 'stage'],
    'other': []  # Catch-all for unclassified environments
}

def debug_log(message):
    """Unified debug logging function."""
    print(f"DEBUG: {message}")
    
def clear_neptune_database(g):
    """Clear all data from Neptune database.
    
    Args:
        g: Neptune graph traversal source
    """
    debug_log("Clearing all data from Neptune database...")
    try:
        debug_log("Fixing traversers attribute error - using next() instead of toList()")
        # Use next() which doesn't have the traversers issue
        g.V().drop().next()
        debug_log("Successfully cleared all vertices and edges from the database")
    except Exception as e:
        debug_log(f"Error in clear_neptune_database: {str(e)}")
        # Fall back to safe_clear_neptune_database
        safe_clear_neptune_database(g)
        
def safe_clear_neptune_database(g):
    """Alternative method to clear Neptune database that avoids the ResultSet issue.
    
    Args:
        g: Neptune graph traversal source or connection
        
    Raises:
        ValueError: If g is None
        AttributeError: If connection retrieval fails
        Exception: For other errors during clearing
    """
    debug_log("Using safe alternative method to clear database...")
    
    # First validate we have a graph object
    if g is None:
        debug_log("Cannot clear database - graph object is None")
        raise ValueError("Graph traversal source cannot be None")
        
    try:
        # Try to get the remote connection if it's a traversal source
        if hasattr(g, 'remote_connection'):
            conn = g.remote_connection
            if conn is None:
                debug_log("Remote connection is None")
                raise ValueError("Remote connection is None")
            conn.submit("g.V().drop()").all().result()
        else:
            # Assume g is the client connection itself
            g.submit("g.V().drop()").all().result()
        debug_log("Successfully cleared database using safe method")
    except Exception as e:
        debug_log(f"Error in safe clear method: {str(e)}")
        raise

def get_neptune_auth_headers():
    """Generate AWS SigV4 authentication headers for Neptune database access.
    
    Returns:
        dict: Headers required for Neptune authentication
    """
    debug_log("Generating Neptune authentication headers...")
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        auth = SigV4Auth(credentials, 'neptune-db', REGION)
        request = AWSRequest(method='GET', url=f'wss://{NEPTUNE_ENDPOINT}:8182/gremlin')
        auth.add_auth(request)
        
        headers = {
            'Host': f'{NEPTUNE_ENDPOINT}:8182',
        }
        # Add only the necessary SigV4 headers
        for key in ['Authorization', 'X-Amz-Date', 'X-Amz-Security-Token']:
            if key in request.headers:
                headers[key] = request.headers[key]
                
        return headers
    except Exception as e:
        debug_log(f"Error generating Neptune auth headers: {str(e)}")
        raise
