#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;34m'
NC='\033[0m'

# Configuration
NEPTUNE_ENDPOINT="primarydbinstance-taijvcthrfqz.cyenjim10cpi.us-east-1.neptune.amazonaws.com"
AWS_REGION="us-east-1"
CLUSTER_ID=$(echo $NEPTUNE_ENDPOINT | cut -d. -f1)

# Get instance metadata using IMDSv2
get_metadata() {
    TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
    if [ -n "$TOKEN" ]; then
        curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/$1
    fi
}

# Get VPC ID
VPC_ID=$(get_metadata "network/interfaces/macs/$(get_metadata mac)/vpc-id")
if [ -z "$VPC_ID" ]; then
    echo -e "${RED}Failed to get VPC ID from metadata${NC}"
    # Try to get VPC ID from the instance
    VPC_ID=$(aws ec2 describe-instances \
        --filters "Name=instance-id,Values=$(get_metadata instance-id)" \
        --query 'Reservations[0].Instances[0].VpcId' \
        --output text)
fi

print_header() {
    echo -e "\n${YELLOW}=== $1 ===${NC}"
}

check_neptune_cluster() {
    print_header "1. Checking Neptune Cluster Configuration"
    
    echo "Getting cluster details..."
    CLUSTER_INFO=$(aws neptune describe-db-clusters \
        --region $AWS_REGION \
        --query 'DBClusters[?contains(Endpoint,`'$NEPTUNE_ENDPOINT'`)]' \
        --output json)
    
    if [ -n "$CLUSTER_INFO" ] && [ "$CLUSTER_INFO" != "null" ] && [ "$CLUSTER_INFO" != "[]" ]; then
        echo "$CLUSTER_INFO" | jq -r '.[0] | {
            "Cluster ID": .DBClusterIdentifier,
            "Status": .Status,
            "IAM Auth": .IAMDatabaseAuthenticationEnabled,
            "VPC": .VpcSecurityGroups[0].VpcSecurityGroupId
        }'
        
        if [ "$(echo "$CLUSTER_INFO" | jq -r '.[0].IAMDatabaseAuthenticationEnabled')" != "true" ]; then
            echo -e "\n${RED}Action Required: Enable IAM authentication:${NC}"
            echo "aws neptune modify-db-cluster --db-cluster-identifier $CLUSTER_ID --enable-iam-database-authentication"
        fi
    else
        echo -e "${RED}Could not find Neptune cluster. Verify the endpoint is correct.${NC}"
    fi
}

check_role_permissions() {
    print_header "2. Checking IAM Role Configuration"
    
    # Get instance profile and role
    INSTANCE_PROFILE=$(get_metadata "iam/info" | jq -r '.InstanceProfileArn')
    if [ -n "$INSTANCE_PROFILE" ] && [ "$INSTANCE_PROFILE" != "null" ]; then
        ROLE_NAME=$(echo $INSTANCE_PROFILE | awk -F'/' '{print $(NF-1)}')
        echo "Instance Profile: $INSTANCE_PROFILE"
        echo "Role Name: $ROLE_NAME"
        
        if [ -n "$ROLE_NAME" ]; then
            echo -e "\nAttached Policies:"
            aws iam list-attached-role-policies --role-name $ROLE_NAME --query 'AttachedPolicies[].[PolicyName,PolicyArn]' --output table
            
            # Check for admin/power user access
            if aws iam list-attached-role-policies --role-name $ROLE_NAME | grep -qE "AdministratorAccess|PowerUserAccess"; then
                echo -e "${GREEN}Role has high-privilege access${NC}"
            else
                echo -e "${YELLOW}Checking for specific Neptune permissions...${NC}"
                aws iam simulate-role-policy \
                    --role-name $ROLE_NAME \
                    --action-names neptune-db:connect neptune-db:ReadDataViaQuery \
                    --resource-arns arn:aws:neptune-db:$AWS_REGION:$(aws sts get-caller-identity --query 'Account' --output text):$CLUSTER_ID/* \
                    --query 'EvaluationResults[].EvalDecision' \
                    --output table
            fi
        fi
    else
        echo -e "${RED}No IAM role found attached to the instance${NC}"
    fi
}

check_network_config() {
    print_header "3. Checking Network Configuration"
    
    if [ -n "$VPC_ID" ]; then
        echo "VPC ID: $VPC_ID"
        
        # Check VPC endpoint
        echo -e "\nChecking VPC endpoints..."
        if aws ec2 describe-vpc-endpoints \
            --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.neptune-db" \
            --query 'VpcEndpoints[].VpcEndpointId' --output text | grep -q "^vpce-"; then
            echo -e "${GREEN}Neptune VPC endpoint exists${NC}"
        else
            echo -e "${RED}No Neptune VPC endpoint found${NC}"
            echo "Required: Create VPC endpoint:"
            echo "aws ec2 create-vpc-endpoint --vpc-id $VPC_ID --vpc-endpoint-type Interface --service-name com.amazonaws.$AWS_REGION.neptune-db"
        fi
        
        # Check security groups
        echo -e "\nChecking security group configuration..."
        INSTANCE_SG=$(aws ec2 describe-instances \
            --filters "Name=vpc-id,Values=$VPC_ID" \
            --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' \
            --output text)
        
        if [ -n "$INSTANCE_SG" ]; then
            echo "Instance Security Group: $INSTANCE_SG"
            aws ec2 describe-security-group-rules \
                --filters "Name=group-id,Values=$INSTANCE_SG" \
                --query 'SecurityGroupRules[?FromPort==`8182`]' \
                --output table
        fi
    else
        echo -e "${RED}Could not determine VPC ID${NC}"
    fi
}

generate_policy() {
    print_header "4. Required IAM Policy"
    
    ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
    
    cat << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "neptune-db:connect",
                "neptune-db:ReadDataViaQuery",
                "neptune-db:WriteDataViaQuery",
                "neptune-db:GetEngineStatus"
            ],
            "Resource": [
                "arn:aws:neptune-db:${AWS_REGION}:${ACCOUNT_ID}:${CLUSTER_ID}/*"
            ]
        }
    ]
}
EOF
}

main() {
    echo -e "${YELLOW}Neptune Authentication Diagnostic Tool${NC}"
    
    check_neptune_cluster
    check_role_permissions
    check_network_config
    generate_policy
    
    print_header "Summary and Required Actions"
    echo "1. Neptune IAM Auth: Enable if not already enabled"
    echo "2. IAM Role: Ensure Neptune permissions are attached"
    echo "3. VPC Endpoint: Create if missing"
    echo "4. Security Groups: Verify port 8182 access"
    echo -e "\nAfter making changes, wait a few minutes and retry the connection"
}

main
