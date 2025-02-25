#!/usr/bin/env python3

import boto3
import json
import datetime
import os
from dataclasses import dataclass
from typing import List, Dict
from neptune_utils import debug_log

@dataclass
class Vertex:
    id: str
    label: str
    properties: Dict

@dataclass
class Edge:
    from_id: str
    to_id: str
    label: str
    properties: Dict

class SSOGraphCollector:
    def __init__(self):
        self.sso_admin = boto3.client('sso-admin')
        self.identitystore = boto3.client('identitystore')
        self.organizations = boto3.client('organizations')
        self.vertices = []
        self.edges = []
        
        # Get SSO instance details
        instances = self.sso_admin.list_instances()
        self.instance_arn = instances['Instances'][0]['InstanceArn']
        self.identity_store_id = instances['Instances'][0]['IdentityStoreId']

    def collect_data(self):
        self._collect_users()
        self._collect_groups()
        self._collect_group_memberships()
        self._collect_accounts()
        self._collect_permission_sets()
        self._collect_assignments()
        
        return {
            'vertices': self.vertices,
            'edges': self.edges
        }

    def _collect_users(self):
        debug_log("Collecting Users...")
        paginator = self.identitystore.get_paginator('list_users')
        for page in paginator.paginate(IdentityStoreId=self.identity_store_id):
            for user in page['Users']:
                self.vertices.append(Vertex(
                    id=f"USER_{user['UserId']}",
                    label="User",
                    properties={
                        'userId': user['UserId'],
                        'userName': user.get('UserName', ''),
                        'email': user.get('Emails', [{}])[0].get('Value', ''),
                        'type': 'USER'
                    }
                ))

    def _collect_groups(self):
        debug_log("Collecting Groups...")
        paginator = self.identitystore.get_paginator('list_groups')
        for page in paginator.paginate(IdentityStoreId=self.identity_store_id):
            for group in page['Groups']:
                self.vertices.append(Vertex(
                    id=f"GROUP_{group['GroupId']}",
                    label="Group",
                    properties={
                        'groupId': group['GroupId'],
                        'groupName': group.get('DisplayName', ''),
                        'type': 'GROUP'
                    }
                ))

    def _collect_group_memberships(self):
        debug_log("Collecting Group Memberships...")
        for group in [v for v in self.vertices if v.label == "Group"]:
            paginator = self.identitystore.get_paginator('list_group_memberships')
            for page in paginator.paginate(
                IdentityStoreId=self.identity_store_id,
                GroupId=group.properties['groupId']
            ):
                for membership in page['GroupMemberships']:
                    self.edges.append(Edge(
                        from_id=f"USER_{membership['MemberId']['UserId']}",
                        to_id=f"GROUP_{group.properties['groupId']}",
                        label="MEMBER_OF",
                        properties={
                            'timestamp': datetime.datetime.now().isoformat()
                        }
                    ))

    def _collect_accounts(self):
        debug_log("Collecting AWS Accounts...")
        paginator = self.organizations.get_paginator('list_accounts')
        for page in paginator.paginate():
            for account in page['Accounts']:
                self.vertices.append(Vertex(
                    id=f"ACCOUNT_{account['Id']}",
                    label="Account",
                    properties={
                        'accountId': account['Id'],
                        'accountName': account['Name'],
                        'email': account['Email'],
                        'type': 'ACCOUNT'
                    }
                ))

    def _collect_permission_sets(self):
        debug_log("Collecting Permission Sets...")
        paginator = self.sso_admin.get_paginator('list_permission_sets')
        for page in paginator.paginate(InstanceArn=self.instance_arn):
            for pset_arn in page['PermissionSets']:
                pset = self.sso_admin.describe_permission_set(
                    InstanceArn=self.instance_arn,
                    PermissionSetArn=pset_arn
                )['PermissionSet']
                
                self.vertices.append(Vertex(
                    id=f"PERMISSION_SET_{pset_arn}",
                    label="PermissionSet",
                    properties={
                        'arn': pset_arn,
                        'name': pset['Name'],
                        'description': pset.get('Description', ''),
                        'type': 'PERMISSION_SET'
                    }
                ))

    def _collect_assignments(self):
        debug_log("Collecting Assignments...")
        for pset in [v for v in self.vertices if v.label == "PermissionSet"]:
            accounts_paginator = self.sso_admin.get_paginator('list_accounts_for_provisioned_permission_set')
            for accounts_page in accounts_paginator.paginate(
                InstanceArn=self.instance_arn,
                PermissionSetArn=pset.properties['arn']
            ):
                for account_id in accounts_page.get('AccountIds', []):
                    assignments_paginator = self.sso_admin.get_paginator('list_account_assignments')
                    for assignments_page in assignments_paginator.paginate(
                        InstanceArn=self.instance_arn,
                        AccountId=account_id,
                        PermissionSetArn=pset.properties['arn']
                    ):
                        for assignment in assignments_page['AccountAssignments']:
                            principal_id = f"{assignment['PrincipalType']}_{assignment['PrincipalId']}"
                            
                            # Create HAS_PERMISSION edge
                            self.edges.append(Edge(
                                from_id=principal_id,
                                to_id=f"PERMISSION_SET_{pset.properties['arn']}",
                                label="HAS_PERMISSION",
                                properties={
                                    'timestamp': datetime.datetime.now().isoformat()
                                }
                            ))
                            
                            # Create IN_ACCOUNT edge
                            self.edges.append(Edge(
                                from_id=principal_id,
                                to_id=f"ACCOUNT_{account_id}",
                                label="HAS_ACCESS_TO",
                                properties={
                                    'permissionSetArn': pset.properties['arn'],
                                    'timestamp': datetime.datetime.now().isoformat()
                                }
                            ))

from neptune_utils import GRAPH_DATA_DIR

def save_graph_data(data, directory):
    graph_dir = os.path.join(directory, GRAPH_DATA_DIR)
    os.makedirs(graph_dir, exist_ok=True)

    # Save vertices
    with open(os.path.join(graph_dir, "vertices.json"), 'w') as f:
        json.dump([{
            'id': v.id,
            'label': v.label,
            'properties': v.properties
        } for v in data['vertices']], f, indent=2)

    # Save edges
    with open(os.path.join(graph_dir, "edges.json"), 'w') as f:
        json.dump([{
            'from': e.from_id,
            'to': e.to_id,
            'label': e.label,
            'properties': e.properties
        } for e in data['edges']], f, indent=2)

def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"iam_data_dump_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    collector = SSOGraphCollector()
    graph_data = collector.collect_data()
    save_graph_data(graph_data, output_dir)

    logger.info(f"Graph data collected and saved to: {output_dir}")

if __name__ == "__main__":
    main()
