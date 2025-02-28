from gremlin_python.structure.graph import Graph
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection

# Gremlin server URL (update this with your actual connection details)
GREMLIN_SERVER_URL = "wss://serverless-kmap.cluster-cyenjim10cpi.us-east-1.neptune.amazonaws.com:8182/gremlin"

# Connect to Gremlin Server
graph = Graph()
conn = DriverRemoteConnection(GREMLIN_SERVER_URL, 'g')
g = graph.traversal().withRemote(conn)

# Define Group and Account IDs
group_id = "GROUP_90676c734f-05f36968-7695-450b-9"
account_id = "ACCOUNT_388598290966"

# Step 1: Check if Group and Account exist
group_exists = g.V().has("groupId", group_id).count().next() > 0
account_exists = g.V().has("accountId", account_id).count().next() > 0

print(f"Group Exists: {group_exists}, Account Exists: {account_exists}")

# Step 2: Create missing vertices if needed
if not group_exists:
    group_vertex = g.addV("Group").property("groupId", group_id).property("groupName", "Example Group").next()
    print(f"Created Group: {group_vertex}")

if not account_exists:
    account_vertex = g.addV("Account").property("accountId", account_id).property("accountName", "Example Account").next()
    print(f"Created Account: {account_vertex}")

# Step 3: Check if Edge Exists
edge_exists = g.V().has("groupId", group_id).outE("ASSIGNED_TO").where(__.inV().has("accountId", account_id)).count().next() > 0
print(f"Edge Exists: {edge_exists}")

# Step 4: Create Edge if it doesn't exist
if not edge_exists:
    try:
        g.V().has("groupId", group_id).addE("ASSIGNED_TO").to(g.V().has("accountId", account_id)).next()
        print("Successfully added edge ASSIGNED_TO")
    except Exception as e:
        print(f"Error adding edge: {e}")

# Step 5: Verify relationships
group_edges = g.V().has("groupId", group_id).outE().valueMap(True).toList()
account_edges = g.V().has("accountId", account_id).inE().valueMap(True).toList()

print(f"Group Edges: {group_edges}")
print(f"Account Edges: {account_edges}")

# Close connection
conn.close()