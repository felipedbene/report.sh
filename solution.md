# Neptune Connection Fix

The error message "ws_connect() got an unexpected keyword argument 'headers_supplier'" indicates a compatibility issue with the version of gremlin-python being used.

## Problem

The code was attempting to use a `headers_supplier` parameter when creating the Neptune connection, but this parameter is not supported in newer versions of the gremlin-python driver.

## Solution

I've updated the code in `neptune_connection.py` to:

1. Call `get_neptune_auth_headers()` directly to obtain the headers first
2. Pass these headers as a static `headers` parameter rather than using `headers_supplier`
3. Added a `message_serializer` parameter to ensure proper serialization

This change maintains the authentication functionality while being compatible with the current version of the gremlin-python library.

## Testing

To test this fix:

1. Run the import script again: `uv run --script import_json_data.py`
2. Verify that the Neptune connection is established without the previous error

If you need further changes to authentication, please let me know.