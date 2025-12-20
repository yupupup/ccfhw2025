#!/usr/bin/env python3
import sys
import os
import math
from psycopg2 import sql

# Add the current directory to sys.path to ensure we can import db_manager if running from same dir
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    import db_manager
except ImportError:
    # Try importing as if we are running from project root
    try:
        from scripts.utils import db_manager
    except ImportError:
         print("Error: Could not import db_manager. Make sure you are running from project root or scripts directory.", file=sys.stderr)
         sys.exit(1)

def get_parameters(conn):
    """
    Fetch parameter definitions from the database.
    Query fields: parameter_name, data_type, default_value, min_value, max_value, value_step
    """
    query = """
        SELECT parameter_name, data_type, default_value, min_value, max_value, value_step
        FROM parameter
        WHERE data_type IN ('integer', 'boolean')
    """
    
    params = []
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            for row in rows:
                params.append({
                    'name': row[0],
                    'type': row[1],
                    'default': row[2],
                    'min': row[3],
                    'max': row[4],
                    'step': row[5]
                })
    except Exception as e:
        print(f"Error fetching parameters: {e}", file=sys.stderr)
        return None
        
    return params

def calculate_range(default_val, min_val, max_val, step_val, param_type):
    """
    Calculate min, max, and step based on available values and default strategy.
    
    Strategy:
    - Min missing: default * 0.5 (or 0 if default is 0). For boolean default is 0/1.
    - Max missing: default * 2.0 (or 1 if default is 0). For boolean default is 0/1.
    - Step missing: (max - min) / 10. For boolean step is 1.
    """
    
    # Boolean override
    if param_type == 'boolean':
        # Booleans are strictly 0 or 1
        return 0, 1, 1

    # helper to convert string to number safely
    def to_int(v):
        if v is None: return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0

    # Convert inputs
    p_def = to_int(default_val)
    p_min = to_int(min_val)
    p_max = to_int(max_val)
    p_step = to_int(step_val)

    # Handle default if strictly None
    if p_def is None: p_def = 0

    # 1. Fill Min/Max
    if p_min is None:
        p_min = math.floor(p_def * 0.5)
        # Ensure min <= default.
        # However if default is 0, min becomes 0.
        if p_min > p_def: p_min = p_def

    if p_max is None:
        if p_def == 0:
            p_max = 100 # arbitrary expansion if 0
        else:
            p_max = math.ceil(p_def * 2.0)
    
    # Ensure consistency
    if p_min > p_max:
        p_min, p_max = p_max, p_min
        
    # 2. Fill Step
    if p_step is None:
        rng = p_max - p_min
        if rng == 0:
            p_step = 1
        else:
            # Target ~10 steps
            calc_step = rng / 10.0
            p_step = max(1, round(calc_step))

    return p_min, p_max, p_step

def generate_code_for_param(param):
    """
    Generate the line of python code for a single parameter.
    """
    name = param['name']
    p_type = param['type'].lower()
    
    # We treat boolean as integer 0-1
    if p_type == 'boolean':
        p_min, p_max, p_step = 0, 1, 1
    else:
        p_min, p_max, p_step = calculate_range(param['default'], param['min'], param['max'], param['step'], 'integer')
    
    use_switch = False
    if p_step > 1 and p_type != 'boolean':
        use_switch = True
    
    if use_switch:
        # Generate list of values
        values = []
        curr = p_min
        
        # Safety limit
        max_options = 1000 
        
        while curr <= p_max:
            values.append(int(curr))
            curr += p_step
            if len(values) > max_options:
                print(f"# Warning: Parameter {name} has > {max_options} options. Reverting to Range.", file=sys.stderr)
                use_switch = False
                break
    
    if use_switch:
        # SwitchParameter('name', [options])
        return f"manipulator.add_parameter(SwitchParameter('{name}', {values}))"
    else:
        # IntegerParameter(name, min, max)
        return f"manipulator.add_parameter(IntegerParameter('{name}', {p_min}, {p_max}))"

def main():
    conn = db_manager.get_connection()
    if not conn:
        print("Failed to connect to database.")
        sys.exit(1)
    
    params = get_parameters(conn)
    conn.close()
    
    if not params:
        print("No parameters found or error query.")
        return
        
    print("# Auto-generated parameter definitions")
    print("manipulator = ConfigurationManipulator()")
    
    for p in params:
        code_line = generate_code_for_param(p)
        print(code_line)
    
    print("return manipulator")

if __name__ == "__main__":
    main()
