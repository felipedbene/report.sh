# Code Analysis Report

## Duplicated Functions
1. `get_neptune_auth_headers()` is duplicated in:
   - build_report.py (lines 26-30)
   - import_json_data.py (lines 33-37)
   
## Code Structure
The codebase appears to be organized into three main Python files:
1. g_collect.py - Contains classes and methods for collecting SSO graph data
2. import_json_data.py - Handles importing JSON data into Neptune database
3. build_report.py - Generates security analysis reports

### Key Components:
- Graph data collection (g_collect.py)
  - Vertex and Edge classes
  - SSOGraphCollector class with various collection methods
- Data import (import_json_data.py)
  - S3 data loading
  - Neptune database connection and batch operations
- Report generation (build_report.py)
  - Multiple analysis functions
  - Excel and HTML report generation

## Potential Improvements
1. Create a shared utilities module to eliminate duplicated functions
   - Move `get_neptune_auth_headers()` to this module
2. Consider standardizing Neptune database connection logic
3. Implement consistent error handling across files

## Missing Variables/Constants
1. Some hardcoded values could be moved to configuration:
   - Environment names ['dev', 'test', 'stage'] in build_report.py
   - Batch sizes (e.g., batch_size=100 in import_json_data.py)
   - File paths and S3 bucket names