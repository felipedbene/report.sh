"""Shared utilities for Neptune database operations and configuration."""
import boto3
import os
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Configuration Constants
REGION = os.getenv('AWS_REGION', 'us-east-1')
NEPTUNE_ENDPOINT = os.getenv('NEPTUNE_ENDPOINT', 'db-neptune-12.cluster-cyenjim10cpi.us-east-1.neptune.amazonaws.com')
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
        
        return {
            'Host': f'{NEPTUNE_ENDPOINT}:8182',
            **request.headers
        }
    except Exception as e:
        debug_log(f"Error generating Neptune auth headers: {str(e)}")
        raise