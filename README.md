# AWS SSO Access Management System

This system allows you to collect, analyze, and visualize AWS SSO (Single Sign-On) access permissions using a Neptune graph database. It provides tools for data collection, import, and report generation to help administrators understand and manage access patterns.

## Features

- **AWS SSO Data Collection**: Collect users, groups, accounts, permission sets, and account assignments
- **Graph Database Integration**: Store and query relationship data in Amazon Neptune graph database
- **User-specific Access Analysis**: Generate detailed HTML reports showing permissions across AWS accounts
- **Organizational Overview**: Create organization-wide reports showing access patterns
- **Environment Classification**: Automatically categorize accounts into production, non-production, and other environments
- **Visual Access Patterns**: HTML reports with styling for easy interpretation of complex access relationships
- **Error Logging**: Comprehensive error handling and logging for data import and report generation

## Components

### 1. Data Collection (`g_collect.py`)

This module collects AWS SSO data using the AWS SDK and organizes it into a graph structure with vertices and edges.

```python
# Collect data from AWS SSO
collector = SSOGraphCollector()
graph_data = collector.collect_data()
save_graph_data(graph_data, output_dir)
```

The collector uses AWS boto3 to gather:
- Users from the Identity Store
- Groups and group memberships
- AWS accounts
- Permission sets
- Account assignments

### 2. Data Import (`import_json_data.py`)

Imports the collected data into a Neptune graph database, with comprehensive error handling and logging.

```bash
# Import data to Neptune
python import_json_data.py --input-dir ./data_directory --neptune-endpoint your-endpoint.neptune.amazonaws.com
```

Command line arguments:
- `--input-dir`: Directory containing the graph data (vertices.json and edges.json)
- `--neptune-endpoint`: Optional, overrides environment variable
- `--region`: AWS region (default: us-east-1)
- `--s3-input`: Use S3 as the data source instead of local files

### 3. Report Generation (`generate_report.py`)

Generates HTML reports for individual users or the entire organization, visualizing access permissions.

```bash
# Generate user report
python generate_report.py --email user@example.com --output-dir ./reports

# Generate organization report
python generate_report.py --org-report --output-dir ./reports
```

Command line arguments:
- `--email`: Email address of the user to analyze
- `--org-report`: Generate organization-wide report instead of user report
- `--output-dir`: Directory to save the report (default: reports)
- `--neptune-endpoint`: Optional, overrides environment variable

## Installation

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Configure your AWS credentials:
   ```
   aws configure
   ```
4. Set up environment variables:
   ```
   export AWS_REGION=us-east-1
   export NEPTUNE_ENDPOINT=your-neptune-endpoint.amazonaws.com
   ```

## Usage

### 1. Collect Data from AWS SSO

```bash
python g_collect.py
```

This will collect all AWS SSO data and save it to a timestamped directory (e.g., `iam_data_dump_20230415_120000`).

### 2. Import Data to Neptune

```bash
python import_json_data.py --input-dir ./iam_data_dump_20230415_120000
```

This imports the JSON data files into the Neptune graph database.

### 3. Generate Reports

For a specific user:
```bash
python generate_report.py --email user@example.com --output-dir ./reports
```

For an organization-wide report:
```bash
python generate_report.py --org-report --output-dir ./reports
```

Reports are saved with timestamped filenames to avoid overwriting previous reports.

## Report Examples

### User Report

The user report includes:
- User information (username, analysis date)
- Access summary (number of groups, accounts, and permission sets)
- Environment distribution (production vs. non-production access)
- Detailed tables of accounts and permissions

```html
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
        <p>Production Access: {{ data.env_distribution.production }}</p>
        <p>Non-Production Access: {{ data.env_distribution.non_production }}</p>
        <p>Other Access: {{ data.env_distribution.other }}</p>
    </div>

    <div>
        <h2>Group Memberships</h2>
        <table>
            <tr>
                <th>Group Name</th>
            </tr>
            {% for group in data.groups %}
            <tr>
                <td>{{ group }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <h2>Account Access</h2>
    <table>
        <tr>
            <th>Account Name</th>
            <th>Account ID</th>
            <th>Environment</th>
            <th>Permission Sets</th>
        </tr>
        {% for account in data.accounts %}
        <tr>
            <td>{{ account.name }}</td>
            <td>{{ account.id }}</td>
            <td>{{ account.environment }}</td>
            <td>{{ account.permission_sets|join(", ") }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
```

### Organization Report

The organization report includes:
- Overall access statistics (total users, groups, accounts, permission sets)
- Environment distribution (production vs non-production)
- Interactive charts using Plotly JavaScript library
- Detailed access patterns across the organization

Here's an example of the organization report template:

```html
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
</body>
</html>
```

When rendered with real data, the organization report provides a comprehensive overview of access patterns across the entire AWS organization, helping administrators identify potential security issues and optimize access management.

## Architecture

The system uses:
- **AWS SSO API**: For data collection through boto3
- **Amazon Neptune**: Graph database for storing and querying relationships
- **Gremlin**: Graph traversal language for querying Neptune
- **Jinja2**: HTML templating for report generation
- **Python**: Core implementation language with boto3 for AWS API integration

## Configuration

Default configuration is stored in the `neptune_utils.py` file:
- AWS Region: `us-east-1` (configurable via environment variable)
- Neptune Endpoint: Configurable via environment variable `NEPTUNE_ENDPOINT`
- Batch Size: 100 (adjustable via `BATCH_SIZE` environment variable)
- S3 Bucket: `awssso-benfelip` (configurable via `S3_BUCKET` environment variable)

Environment classification rules:
```python
ENVIRONMENTS = {
    'production': ['prod'],
    'non_production': ['dev', 'test', 'stage'],
    'other': []  # Catch-all for unclassified environments
}
```

## Troubleshooting

For connection issues:
- Verify Neptune endpoint is correct in environment variables
- Ensure proper VPC configuration
- Check IAM permissions for Neptune access
- Review error logs created during import operations

For data collection issues:
- Ensure AWS credentials have proper permissions for SSO admin and Identity Store
- Check the error log files generated during the collection process

## License

This project is licensed under the MIT License - see the LICENSE file for details.