# AWS SSO Access Analysis and Graph Database Tool

A comprehensive tool for analyzing AWS Single Sign-On (SSO) access patterns using Amazon Neptune graph database. This solution helps security teams identify potential security risks, toxic access combinations, and provides detailed access reports for AWS SSO environments.

The tool collects data from AWS SSO, AWS Identity Store, and AWS Organizations to build a graph representation of user access patterns. It analyzes cross-environment access, administrative privileges, and extensive account access patterns to identify potential security risks. The solution generates detailed HTML reports for both individual users and organization-wide access patterns, making it easier to maintain security compliance and perform access reviews.

## Repository Structure
```
.
├── devfile.yaml              # Development environment configuration for container-based development
├── docs/                     # Documentation files including infrastructure diagrams
├── g_collect.py             # Collects AWS SSO data and builds graph representation
├── generate_report.py       # Generates HTML reports for user and organization access analysis
├── import_json_data.py      # Imports graph data from S3 into Neptune database
├── neptune_connection.py    # Neptune database connection utilities
├── neptune_utils.py         # Shared utilities for Neptune operations
├── neptune.yaml            # CloudFormation template for Neptune infrastructure
├── requirements.txt        # Python package dependencies
└── toxic.py               # Analyzes toxic access combinations and security risks
```

## Usage Instructions
### Prerequisites
- AWS Account with SSO enabled
- Python 3.6 or higher
- AWS CLI configured with appropriate permissions
- Amazon Neptune cluster (can be deployed using provided CloudFormation template)
- IAM permissions for:
  - AWS SSO
  - AWS Organizations
  - Amazon Neptune
  - Amazon S3

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

3. Generate access analysis report:
```bash
python generate_report.py --email user@example.com
```

### More Detailed Examples
1. Analyze toxic combinations:
```python
python toxic.py \
  --neptune-endpoint your-neptune-endpoint \
  --region us-east-1 \
  --output-dir reports \
  --toxic
```

2. Generate organization-wide report:
```python
python generate_report.py \
  --org-report \
  --output-dir reports
```

### Troubleshooting
1. Neptune Connection Issues
   - Error: "Failed to connect to Neptune endpoint"
   - Solution: 
     ```bash
     # Verify security group settings
     aws ec2 describe-security-groups --group-ids <security-group-id>
     
     # Test network connectivity
     nc -zv <neptune-endpoint> 8182
     ```

2. Data Collection Errors
   - Error: "Access denied when calling AWS SSO service"
   - Solution: Verify IAM permissions and run:
     ```bash
     aws sts get-caller-identity
     aws sso-admin list-instances
     ```

3. Performance Optimization
   - Monitor Neptune metrics in CloudWatch
   - Use batch loading for large datasets
   - Enable Neptune slow query logs:
     ```bash
     aws neptune modify-db-cluster \
       --db-cluster-identifier <cluster-id> \
       --enable-cloudwatch-logs-exports '["slowquery"]'
     ```

## Data Flow
The tool processes AWS SSO access data through a graph-based analysis pipeline, transforming organizational hierarchy and permissions into actionable security insights.

```ascii
AWS Services         Graph Processing           Analysis & Reporting
[SSO Service]    →   [Neptune DB]         →    [Access Reports]
[Identity Store] →   [Graph Vertices]     →    [Toxic Combinations]
[Organizations]  →   [Graph Edges]        →    [Security Insights]
```

Component interactions:
1. AWS service APIs provide raw access data
2. Data collector transforms data into graph structure
3. Neptune database stores and indexes the graph
4. Analysis modules traverse the graph for patterns
5. Report generator creates HTML output
6. Security checks identify risky combinations
7. Batch processing handles large-scale updates

## Infrastructure

![Infrastructure diagram](./docs/infra.svg)
### Neptune Database
- DBCluster (AWS::Neptune::DBCluster)
  - Identifier: db-neptune-1
  - Engine Version: 1.4.3.0
  - IAM Authentication: Enabled
  - Encryption: KMS-based
  - Logging: Audit and slow query logs enabled

### Network Resources
- SecurityGroup (AWS::EC2::SecurityGroup)
  - Purpose: Controls access to Neptune cluster
  - Inbound rules for port 8182
- DBSubnetGroup (AWS::Neptune::DBSubnetGroup)
  - Purpose: Defines network placement
  - Uses private subnets for security

### Database Instances
- PrimaryDBInstance (AWS::Neptune::DBInstance)
  - Class: Configurable (default: db.r6g.large)
  - High availability in primary AZ
- ReplicaDBInstance (AWS::Neptune::DBInstance)
  - Only deployed in production
  - Provides read scaling and failover