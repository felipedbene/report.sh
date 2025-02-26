# AWS SSO Access Analysis and Graph Database Tool

This project provides a comprehensive solution for analyzing AWS Single Sign-On (SSO) access patterns using Amazon Neptune graph database. It enables organizations to identify potential security risks, analyze cross-environment access, and generate detailed access reports for compliance and security auditing.

The tool collects data from AWS SSO, AWS Identity Store, and AWS Organizations, storing it in a Neptune graph database for advanced analysis. Key features include toxic combination detection (users with both production and non-production access), administrative access analysis, and detailed HTML report generation with access patterns visualization. The solution helps security teams identify potential security risks and maintain compliance with access control policies.

## Repository Structure
```
.
├── devfile.yaml              # Development environment configuration for container-based development
├── g_collect.py             # Collects AWS SSO, Identity Store, and Organizations data
├── generate_report.py       # Generates HTML reports for user and organization-wide access analysis
├── import_json_data.py      # Imports collected data into Neptune graph database
├── neptune_connection.py    # Handles Neptune database connection and query execution
├── neptune_utils.py         # Utility functions for Neptune operations
├── neptune.yaml            # CloudFormation template for Neptune infrastructure
├── requirements.txt        # Python package dependencies
└── toxic.py               # Analyzes toxic access combinations and security risks
```

## Usage Instructions
### Prerequisites
- AWS account with permissions to:
  - AWS SSO
  - AWS Identity Store
  - AWS Organizations
  - Amazon Neptune
- Python 3.6 or higher
- AWS CLI configured with appropriate credentials
- Amazon Neptune cluster (can be deployed using provided neptune.yaml)

### Installation
```bash
# Clone the repository
git clone <repository-url>
cd <repository-name>

# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials
aws configure
```

### Quick Start
1. Deploy Neptune infrastructure:
```bash
aws cloudformation deploy \
  --template-file neptune.yaml \
  --stack-name sso-analysis \
  --parameter-overrides \
    Environment=dev \
    DBClusterIdentifier=sso-analysis
```

2. Collect AWS SSO data:
```bash
python g_collect.py --region us-east-1
```

3. Import data into Neptune:
```bash
python import_json_data.py \
  --neptune-endpoint <your-neptune-endpoint> \
  --region us-east-1
```

4. Generate access analysis report:
```bash
python generate_report.py \
  --neptune-endpoint <your-neptune-endpoint> \
  --output-dir reports
```

### More Detailed Examples
1. Analyze toxic combinations:
```python
python toxic.py \
  --neptune-endpoint <your-neptune-endpoint> \
  --region us-east-1 \
  --output-dir reports \
  --toxic
```

2. Generate organization-wide report:
```python
python generate_report.py \
  --neptune-endpoint <your-neptune-endpoint> \
  --org-report \
  --output-dir reports
```

### Troubleshooting
1. Neptune Connection Issues
- Error: "Failed to connect to Neptune endpoint"
  - Verify VPC security group allows inbound traffic on port 8182
  - Check IAM authentication is properly configured
  - Ensure Neptune endpoint is correct and accessible
```bash
aws neptune describe-db-clusters --query 'DBClusters[*].Endpoint'
```

2. Data Import Failures
- Error: "S3 access denied"
  - Verify IAM roles have proper S3 permissions
  - Check S3 bucket exists and is accessible
```bash
aws s3 ls s3://<bucket-name>/graph_data/
```

3. Report Generation Issues
- Error: "No data found in Neptune database"
  - Verify data collection and import completed successfully
  - Check Neptune query logs:
```bash
aws logs get-log-events \
  --log-group-name /aws/neptune/<cluster-id>/slowquery \
  --log-stream-name <stream-name>
```

## Data Flow
The tool follows a three-stage data processing pipeline: collection, storage, and analysis.

```ascii
AWS Services         Collection           Storage              Analysis
+------------+      +---------+          +---------+          +---------+
|   AWS SSO  |----->|         |          |         |          |         |
+------------+      |         |          |         |    ------>| Report  |
|  Identity  |----->|g_collect|--JSON--->| Neptune |   /      |Generator|
|   Store    |      |   .py   |          |   DB    |--/       |         |
+------------+      |         |          |         |--\       |         |
|Organizations|---->|         |          |         |   \      | Toxic   |
+------------+      +---------+          +---------+    ------>|Analysis |
                                                              +---------+
```

Component interactions:
1. g_collect.py queries AWS services using boto3 SDK
2. Data is transformed into vertex and edge JSON format
3. import_json_data.py loads JSON data into Neptune using Gremlin
4. Neptune stores data in graph format optimized for traversal
5. Analysis tools query Neptune using Gremlin traversals
6. Reports are generated using HTML templates
7. Security findings are output in structured format

## Infrastructure

![Infrastructure diagram](./docs/infra.svg)
### Neptune Database
- **DBCluster**: Neptune cluster with encryption and IAM authentication
  - Type: AWS::Neptune::DBCluster
  - Identifier: Specified by DBClusterIdentifier parameter
  - Features: Backup retention, maintenance windows, CloudWatch logging

- **DBInstances**:
  - Primary Instance (Type: AWS::Neptune::DBInstance)
    - Class: Configurable (default: db.r6g.large)
    - AZ: Specified by AvailabilityZone1
  - Replica Instance (Production only)
    - Class: Matches primary
    - AZ: Specified by AvailabilityZone2

- **Security**:
  - SecurityGroup: Allows inbound on Neptune port from VPC CIDR
  - KMS encryption enabled
  - IAM authentication required

- **Networking**:
  - DBSubnetGroup: Spans two private subnets
  - VPC integration with security group controls

## Deployment
### Prerequisites
- VPC with two private subnets
- KMS key for encryption
- IAM roles and permissions configured

### Deployment Steps
1. Deploy Neptune infrastructure:
```bash
aws cloudformation deploy \
  --template-file neptune.yaml \
  --stack-name sso-analysis \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    Environment=prod \
    DBClusterIdentifier=sso-analysis \
    DBInstanceClass=db.r6g.xlarge
```

2. Configure environment:
```bash
export NEPTUNE_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name sso-analysis \
  --query 'Stacks[0].Outputs[?OutputKey==`ClusterEndpoint`].OutputValue' \
  --output text)
```

3. Initialize database:
```bash
python import_json_data.py --clean --neptune-endpoint $NEPTUNE_ENDPOINT
```