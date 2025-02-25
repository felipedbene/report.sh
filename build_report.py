import boto3
import json
import pandas as pd
from datetime import datetime, timezone
import os
from gremlin_python.process.traversal import T
from neptune_utils import get_neptune_auth_headers, debug_log, ENVIRONMENTS
from neptune_connection import create_neptune_connection, execute_query

def clean_permission_set_name(arn):
    """Extract and clean permission set name from ARN"""
    return arn.split('/')[-1].replace('-', ' ').title()

def get_access_data(g, username):
    """Get access data for specific user"""
    try:
        results = g.V().has('label', 'User')\
            .has('username', username)\
            .as_('user')\
            .out('MEMBER_OF').as_('group')\
            .outE('HAS_ACCESS_TO').as_('access')\
            .inV().as_('account')\
            .select('user', 'group', 'access', 'account')\
            .by('username')\
            .by('name')\
            .by(T.label)\
            .by('name')\
            .toList()
        
        rows = []
        for result in results:
            access = {
                'user': result['user'],
                'group': result['group'],
                'account': result['account'],
                'permission_set': clean_permission_set_name(result['access'])
            }
            rows.append({
                'User': access['user'],
                'Account': access['account'],
                'Permission Set': access['permission_set'],
                'Group': access['group'],
                'Environment': 'Production' if any(env in access['account'].lower() 
                             for env in ENVIRONMENTS['production'])
                             else 'Non-Production' if any(env in access['account'].lower() 
                             for env in ENVIRONMENTS['non_production']) else 'Other'
            })
        
        df = pd.DataFrame(rows).drop_duplicates()
        return df.sort_values(['User', 'Account', 'Permission Set'])
        
    except Exception as e:
        debug_log(f"Error getting access data: {str(e)}")
        raise

def get_org_access_data(g):
    """Get access data for all users"""
    try:
        results = execute_query(g, '''
            g.V().hasLabel('User').as('user')
             .out('MEMBER_OF').as('group')
             .outE('HAS_ACCESS_TO').as('access')
             .inV().as('account')
             .select('user', 'group', 'access', 'account')
             .by('username')
             .by('name')
             .by(T.label)
             .by('name')
        ''')
        
        rows = []
        for result in results:
            access = {
                'user': result['user'],
                'group': result['group'],
                'account': result['account'],
                'permission_set': clean_permission_set_name(result['access'])
            }
            rows.append({
                'User': access['user'],
                'Account': access['account'],
                'Permission Set': access['permission_set'],
                'Group': access['group'],
                'Environment': 'Production' if any(env in access['account'].lower() 
                             for env in ENVIRONMENTS['production'])
                             else 'Non-Production' if any(env in access['account'].lower() 
                             for env in ENVIRONMENTS['non_production']) else 'Other'
            })
            
        return pd.DataFrame(rows).drop_duplicates()
    except Exception as e:
        debug_log(f"Error getting organization access data: {str(e)}")
        raise