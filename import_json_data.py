def load_edges_batch(g, edges, batch_size=100):
    """Load edges with proper relationship handling"""
    print("\nLoading edges...")
    successful = 0
    failed = 0
    
    for i in range(0, len(edges), batch_size):
        batch = edges[i:i + batch_size]
        for edge in batch:
            try:
                label = edge['label']
                
                if label == 'MEMBER_OF':
                    # User to Group relationship
                    g.V().has('User', 'userId', edge['from'].replace('USER_', ''))\
                        .addE(label)\
                        .to(__.V().has('Group', 'groupId', edge['to'].replace('GROUP_', '')))\
                        .property('timestamp', edge['properties']['timestamp'])\
                        .next()
                
                elif label == 'HAS_ACCESS_TO':
                    # Group to Account relationship
                    g.V().has('Group', 'groupId', edge['from'].replace('GROUP_', ''))\
                        .addE(label)\
                        .to(__.V().has('Account', 'accountId', edge['to'].replace('ACCOUNT_', '')))\
                        .property('timestamp', edge['properties']['timestamp'])\
                        .property('permissionSetArn', edge['properties']['permissionSetArn'])\
                        .next()
                
                elif label == 'HAS_PERMISSION':
                    # Group to PermissionSet relationship
                    g.V().has('Group', 'groupId', edge['from'].replace('GROUP_', ''))\
                        .addE(label)\
                        .to(__.V().has('PermissionSet', 'arn', edge['to'].replace('PERMISSION_SET_', '')))\
                        .property('timestamp', edge['properties']['timestamp'])\
                        .next()
                
                successful += 1
                if successful % 100 == 0:
                    print(f"Successfully loaded {successful} edges")
                    
            except Exception as e:
                failed += 1
                if failed < 5:
                    print(f"\nError in edge ({label}):")
                    print(json.dumps(edge, indent=2))
                    print(f"Error: {str(e)}")
        
        print(f"Processed batch ending at {i + len(batch)}")
    
    # Print statistics by edge type
    print("\nEdge loading summary:")
    edge_counts = g.E().groupCount().by(T.label).next()
    for label, count in edge_counts.items():
        print(f"{label}: {count}")
    
    print(f"\nTotal successful: {successful}")
    print(f"Total failed: {failed}")
    
    return successful, failed

# Run the loading process
try:
    print("Connecting to Neptune...")
    g, conn = connect_to_neptune()
    
    print("\nLoading edges...")
    vertices, edges = load_json_from_s3()
    edge_load_success, edge_load_failed = load_edges_batch(g, edges)
    
    # Verify the relationships
    print("\nVerifying relationships...")
    
    # Check MEMBER_OF relationships
    member_of = g.E().hasLabel('MEMBER_OF').count().next()
    print(f"MEMBER_OF edges: {member_of}")
    
    # Check HAS_ACCESS_TO relationships
    has_access = g.E().hasLabel('HAS_ACCESS_TO').count().next()
    print(f"HAS_ACCESS_TO edges: {has_access}")
    
    # Check HAS_PERMISSION relationships
    has_permission = g.E().hasLabel('HAS_PERMISSION').count().next()
    print(f"HAS_PERMISSION edges: {has_permission}")
    
    # Sample complete path
    print("\nSample access path:")
    path = g.V().hasLabel('User')\
        .out('MEMBER_OF')\
        .out('HAS_ACCESS_TO')\
        .path()\
        .by('userName')\
        .by('groupName')\
        .by('accountName')\
        .limit(1)\
        .next()
    
    print(f"User -> Group -> Account path: {path}")
    
finally:
    if conn:
        conn.close()
        print("\nConnection closed")
