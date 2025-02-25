import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import requests
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
from datetime import datetime
from gremlin_python.process.graph_traversal import __
from gremlin_python.structure.graph import Graph
from gremlin_python.process.traversal import T
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.driver.serializer import GraphSONSerializersV3d0

# Replace with your actual Neptune endpoint
NEPTUNE_ENDPOINT = "db-neptune-1.cluster-cyenjim10cpi.us-east-1.neptune.amazonaws.com"
AWS_REGION = "us-east-1"  # Replace with your region

DEBUG_MODE = False  # Set to True to enable debug logging

def debug_log(message):
    if DEBUG_MODE:
        print(f"Debug: {message}")

def get_neptune_auth_headers():
    debug_log("Generating Neptune authentication headers...")
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        if not credentials:
            raise Exception("No AWS credentials found")
        
        region = session.region_name or 'us-east-1'  # Replace with your region if needed
        
        # Get current timestamp
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        
        # Create the request to sign
        request = AWSRequest(
            method='GET',
            url=f'https://{NEPTUNE_ENDPOINT}:8182/gremlin',
            headers={
                'host': f'{NEPTUNE_ENDPOINT}:8182',
                'x-amz-date': timestamp
            }
        )
        
        # Sign the request
        SigV4Auth(credentials, 'neptune-db', region).add_auth(request)
        
        # Extract and return the signed headers
        auth_headers = dict(request.headers.items())
        debug_log("Authentication headers generated successfully")
        return auth_headers
        
    except Exception as e:
        debug_log(f"Error generating Neptune authentication headers: {str(e)}")
        raise

def clean_permission_set_name(arn):
    name = arn.split('/')[-1]
    if name.startswith('ps-'):
        name = name[3:]
    return name.replace('-', ' ').title()

def get_access_data(g, username):
    debug_log(f"Starting data collection for user {username}...")
    try:
        access_matrix = g.V().hasLabel('User').has('userName', username)\
            .out('MEMBER_OF').as_('group')\
            .outE('HAS_ACCESS_TO').as_('access')\
            .project('account', 'permission_set', 'group')\
            .by(__.inV().values('accountName'))\
            .by('permissionSetArn')\
            .by(__.select('group').values('groupName'))\
            .toList()
        
        debug_log(f"Raw data collected for {username}. Items: {len(access_matrix)}")
        
        if not access_matrix:
            debug_log(f"No access data found for user: {username}")
            return pd.DataFrame(columns=['Account', 'Permission Set', 'Permission Set Name', 
                                         'Group', 'Environment'])
        
        rows = []
        for access in access_matrix:
            rows.append({
                'Account': access['account'],
                'Permission Set': access['permission_set'],
                'Permission Set Name': clean_permission_set_name(access['permission_set']),
                'Group': access['group'],
                'Environment': 'Production' if 'prod' in access['account'].lower() 
                             else 'Non-Production' if any(env in access['account'].lower() 
                             for env in ['dev', 'test', 'stage']) else 'Other'
            })
        
        df = pd.DataFrame(rows).drop_duplicates()
        debug_log(f"Data processed for {username}. Final shape: {df.shape}")
        return df
        
    except Exception as e:
        debug_log(f"Error collecting access data for {username}: {str(e)}")
        return pd.DataFrame(columns=['Account', 'Permission Set', 'Permission Set Name', 
                                     'Group', 'Environment'])

def get_org_access_data(g):
    debug_log("Starting organizationall data collection...")
    try:
        users = g.V().hasLabel('User').values('userName').toList()
        debug_log(f"Found {len(users)} users")
        
        all_data = []
        for username in users:
            user_df = get_access_data(g, username)
            user_df['Username'] = username
            all_data.append(user_df)
        
        org_df = pd.concat(all_data, ignore_index=True)
        debug_log(f"Organizational data collected. Final shape: {org_df.shape}")
        return org_df
        
    except Exception as e:
        debug_log(f"Error collecting organizational data: {str(e)}")
        return pd.DataFrame(columns=['Username', 'Account', 'Permission Set', 
                                     'Permission Set Name', 'Group', 'Environment'])

def analyze_access_overlap(df):
    debug_log("Analyzing access overlap...")
    try:
        # Create user-group matrix
        user_group_matrix = pd.crosstab(df['Username'], df['Group'])
        
        # Calculate overlap
        overlapping_groups = (user_group_matrix > 0).dot((user_group_matrix > 0).T)
        
        # Calculate overlap percentages
        total_users = len(user_group_matrix)
        overlap_percentages = (overlapping_groups / total_users) * 100
        
        return {
            'matrix': overlapping_groups,
            'percentages': overlap_percentages
        }
    except Exception as e:
        debug_log(f"Error in access overlap analysis: {str(e)}")
        return None

def analyze_permission_sets(df):
    debug_log("Analyzing permission sets...")
    try:
        # Define permission set categories
        permission_categories = {
            'admin': ['admin', 'dba', 'platform', 'arch'],
            'write': ['write', 'full', 'poweruser'],
            'read': ['read', 'ro', 'view'],
            'special': ['devops', 'lead', 'support']
        }
        
        # Analyze user permissions
        user_permissions = {}
        conflicts = []
        
        for username in df['Username'].unique():
            user_perms = df[df['Username'] == username]['Permission Set Name'].str.lower()
            user_categories = set()
            
            for category, keywords in permission_categories.items():
                if any(word in user_perms.str.cat() for word in keywords):
                    user_categories.add(category)
            
            user_permissions[username] = user_categories
            
            # Check for conflicts (e.g., both read and write permissions)
            if 'read' in user_categories and ('write' in user_categories or 'admin' in user_categories):
                conflicts.append(username)
        
        return {
            'user_permissions': user_permissions,
            'conflicts': conflicts
        }
    except Exception as e:
        debug_log(f"Error in permission set analysis: {str(e)}")
        return None

def analyze_environment_access(df):
    debug_log("Analyzing environment access...")
    try:
        # Group by username and count unique environments
        user_env_access = df.groupby('Username')['Environment'].agg(set).to_dict()
        
        # Get all possible environments
        all_environments = set(df['Environment'].unique())
        debug_log(f"All environments found: {all_environments}")
        
        # Find users with access to all environments
        users_all_envs = [
            username for username, envs in user_env_access.items() 
            if envs == all_environments and len(envs) > 1  # Make sure they have access to multiple environments
        ]
        
        debug_log(f"Found {len(users_all_envs)} users with access to all environments")
        debug_log(f"Environment counts per user sample: {dict(list(user_env_access.items())[:5])}")
        
        # Count users with access to specific environment combinations
        env_combinations = {
            'prod_and_nonprod': [],
            'only_prod': [],
            'only_nonprod': [],
            'other': []
        }
        
        for username, envs in user_env_access.items():
            if 'Production' in envs and 'Non-Productiotion' in envs:
                env_combinations['prod_and_nonprod'].append(username)
            elif 'Production' in envs and len(envs) == 1:
                env_combinations['only_prod'].append(username)
            elif 'Non-Production' in envs and len(envs) == 1:
                env_combinations['only_nonprod'].append(username)
            else:
                env_combinations['other'].append(username)

        return {
            'env_per_user': user_env_access,
            'users_all_envs': users_all_envs,
            'env_combinations': env_combinations
        }
    except Exception as e:
        debug_log(f"Error in environment access analysis: {str(e)}")
        return None

def analyze_group_patterns(df):
    debug_log("Analyzing group patterns...")
    try:
        # Calculate group statistics
        group_stats = df.groupby('Group').agg({
            'Username': 'nunique',
            'Permission Set': 'nunique',
            'Account': 'nunique'
        }).rename(columns={
            'Username': 'User_Count',
            'Permission Set': 'Permission_Set_Count',
            'Account': 'Account_Count'
        })
        
        # Identify empty or potentially problematic groups
        empty_groups = group_stats[group_stats['User_Count'] == 0].index.tolist()
        single_user_groups = group_stats[group_stats['User_Count'] == 1].index.tolist()
        
        # Analyze group membership distribution
        user_group_counts = df.groupby('Username')['Group'].nunique()
        unusual_group_counts = user_group_counts[
            user_group_counts > user_group_counts.mean() + 2*user_group_counts.std()
        ]
        
        return {
            'group_stats': group_stats,
            'empty_groups': empty_groups,
            'single_user_groups': single_user_groups,
            'unusual_group_counts': unusual_group_counts
        }
    except Exception as e:
        debug_log(f"Error in group pattern analysis: {str(e)}")
        return None

def analyze_access_matrix(df):
    debug_log("Analyzing access matrix...")
    try:
        # Create user-group matrix
        user_group_matrix = pd.crosstab(df['Username'], df['Group'])
        
        # Calculate access patterns
        access_patterns = pd.DataFrame({
            'User': user_group_matrix.index,
            'Group_Count': user_group_matrix.sum(axis=1),
            'Groups': [','.join(user_group_matrix.columns[user_group_matrix.loc[user] > 0].tolist()) 
                      for user in user_group_matrix.index]
        })
        
        return {
            'matrix': user_group_matrix,
            'patterns': access_patterns
        }
    except Exception as e:
        debug_log(f"Error in access matrix analysis: {str(e)}")
        return None

def generate_security_insights(df):
    debug_log("Generating security insights...")
    try:
        insights = {
            'access_overlap': analyze_access_overlap(df),
            'permission_sets': analyze_permission_sets(df),
            'environment_access': analyze_environment_access(df),
            'group_patterns': analyze_group_patterns(df),
            'access_matrix': analyze_access_matrix(df)
        }
        
        # Calculate overall risk metrics
        risk_metrics = {
            'total_users': df['Username'].nunique(),
            'users_with_conflicts': len(insights['permission_sets']['conflicts']),
            'users_with_all_envs': len(insights['environment_access']['users_all_envs']),
            'empty_groups': len(insights['group_patterns']['empty_groups'])
        }
        
        insights['risk_metrics'] = risk_metrics
        return insights
        
    except Exception as e:
        debug_log(f"Error generating security insights: {str(e)}")
        return None

def generate_security_report(insights, df):
    debug_log("Generating security report...")
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AWS SSO Security Analysis</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 40px;
                line-height: 1.6;
            }
            .header { margin-bottom: 30px; }
            .section {
                margin-bottom: 40px;
                background: #fff;
                padding: 20px;
                border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            .risk-high { color: #d73a49; }
            .risk-medium { color: #f66a0a; }
            .risk-low { color: #28a745; }
            h2 { 
                color: #333;
                border-bottom: 2px solid #eee;
                padding-bottom: 10px;
            }
            ul { padding-left: 20px; }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }
            th, td {
                padding: 12px;
                border: 1px solid #ddd;
                text-align: left;
            }
            th { background: #f5f5f5; }
            tr:nth-child(even) { background: #f9f9f9; }
        </style>
    </head>
    <body>
    """
    
    # Add Executive Summary
    html_content += f"""
        <div class="header">
            <h1>AWS SSO Security Analysis Report</h1>
            <p>Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
        
        <div class="section">
            <h2>Executive Summary</h2>
            <ul>
                <li>Total Users: {insights['risk_metrics']['total_users']}</li>
                <li class="{'risk-high' if insights['risk_metrics']['users_with_conflicts'] > 0 else 'risk-low'}">
                    Users with Permission Conflicts: {insights['risk_metrics']['users_with_conflicts']}
                </li>
                <li class="{'risk-high' if insights['risk_metrics']['users_with_all_envs'] > 5 else 'risk-medium'}">
                    Users with All Environment Access: {insights['risk_metrics']['users_with_all_envs']}
                </li>
            </ul>
        </div>
    """
    
    # Add Environment Access Section
    html_content += """
        <div class="section">
            <h2>Environment Access Analysis</h2>
    """
    if insights['environment_access']:
        env_combinations = insights['environment_access']['env_combinations']
        html_content += f"""
            <h3>Environment Access Distribution</h3>
            <ul>
                <li>Users with access to all environments: {len(insights['environment_access']['users_all_envs'])}</li>
                <li>Users with both Prod and Non-Prod access: {len(env_combinations['prod_and_nonprod'])}</li>
                <li>Users with Production access only: {len(env_combinations['only_prod'])}</li>
                <li>Users with Non-Production access only: {len(env_combinations['only_nonprod'])}</li>
                <li>Users with other environment combinations: {len(env_combinations['other'])}</li>
            </ul>

            <h3>Users with All Environment Access</h3>
            <div class="subsection">
                <p>The following users have access to all environments:</p>
                <ul>
                    {"".join(f"<li>{user}</li>" for user in insights['environment_access']['users_all_envs'])}
                </ul>
            </div>
        """
    
    # Add Group Analysis Section
    html_content += """
        <div class="section">
            <h2>Group Analysis</h2>
    """
    if insights['group_patterns']:
        html_content += f"""
            <h3>Empty Groups</h3>
            <ul>
                {"".join(f"<li>{group}</li>" for group in insights['group_patterns']['empty_groups'])}
            </ul>
            
            <h3>Single-User Groups</h3>
            <ul>
                {"".join(f"<li>{group}</li>" for group in insights['group_patterns']['single_user_groups'])}
            </ul>
        """
    
    # Add Access Matrix Section
    if insights['access_matrix']:
        html_content += """
            <div class="section">
                <h2>Access Matrix Analysis</h2>
        """
        matrix_data = insights['access_matrix']['patterns']
        html_content += f"""
                <h3>User Access Patterns</h3>
                <table class="matrix-table">
                    <tr>
                        <th>User</th>
                        <th>Number of Groups</th>
                    </tr>
                    {"".join(f"<tr><td>{row['User']}</td><td>{row['Group_Count']}</td></tr>" 
                            for _, row in matrix_data.iterrows())}
                </table>
            </div>
        """

    html_content += """
    </body>
    </html>
    """
    
    # Generate Excel Report
    excel_filename = f"sso_security_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(excel_filename, engine='xlsxwriter') as writer:
        # Summary Sheet
        summary_data = pd.DataFrame([insights['risk_metrics']])
        summary_data.to_excel(writer, sheet_name='Summary', index=False)
        
        # Environment Access
        if insights['environment_access']:
            # Users with all environments access
            pd.DataFrame(insights['environment_access']['users_all_envs'], 
                        columns=['Username']).to_excel(writer, 
                                                     sheet_name='Full Env Access', 
                                                     index=False)
            
  
            # Environment combinations
            env_combinations = insights['environment_access']['env_combinations']
            env_data = {
                'Category': ['Prod and Non-Prod', 'Production Only', 'Non-Production Only', 'Other'],
                'Count': [
                    len(env_combinations['prod_and_nonprod']),
                    len(env_combinations['only_prod']),
                    len(env_combinations['only_nonprod']),
                    len(env_combinations['other'])
                ],
                'Users': [
                    ', '.join(env_combinations['prod_and_nonprod']),
                    ', '.join(env_combinations['only_prod']),
                    ', '.join(env_combinations['only_nonprod']),
                    ', '.join(env_combinations['other'])
                ]
            }
            pd.DataFrame(env_data).to_excel(writer, 
                                          sheet_name='Environment Access', 
                                          index=False)
        
        # Group Analysis
        if insights['group_patterns']:
            insights['group_patterns']['group_stats'].to_excel(writer, 
                                                             sheet_name='Group Statistics')
        
        # Access Matrix
        if insights['access_matrix']:
            insights['access_matrix']['patterns'].to_excel(writer, 
                                                         sheet_name='Access Matrix', 
                                                         index=False)
        
        # Format workbook
        workbook = writer.book
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D3D3D3',
            'border': 1
        })
        
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.set_row(0, None, header_format)
            worksheet.autofit()
    
    return html_content, excel_filename

def main():
    try:
        debug_log("Starting connection process...")
        auth_headers = get_neptune_auth_headers()
        graph = Graph()
        conn = DriverRemoteConnection(
            f'wss://{NEPTUNE_ENDPOINT}:8182/gremlin',
            'g',
            message_serializer=GraphSONSerializersV3d0(),
            headers=auth_headers
        )
        g = graph.traversal().withRemote(conn)
        
        # Test connection
        test = g.V().limit(1).toList()
        debug_log(f"Connection test result: {len(test)} vertices found")
        
        # Generate organizational data
        print("\nGenerating organizational report...")
        df_org = get_org_access_data(g)
        
        if df_org.empty:
            print("Warning: No organizational data found")
        else:
            debug_log(f"Analyzing security for {df_org['Username'].nunique()} users")
            
            # Generate security insights
            insights = generate_security_insights(df_org)
            
            # Generate security report
            html_content, excel_file = generate_security_report(insights, df_org)
            
            # Save HTML report
            html_file = f"sso_security_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(html_file, 'w') as f:
                f.write(html_content)
            
            print(f"\nSecurity reports generated:")
            print(f"HTML: {html_file}")
            print(f"Excel: {excel_file}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        raise
        
    finally:
        debug_log("Closing connection")
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
