#!/usr/bin/env python3
import csv
import os
import sys

# --- Path Setup ---
# Add the 'scripts' directory to the path to allow sibling imports
current_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
# --- End Path Setup ---

# Now we can import the shared db_manager
try:
    from utils import db_manager
except ImportError as e:
    print(f"Error: Failed to import db_manager from utils.", file=sys.stderr)
    print(f"Please ensure 'scripts/utils/db_manager.py' exists.", file=sys.stderr)
    print(f"Details: {e}", file=sys.stderr)
    sys.exit(1)

def read_categories_from_csv(csv_path):
    """
    Reads the voted categories from the MERGE_RESULT.csv file.
    Returns a dictionary mapping parameter_name to category.
    """
    categories = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                flag = row.get('flag')
                voted_category = row.get('voted_category')
                if flag and voted_category:
                    categories[flag.strip()] = voted_category.strip()
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error reading CSV file: {e}", file=sys.stderr)
        return None
    
    print(f"Read {len(categories)} categories from {os.path.basename(csv_path)}.")
    return categories

def update_database_categories(conn, categories):
    """
    Updates the 'category' column in the 'parameter' table.
    """
    if not categories:
        print("No categories to update.")
        return

    updated_count = 0
    skipped_count = 0
    
    # Note: Using parameter_name to match the 'flag' from the CSV
    update_query = "UPDATE parameter SET category = %s WHERE parameter_name = %s;"

    try:
        with conn.cursor() as cur:
            for name, category in categories.items():
                # Convert kebab-case from CSV to snake_case for DB
                # db_param_name = name.replace('-', '_')
                cur.execute(update_query, (category, name))
                if cur.rowcount > 0:
                    updated_count += 1
                else:
                    skipped_count += 1
                    # This warning is useful for debugging mismatches
                    print(f"  - WARNING: Parameter '{name}' (from CSV: '{name}') not found in the database. Skipped.")
            conn.commit()
            print(f"\nSuccessfully updated {updated_count} parameter categories in the database.")
            if skipped_count > 0:
                print(f"Skipped {skipped_count} parameters that were not found in the 'parameter' table.")

    except Exception as e:
        print(f"Database update failed: {e}", file=sys.stderr)
        conn.rollback()

if __name__ == '__main__':
    # The CSV file is in the same directory as this script.
    csv_file_path = os.path.join(current_dir, 'MERGE_RESULT.csv')
    
    print("Starting category update process...")
    
    # 1. Read data from CSV
    category_data = read_categories_from_csv(csv_file_path)
    
    if category_data:
        # 2. Get database connection.
        # db_manager.py will look for 'scripts/parameter-analyzer/config.ini' relative to the workspace root.
        # This works because we run the script from the root.
        print("Connecting to the database...")
        connection = db_manager.get_connection()
        
        if connection:
            # 3. Update database
            update_database_categories(connection, category_data)
            
            # 4. Close connection
            connection.close()
            print("\nDatabase connection closed.")
        else:
            print("Failed to connect to the database. Aborting.", file=sys.stderr)
    
    print("\nProcess finished.")