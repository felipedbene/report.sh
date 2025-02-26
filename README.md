# Neptune Connection Troubleshooting

## Issue

The script was encountering a HTTP 403 Forbidden error when trying to connect to Neptune database. This typically happens when:

1. IAM authentication is required but not enabled in the connection code
2. The IAM credentials don't have the proper permissions to access Neptune
3. The necessary libraries for IAM authentication are not installed

## Solution

The solution involves:

1. Installing the necessary dependencies:
   
   First, activate the Neptune virtual environment (if using one):
   ```
   source ~/report.sh/neptune/bin/activate
   ```
   
   Or use the Python interpreter from the virtual environment directly:
   ```
   ~/report.sh/neptune/bin/pip install -r requirements.txt
   ```
   
   If not using a virtual environment:
   ```
   python3 -m pip install -r requirements.txt
   ```

2. Enabling IAM authentication in the connection code
3. Using the neptune-python-utils library for proper IAM authentication with Neptune
4. Adding a fallback mechanism if neptune-python-utils is not available

## Required IAM Permissions

Make sure the EC2 instance or user running the script has an IAM role/policy with the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "neptune-db:*"
            ],
            "Resource": [
                "arn:aws:neptune-db:region:account-id:cluster-resource-id/*"
            ]
        }
    ]
}
```

Replace `region`, `account-id`, and `cluster-resource-id` with the appropriate values for your Neptune database.