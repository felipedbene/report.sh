#!/usr/bin/env python3
import os
import json
import boto3
import argparse
from datetime import datetime
from jinja2 import Template
from collections import defaultdict, Counter
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T, P, Cardinality
from neptune_python_utils.endpoints import Endpoints
from neptune_python_utils.gremlin_utils import GremlinUtils

# Default configuration constants - reuse from import_json_data.py
DEFAULTS = {
    "REGION": "us-east-1",
    "NEPTUNE_ENDPOINT": "primarydbinstance-taijvcthrfqz.cyenjim10cpi.us-east-1.neptune.amazonaws.com",
    "NEPTUNE_PORT": "8182",
    "OUTPUT_DIR": "reports"
}

def connect_to_neptune(args):
    """Reuse the connection function from import_json_data.py"""
    try:
        print(f"Connecting to Neptune at {args.neptune_endpoint}")
        
        session = boto3.Session(region_name=args.region)
        credentials = session.get_credentials()
        
        if not credentials:
            raise Exception("No AWS credentials found")
        
        endpoints = Endpoints(
            neptune_endpoint=args.neptune_endpoint,
            region_name=args.region,
            credentials=credentials
        )
        
        gremlin_utils = GremlinUtils(endpoints)
        conn = gremlin_utils.remote_connection()
        g = traversal().withRemote(conn)
        
        return g, conn
    except Exception as e:
        print(f"Failed to connect to Neptune: {str(e)}")
        raise

def get_user_data(g, email):
    """Get all access data for a user"""
    try:
        data = {
            'username': email,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'groups': set(),
            'accounts': set(),
            'permission_sets': set(),
            'access_matrix': [],
            'environments': defaultdict(int)
        }
        
        # Find user and their groups
        user_vertex = g.V().has('User', 'email', email).next()
        
        # Get all groups the user is a member of
        groups = g.V(user_vertex).out('MEMBER_OF').toList()
        
        for group in groups:
            group_name = g.V(group).values('groupName').next()
            data['groups'].add(group_name)
            
            # Get accounts this group has access to
            accounts = g.V(group).out('HAS_ACCESS_TO').toList()
            
            # Get permission sets for this group
            permissions = g.V(group).out('HAS_PERMISSION').toList()
            
            for account in accounts:
                account_name = g.V(account).values('accountName').next()
                data['accounts'].add(account_name)
                
                for perm in permissions:
                    perm_arn = g.V(perm).values('arn').next()
                    data['permission_sets'].add(perm_arn)
                    
                    # Determine environment based on account name
                    environment = determine_environment(account_name)
                    data['environments'][environment] += 1
                    
                    # Add to access matrix
                    entry = {
                        'account': account_name,
                        'permission_set': perm_arn,
                        'group': group_name,
                        'environment': environment
                    }
                    data['access_matrix'].append(entry)
        
        return data
        
    except Exception as e:
        print(f"Error getting user data: {str(e)}")
        raise

def determine_environment(account_name):
    """Determine environment based on account name"""
    account_lower = account_name.lower()
    if any(x in account_lower for x in ['prod', 'production']):
        return 'Production'
    elif any(x in account_lower for x in ['dev', 'development', 'test', 'stage', 'staging']):
        return 'Non-Production'
    else:
        return 'Other'

def generate_html_report(data, output_file):
    """Generate HTML report from the data"""
    template = Template('''
<!DOCTYPE html>
<html>
<head>
    <title>AWS SSO Access Analysis - {{ data.username }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        h1, h2 { color: #333; }
        .summary { margin: 20px 0; }
        .distribution { margin: 20px 0; }
    </style>
</head>
<body>
    <h1>AWS SSO Access Analysis</h1>
    
    <div class="summary">
        <h2>User Information</h2>
        <p>Username: {{ data.username }}</p>
        <p>Analysis Date: {{ data.analysis_date }}</p>
    </div>

    <div class="summary">
        <h2>Access Summary</h2>
        <p>Total Groups: {{ data.groups|length }}</p>
        <p>Total Accounts: {{ data.accounts|length }}</p>
        <p>Total Permission Sets: {{ data.permission_sets|length }}</p>
    </div>

    <div class="distribution">
        <h2>Environment Distribution</h2>
        {% for env, count in data.environments.items() %}
        <p>{{ env }}: {{ count }}</p>
        {% endfor %}
    </div>

    <h2>Access Matrix</h2>
    <table>
        <tr>
            <th>Account</th>
            <th>Permission Set</th>
            <th>Group</th>
            <th>Environment</th>
        </tr>
        {% for entry in data.access_matrix %}
        <tr>
            <td>{{ entry.account }}</td>
            <td>{{ entry.permission_set }}</td>
            <td>{{ entry.group }}</td>
            <td>{{ entry.environment }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
    ''')
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Generate and save the report
    with open(output_file, 'w') as f:
        f.write(template.render(data=data))

def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate AWS SSO Access Report')
    parser.add_argument('--email', help='Email address of the user to analyze')
    parser.add_argument('--org-report', action='store_true',
                       help='Generate organization-wide report')    
    parser.add_argument('--region', default=DEFAULTS["REGION"],
                       help=f'AWS Region (default: {DEFAULTS["REGION"]})')
    parser.add_argument('--neptune-endpoint', default=DEFAULTS["NEPTUNE_ENDPOINT"],
                       help=f'Neptune endpoint (default: {DEFAULTS["NEPTUNE_ENDPOINT"]})')
    parser.add_argument('--output-dir', default=DEFAULTS["OUTPUT_DIR"],
                       help=f'Output directory for reports (default: {DEFAULTS["OUTPUT_DIR"]})')
    return parser.parse_args()
class OrganizationReport:
    def __init__(self, g):
        self.g = g
        self.analysis_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.user_count = 0
        self.all_groups = set()
        self.all_accounts = set()
        self.all_permission_sets = set()
        self.environment_distribution = defaultdict(int)
        self.group_distribution = defaultdict(int)
        self.user_access_patterns = defaultdict(int)
        self.group_membership_counts = defaultdict(int)
        self.account_access_counts = defaultdict(int)
        self.permission_set_usage = defaultdict(int)

    def generate_report(self):
        """Generate organization-wide report"""
        self._collect_data()
        return self._render_template()

    def _collect_data(self):
        """Collect organization-wide statistics"""
        try:
            # Get all users
            users = self.g.V().hasLabel('User').toList()
            self.user_count = len(users)

            for user in users:
                email = self.g.V(user).values('email').next()
                print(f"Processing user: {email}")

                # Get user's groups
                groups = self.g.V(user).out('MEMBER_OF').toList()
                user_groups = set()

                for group in groups:
                    group_name = self.g.V(group).values('groupName').next()
                    user_groups.add(group_name)
                    self.all_groups.add(group_name)
                    self.group_membership_counts[group_name] += 1

                    # Get accounts this group has access to
                    accounts = self.g.V(group).out('HAS_ACCESS_TO').toList()
                    
                    # Get permission sets for this group
                    permissions = self.g.V(group).out('HAS_PERMISSION').toList()

                    for account in accounts:
                        account_name = self.g.V(account).values('accountName').next()
                        self.all_accounts.add(account_name)
                        self.account_access_counts[account_name] += 1
                        
                        environment = determine_environment(account_name)
                        self.environment_distribution[environment] += 1

                        for perm in permissions:
                            perm_arn = self.g.V(perm).values('arn').next()
                            self.all_permission_sets.add(perm_arn)
                            self.permission_set_usage[perm_arn] += 1

                # Track access pattern for this user
                pattern = f"Groups: {len(user_groups)}, Accounts: {len(set(self.account_access_counts.keys()))}"
                self.user_access_patterns[pattern] += 1

        except Exception as e:
            print(f"Error collecting organization data: {str(e)}")
            raise

    def _render_template(self):
        """Render the organization report template"""
        template = Template('''
    <!DOCTYPE html>
    <html>
    <head>
    <title>AWS SSO Organization Access Analysis</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        h1, h2 { color: #333; }
        .summary { margin: 20px 0; }
        .chart { margin: 20px 0; height: 300px; }
        .distribution { margin: 20px 0; }
    </style>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    </head>
    <body>
    <h1>AWS SSO Organization Access Analysis</h1>

    <div class="summary">
        <h2>Organization Summary</h2>
        <p>Analysis Date: {{ analysis_date }}</p>
        <p>Total Users: {{ user_count }}</p>
        <p>Total Groups: {{ all_groups|length }}</p>
        <p>Total Accounts: {{ all_accounts|length }}</p>
        <p>Total Permission Sets: {{ all_permission_sets|length }}</p>
    </div>

    <div class="distribution">
        <h2>Environment Distribution</h2>
        <div id="envChart" class="chart"></div>
        {% for env, count in environment_distribution.items() %}
        <p>{{ env }}: {{ count }}</p>
        {% endfor %}
    </div>

    <div class="distribution">
        <h2>Most Used Groups</h2>
        <table>
            <tr>
                <th>Group Name</th>
                <th>Member Count</th>
            </tr>
            {% for group, count in group_membership_counts|dictsort(by='value', reverse=True) if loop.index <= 20 %}
            <tr>
                <td>{{ group }}</td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="distribution">
        <h2>Most Accessed Accounts</h2>
        <table>
            <tr>
                <th>Account Name</th>
                <th>Access Count</th>
            </tr>
            {% for account, count in account_access_counts|dictsort(by='value', reverse=True) if loop.index <= 20 %}
            <tr>
                <td>{{ account }}</td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="distribution">
        <h2>Most Used Permission Sets</h2>
        <table>
            <tr>
                <th>Permission Set</th>
                <th>Usage Count</th>
            </tr>
            {% for perm, count in permission_set_usage|dictsort(by='value', reverse=True) if loop.index <= 20 %}
            <tr>
                <td>{{ perm }}</td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="distribution">
        <h2>User Access Patterns</h2>
        <table>
            <tr>
                <th>Pattern</th>
                <th>User Count</th>
            </tr>
            {% for pattern, count in user_access_patterns|dictsort(by='value', reverse=True) %}
            <tr>
                <td>{{ pattern }}</td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <script>
        // Add interactive charts using Plotly
        var envData = [{
            values: {{ environment_distribution.values()|list|tojson }},
            labels: {{ environment_distribution.keys()|list|tojson }},
            type: 'pie'
        }];
        Plotly.newPlot('envChart', envData);
    </script>
    </body>
    </html>
        ''')

        return template.render(
            analysis_date=self.analysis_date,
            user_count=self.user_count,
            all_groups=self.all_groups,
            all_accounts=self.all_accounts,
            all_permission_sets=self.all_permission_sets,
            environment_distribution=dict(self.environment_distribution),
            group_membership_counts=dict(self.group_membership_counts),
            account_access_counts=dict(self.account_access_counts),
            permission_set_usage=dict(self.permission_set_usage),
            user_access_patterns=dict(self.user_access_patterns)
        )


def main():
    args = parse_arguments()
    conn = None
    
    try:
        # Connect to Neptune
        g, conn = connect_to_neptune(args)
        
        if args.org_report:
            # Generate organization report
            org_report = OrganizationReport(g)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(args.output_dir, f"sso_org_report_{timestamp}.html")
            
            with open(output_file, 'w') as f:
                f.write(org_report.generate_report())
            
            print(f"Organization report generated: {output_file}")
            
        elif args.email:
            # Generate individual user report
            data = get_user_data(g, args.email)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(args.output_dir, 
                                     f"sso_access_report_{args.email.replace('@', '_')}_{timestamp}.html")
            generate_html_report(data, output_file)
            print(f"User report generated: {output_file}")
            
        else:
            print("Please specify either --email or --org-report")
            
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()
            print("Neptune connection closed")

if __name__ == "__main__":
    main()
