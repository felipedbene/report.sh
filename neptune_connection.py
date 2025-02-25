"""Neptune database connection utilities."""
from gremlin_python.driver import client
from gremlin_python.driver.protocol import GremlinServerError
from neptune_utils import get_neptune_auth_headers, NEPTUNE_ENDPOINT, debug_log

def create_neptune_connection():
    """Create a connection to Neptune database with proper error handling.
    
    Returns:
        client.Client: Gremlin client connected to Neptune
    
    Raises:
        GremlinServerError: If connection fails
        Exception: For other unexpected errors
    """
    try:
        debug_log(f"Connecting to Neptune at {NEPTUNE_ENDPOINT}")
        # Create a connection without headers_supplier
        # headers_supplier is not supported in newer gremlin-python versions
        # Instead, we'll use the connection without headers for IAM auth
        # or pass static headers if needed
        headers = get_neptune_auth_headers()
        return client.Client(
            f'wss://{NEPTUNE_ENDPOINT}:8182/gremlin',
            'g',
            message_serializer=client.serializer.GraphSONSerializersV2d0(),
            headers=headers
        )
    except GremlinServerError as e:
        debug_log(f"Failed to connect to Neptune: {str(e)}")
        raise
    except Exception as e:
        debug_log(f"Unexpected error connecting to Neptune: {str(e)}")
        raise

def execute_query(g, query, **params):
    """Execute a Gremlin query with proper error handling.
    
    Args:
        g: Gremlin traversal source
        query: Query string to execute
        **params: Query parameters
        
    Returns:
        Query results
        
    Raises:
        GremlinServerError: If query execution fails
        Exception: For other unexpected errors
    """
    try:
        return g.V().eval(query, **params).toList()
    except GremlinServerError as e:
        debug_log(f"Query execution failed: {str(e)}")
        raise
    except Exception as e:
        debug_log(f"Unexpected error during query: {str(e)}")
        raise