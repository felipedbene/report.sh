#!/usr/bin/env python3
import os
import json
import boto3
import argparse
from datetime import datetime
from jinja2 import Template
from collections import defaultdict, Counter
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.traversal import T, P, Cardinality
from gremlin_python.process.graph_traversal import __, GraphTraversalSource
from neptune_python_utils.endpoints import Endpoints
from neptune_python_utils.gremlin_utils import GremlinUtils

# Default configuration constants
DEFAULTS = {
    "REGION": "us-east-1",
    "NEPTUNE_ENDPOINT": "primarydbinstance-taijvcthrfqz.cyenjim10cpi.us-east-1.neptune.amazonaws.com",
    "NEPTUNE_PORT": "8182",
    "OUTPUT_DIR": "reports"
}

def parse_arguments():
    parser = argparse.ArgumentParser(description='AWS SSO Access Analysis Tool')
    parser.add_argument('--neptune-endpoint', default=DEFAULTS['NEPTUNE_ENDPOINT'],
                       help='Neptune endpoint')
    parser.add_argument('--region', default=DEFAULTS['REGION'],
                       help='AWS region')
    parser.add_argument('--output-dir', default=DEFAULTS['OUTPUT_DIR'],
                       help='Output directory')
    parser.add_argument('--toxic', action='store_true',
                       help='Generate toxic combinations report')
    return parser.parse_args()

def connect_to_neptune(args):
    """Connect to Neptune database"""
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

def get_permission_type(permission_name):
    """Determine if a permission is read-only or read-write"""
    lower_name = permission_name.lower()
    ro_patterns = ['readonly', 'read-only', 'viewer', 'view-only', 'read_only']
    if any(pattern in lower_name for pattern in ro_patterns):
        return 'ro'
    return 'rw'  # Default to RW if unclear

def analyze_toxic_combinations(g):
    """Identify critical toxic combinations in AWS SSO"""
    print("Starting toxic combination analysis...")
    findings = {
        'critical_findings': [],
        'statistics': {},
        'remediation': {}
    }
    
    try:
        # Basic data statistics
        print("\nGathering basic statistics...")
        users_count = g.V().hasLabel('User').count().next()
        groups_count = g.V().hasLabel('Group').count().next()
        accounts_count = g.V().hasLabel('Account').count().next()
        permission_sets_count = g.V().hasLabel('PermissionSet').count().next()
        
        print(f"Total Users: {users_count}")
        print(f"Total Groups: {groups_count}")
        print(f"Total Accounts: {accounts_count}")
        print(f"Total Permission Sets: {permission_sets_count}")

        # Get all accounts and classify them
        print("\nAnalyzing cross-environment access...")
        all_accounts = g.V().hasLabel('Account').project('id', 'name'). \
            by('accountId'). \
            by('accountName'). \
            toList()
        
        print("\nSample accounts:")
        for acc in all_accounts[:5]:
            print(f"Account: {acc}")
        
        # Classify accounts
        prod_accounts = []
        nonprod_accounts = []
        
        for account in all_accounts:
            account_name = account['name']
            if 'non-prod' in account_name.lower() or 'nonprod' in account_name.lower() or 'non prod' in account_name.lower() or '-dev' in account_name.lower() or 'stage' in account_name.lower() or 'test' in account_name.lower():
                nonprod_accounts.append(account_name)
            elif 'prod' in account_name.lower():
                prod_accounts.append(account_name)
            else:
                nonprod_accounts.append(account_name)

        print(f"\nFound {len(prod_accounts)} production and {len(nonprod_accounts)} non-production accounts")
        print("Sample prod accounts:", prod_accounts[:5])
        print("Sample nonprod accounts:", nonprod_accounts[:5])

        # Get user access patterns with RO/RW distinction
        print("\nGetting user access patterns...")
        user_access = g.V().hasLabel('User').project('user', 'access_details'). \
            by('email'). \
            by(__.out('MEMBER_OF').as_('group'). \
               out('HAS_ACCESS_TO').as_('account'). \
               optional(__.out('HAS_PERMISSION')).as_('permission'). \
               select('group', 'account', 'permission'). \
               by(__.values('groupName').fold()). \
               by(__.values('accountName').fold()). \
               by(__.values('name').fold()). \
               fold()). \
            toList()

        print("\nSample user access pattern:")
        if user_access:
            sample_user = user_access[0]
            print(f"User: {sample_user['user']}")
            print(f"Access details (first 2): {json.dumps(sample_user['access_details'][:2], indent=2)}")

        findings['cross_env'] = []
        for user in user_access:
            user_email = user['user']
            prod_access = {'ro': set(), 'rw': set()}
            nonprod_access = {'ro': set(), 'rw': set()}
            groups = set()

            for access in user['access_details']:
                if not access:
                    continue

                group_names = access['group']
                account_names = access['account']
                permission_names = access['permission']

                for group_name in group_names:
                    groups.add(group_name)

                for account_name in account_names:
                    # Check for read-only patterns in permission names
                    access_type = 'ro' if any('readonly' in p.lower() or 'read-only' in p.lower() or '-ro' in p.lower() 
                                            for p in permission_names) else 'rw'

                    if account_name in prod_accounts:
                        prod_access[access_type].add(account_name)
                    elif account_name in nonprod_accounts:
                        nonprod_access[access_type].add(account_name)

            if (prod_access['ro'] or prod_access['rw']) and (nonprod_access['ro'] or nonprod_access['rw']):
                findings['cross_env'].append({
                    'user': user_email,
                    'prod_access_ro': list(prod_access['ro']),
                    'prod_access_rw': list(prod_access['rw']),
                    'nonprod_access_ro': list(nonprod_access['ro']),
                    'nonprod_access_rw': list(nonprod_access['rw']),
                    'groups': list(groups)
                })

        print(f"\nFound {len(findings['cross_env'])} users with cross-environment access")
        if findings['cross_env']:
            print("Sample cross-env user:", json.dumps(findings['cross_env'][0], indent=2))

        # Admin access analysis
        print("\nAnalyzing administrative access...")
        print("\nAnalyzing permission sets...")
        all_permission_sets = g.V().hasLabel('PermissionSet').values('name').toList()
        print("Sample permission sets:", all_permission_sets[:10])

        # Look for admin patterns in permission names
        admin_patterns = [
            'admin', 'administrator', 'poweruser', 'fullaccess',
            'securityadmin', 'systemadmin', 'organizationadmin'
        ]
        
        admin_permission_sets = [
            perm for perm in all_permission_sets 
            if any(pattern in perm.lower() for pattern in admin_patterns)
        ]
        
        print(f"Found {len(admin_permission_sets)} admin permission sets")
        print("Sample admin permission sets:", admin_permission_sets[:5])

        # Find users with admin permissions
        admin_users = g.V().hasLabel('User'). \
            where(__.out('MEMBER_OF'). \
                  out('HAS_PERMISSION'). \
                  has('name', P.within(admin_permission_sets))). \
            project('user', 'admin_groups'). \
            by('email'). \
            by(__.out('MEMBER_OF'). \
               where(__.out('HAS_PERMISSION'). \
                     has('name', P.within(admin_permission_sets))). \
               values('groupName'). \
               fold()). \
            toList()

        findings['admin_access'] = []
        for user in admin_users:
            if user['admin_groups']:
                findings['admin_access'].append({
                    'user': user['user'],
                    'admin_groups': user['admin_groups']
                })

        print(f"\nFound {len(findings['admin_access'])} users with admin access")
        if findings['admin_access']:
            print("Sample admin user:", json.dumps(findings['admin_access'][0], indent=2))

        # Extensive access analysis
        print("\nAnalyzing extensive account access...")
        threshold = accounts_count * 0.8

        user_account_access = g.V().hasLabel('User').project('user', 'access_details'). \
            by('email'). \
            by(__.out('MEMBER_OF').out('HAS_ACCESS_TO'). \
               project('account', 'permission_info'). \
               by('accountName'). \
               by(__.out('HAS_PERMISSION').values('name').fold()). \
               fold()). \
            toList()

        findings['extensive_access'] = []
        for user in user_account_access:
            access_by_type = {'ro': set(), 'rw': set()}
            
            for access in user['access_details']:
                account_name = access['account']
                permissions = access['permission_info']
                
                access_type = 'ro' if any('readonly' in p.lower() or 'read-only' in p.lower() or '-ro' in p.lower() 
                                        for p in permissions) else 'rw'
                access_by_type[access_type].add(account_name)

            total_accounts = len(access_by_type['ro'] | access_by_type['rw'])
            if total_accounts > threshold:
                findings['extensive_access'].append({
                    'user': user['user'],
                    'ro_accounts': list(access_by_type['ro']),
                    'rw_accounts': list(access_by_type['rw']),
                    'total_accounts': accounts_count,
                    'access_percentage': round((total_accounts / accounts_count) * 100, 1)
                })

        print(f"\nFound {len(findings['extensive_access'])} users with extensive access")
        if findings['extensive_access']:
            print("Sample extensive access user:", json.dumps(findings['extensive_access'][0], indent=2))

        # Calculate detailed statistics with de-duplication
        all_prod_rw = set()
        all_prod_ro = set()
        all_nonprod_rw = set()
        all_nonprod_ro = set()
        users_with_prod_rw = set()
        users_with_prod_ro = set()
        users_with_nonprod_rw = set()
        users_with_nonprod_ro = set()

        for user in findings['cross_env']:
            if user['prod_access_rw']:
                users_with_prod_rw.add(user['user'])
                all_prod_rw.update(user['prod_access_rw'])
            if user['prod_access_ro']:
                users_with_prod_ro.add(user['user'])
                all_prod_ro.update(user['prod_access_ro'])
            if user['nonprod_access_rw']:
                users_with_nonprod_rw.add(user['user'])
                all_nonprod_rw.update(user['nonprod_access_rw'])
            if user['nonprod_access_ro']:
                users_with_nonprod_ro.add(user['user'])
                all_nonprod_ro.update(user['nonprod_access_ro'])

        findings['statistics'] = {
            'total_users': users_count,
            'total_groups': groups_count,
            'total_accounts': accounts_count,
            'total_permission_sets': permission_sets_count,
            'users_with_cross_env': len(findings['cross_env']),
            'users_with_admin': len(findings['admin_access']),
            'users_with_extensive_access': len(findings['extensive_access']),
            'users_with_prod_rw': len(users_with_prod_rw),
            'users_with_prod_ro': len(users_with_prod_ro),
            'users_with_nonprod_rw': len(users_with_nonprod_rw),
            'users_with_nonprod_ro': len(users_with_nonprod_ro),
            'unique_prod_rw_accounts': len(all_prod_rw),
            'unique_prod_ro_accounts': len(all_prod_ro),
            'unique_nonprod_rw_accounts': len(all_nonprod_rw),
            'unique_nonprod_ro_accounts': len(all_nonprod_ro),
            'users_with_both_prod_nonprod_rw': len(users_with_prod_rw.intersection(users_with_nonprod_rw)),
            'high_risk_users': len([u for u in findings['cross_env'] 
                                  if u['prod_access_rw'] and u['nonprod_access_rw'] and 
                                  len(u['prod_access_rw']) > 5 and len(u['nonprod_access_rw']) > 5])
        }

        # Add percentage calculations
        findings['statistics'].update({
            'prod_rw_coverage': round((len(all_prod_rw) / len(prod_accounts)) * 100, 1),
            'prod_ro_coverage': round((len(all_prod_ro) / len(prod_accounts)) * 100, 1),
            'nonprod_rw_coverage': round((len(all_nonprod_rw) / len(nonprod_accounts)) * 100, 1),
            'nonprod_ro_coverage': round((len(all_nonprod_ro) / len(nonprod_accounts)) * 100, 1),
            'users_with_cross_env_percentage': round((len(findings['cross_env']) / users_count) * 100, 1),
            'users_with_admin_percentage': round((len(findings['admin_access']) / users_count) * 100, 1)
        })

        print("\nDetailed Statistics:")
        print(f"Production RW Accounts: {len(all_prod_rw)} of {len(prod_accounts)} ({findings['statistics']['prod_rw_coverage']}%)")
        print(f"Production RO Accounts: {len(all_prod_ro)} of {len(prod_accounts)} ({findings['statistics']['prod_ro_coverage']}%)")
        print(f"Non-Production RW Accounts: {len(all_nonprod_rw)} of {len(nonprod_accounts)} ({findings['statistics']['nonprod_rw_coverage']}%)")
        print(f"Non-Production RO Accounts: {len(all_nonprod_ro)} of {len(nonprod_accounts)} ({findings['statistics']['nonprod_ro_coverage']}%)")
        print(f"\nHigh Risk Users (>5 accounts in both environments): {findings['statistics']['high_risk_users']}")

        # Add remediation suggestions
        findings['remediation'] = {
            'cross_env': [
                "Implement strict environment separation",
                "Review and justify any cross-environment access",
                "Consider using separate roles for production and non-production",
                "Limit production write access to necessary personnel only"
            ],
            'admin_access': [
                "Limit administrative access to necessary personnel only",
                "Implement time-bound administrative access",
                "Regular review of administrative permissions",
                "Consider read-only access for monitoring purposes"
            ],
            'extensive_access': [
                "Implement least-privilege access model",
                "Regular review of access patterns",
                "Consider implementing access boundaries",
                "Separate read and write permissions clearly"
            ]
        }

        return findings

    except Exception as e:
        print(f"Error in toxic combination analysis: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise

def generate_toxic_report(findings, output_file):
    """Generate HTML report for toxic combinations"""
    template = Template('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>AWS SSO Critical Access Patterns</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; max-width: 1200px; margin: 0 auto; }
            .finding { margin: 20px 0; padding: 15px; border-radius: 4px; background-color: #fff3e0; }
            .remediation { background-color: #e8f5e9; padding: 10px; margin: 10px 0; }
            table { width: 100%; border-collapse: collapse; margin: 15px 0; }
            th, td { padding: 8px; border: 1px solid #ddd; text-align: left; }
            th { background-color: #f5f5f5; }
            .critical { color: #d32f2f; }
            .warning { color: #f57c00; }
            .ro { color: #2196F3; }
            .rw { color: #F44336; }
            .access-type { display: inline-block; padding: 2px 6px; border-radius: 3px; margin: 2px; }
            .stat-block { margin: 20px 0; padding: 15px; background-color: #f5f5f5; border-radius: 4px; }
            .risk-high { background-color: #ffebee; }
            .risk-medium { background-color: #fff3e0; }
            .risk-low { background-color: #e8f5e9; }
        </style>
    </head>
    <body>
        <h1>AWS SSO Critical Access Patterns</h1>

        <div class="summary">
            <h2>Executive Summary</h2>
            <div class="stat-block">
                <h3>Overall Statistics</h3>
                <table>
                    <tr>
                        <th>Category</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                    <tr>
                        <td>Total Users</td>
                        <td>{{ findings.statistics.total_users }}</td>
                        <td>100%</td>
                    </tr>
                    <tr>
                        <td>Total AWS Accounts</td>
                        <td>{{ findings.statistics.total_accounts }}</td>
                        <td>-</td>
                    </tr>
                    <tr class="critical">
                        <td>Users with Cross-Environment Access</td>
                        <td>{{ findings.statistics.users_with_cross_env }}</td>
                        <td>{{ findings.statistics.users_with_cross_env_percentage }}%</td>
                    </tr>
                    <tr class="critical">
                        <td>Users with Administrative Access</td>
                        <td>{{ findings.statistics.users_with_admin }}</td>
                        <td>{{ findings.statistics.users_with_admin_percentage }}%</td>
                    </tr>
                    <tr class="warning">
                        <td>Users with Extensive Access (>80% of accounts)</td>
                        <td>{{ findings.statistics.users_with_extensive_access }}</td>
                        <td>{{ "%.1f"|format(findings.statistics.users_with_extensive_access / findings.statistics.total_users * 100) }}%</td>
                    </tr>
                    <tr class="critical">
                        <td>High Risk Users (>5 accounts in both envs)</td>
                        <td>{{ findings.statistics.high_risk_users }}</td>
                        <td>{{ "%.1f"|format(findings.statistics.high_risk_users / findings.statistics.total_users * 100) }}%</td>
                    </tr>
                </table>
            </div>

            <div class="stat-block">
                <h3>Access Pattern Analysis</h3>
                <table>
                    <tr>
                        <th>Access Type</th>
                        <th>Production</th>
                        <th>Non-Production</th>
                    </tr>
                    <tr>
                        <td>Read-Write Access (Users)</td>
                        <td class="rw">{{ findings.statistics.users_with_prod_rw }} ({{ "%.1f"|format(findings.statistics.users_with_prod_rw / findings.statistics.total_users * 100) }}%)</td>
                        <td class="rw">{{ findings.statistics.users_with_nonprod_rw }} ({{ "%.1f"|format(findings.statistics.users_with_nonprod_rw / findings.statistics.total_users * 100) }}%)</td>
                    </tr>
                    <tr>
                        <td>Read-Only Access (Users)</td>
                        <td class="ro">{{ findings.statistics.users_with_prod_ro }} ({{ "%.1f"|format(findings.statistics.users_with_prod_ro / findings.statistics.total_users * 100) }}%)</td>
                        <td class="ro">{{ findings.statistics.users_with_nonprod_ro }} ({{ "%.1f"|format(findings.statistics.users_with_nonprod_ro / findings.statistics.total_users * 100) }}%)</td>
                    </tr>
                    <tr>
                        <td>Unique Accounts (RW)</td>
                        <td>{{ findings.statistics.unique_prod_rw_accounts }} ({{ findings.statistics.prod_rw_coverage }}%)</td>
                        <td>{{ findings.statistics.unique_nonprod_rw_accounts }} ({{ findings.statistics.nonprod_rw_coverage }}%)</td>
                    </tr>
                    <tr>
                        <td>Unique Accounts (RO)</td>
                        <td>{{ findings.statistics.unique_prod_ro_accounts }} ({{ findings.statistics.prod_ro_coverage }}%)</td>
                        <td>{{ findings.statistics.unique_nonprod_ro_accounts }} ({{ findings.statistics.nonprod_ro_coverage }}%)</td>
                    </tr>
                </table>
            </div>
        </div>

        <div class="findings">
            <h2>Cross-Environment Access</h2>
            {% for finding in findings.cross_env %}
            <div class="finding {% if finding.prod_access_rw and finding.nonprod_access_rw %}risk-high{% endif %}">
                <h3>User: {{ finding.user }}</h3>
                <div class="production">
                    <h4>Production Access:</h4>
                    {% if finding.prod_access_rw %}
                    <p><span class="access-type rw">RW</span> <strong>Write Access ({{ finding.prod_access_rw|length }}):</strong> {{ finding.prod_access_rw|join(', ') }}</p>
                    {% endif %}
                    {% if finding.prod_access_ro %}
                    <p><span class="access-type ro">RO</span> <strong>Read-Only Access ({{ finding.prod_access_ro|length }}):</strong> {{ finding.prod_access_ro|join(', ') }}</p>
                    {% endif %}
                </div>
                <div class="non-production">
                    <h4>Non-Production Access:</h4>
                    {% if finding.nonprod_access_rw %}
                    <p><span class="access-type rw">RW</span> <strong>Write Access ({{ finding.nonprod_access_rw|length }}):</strong> {{ finding.nonprod_access_rw|join(', ') }}</p>
                    {% endif %}
                    {% if finding.nonprod_access_ro %}
                    <p><span class="access-type ro">RO</span> <strong>Read-Only Access ({{ finding.nonprod_access_ro|length }}):</strong> {{ finding.nonprod_access_ro|join(', ') }}</p>
                    {% endif %}
                </div>
                <p><strong>Through Groups ({{ finding.groups|length }}):</strong> {{ finding.groups|join(', ') }}</p>
            </div>
            {% endfor %}

            <h2>Administrative Access</h2>
            {% for finding in findings.admin_access %}
            <div class="finding risk-high">
                <h3>User: {{ finding.user }}</h3>
                <p><strong>Admin Groups:</strong> {{ finding.admin_groups|join(', ') }}</p>
            </div>
            {% endfor %}

            <h2>Extensive Account Access</h2>
            {% for finding in findings.extensive_access %}
            <div class="finding risk-medium">
                <h3>User: {{ finding.user }}</h3>
                <p><strong>Access Coverage:</strong> {{ finding.access_percentage }}% ({{ finding.total_accounts }} accounts)</p>
                {% if finding.ro_accounts %}
                <p><span class="access-type ro">RO</span> <strong>Read-Only Access ({{ finding.ro_accounts|length }}):</strong> {{ finding.ro_accounts|join(', ') }}</p>
                {% endif %}
                {% if finding.rw_accounts %}
                <p><span class="access-type rw">RW</span> <strong>Write Access ({{ finding.rw_accounts|length }}):</strong> {{ finding.rw_accounts|join(', ') }}</p>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        <div class="remediation">
            <h2>Remediation Recommendations</h2>
            
            <h3>Cross-Environment Access</h3>
            <ul>
            {% for item in findings.remediation.cross_env %}
                <li>{{ item }}</li>
            {% endfor %}
            </ul>

            <h3>Administrative Access</h3>
            <ul>
            {% for item in findings.remediation.admin_access %}
                <li>{{ item }}</li>
            {% endfor %}
            </ul>

            <h3>Extensive Access</h3>
            <ul>
            {% for item in findings.remediation.extensive_access %}
                <li>{{ item }}</li>
            {% endfor %}
            </ul>
        </div>
    </body>
    </html>
    ''')

    with open(output_file, 'w') as f:
        f.write(template.render(findings=findings))


def main():
    args = parse_arguments()
    os.makedirs(args.output_dir, exist_ok=True)
    
    conn = None
    try:
        g, conn = connect_to_neptune(args)
        
        if args.toxic:
            findings = analyze_toxic_combinations(g)
            output_file = os.path.join(
                args.output_dir, 
                f"sso_critical_access_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )
            generate_toxic_report(findings, output_file)
            print(f"\nCritical access patterns report generated: {output_file}")
            
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
