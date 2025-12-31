#!/usr/bin/env python3
import re
import sys
import os
import psycopg2

# Add the script directory to sys.path to allow importing utils
# Assuming this script is run from the project root (ccfhw2025) or its own directory
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from scripts.utils import db_manager
except ImportError:
    # Fallback if running from scripts/parameter-extractor/
    sys.path.append(os.path.abspath(os.path.join(current_dir, '..')))
    from utils import db_manager

def remove_preprocessor_defs(text):
    """
    Removes multi-line and single-line #define blocks from the text.
    """
    lines = text.splitlines()
    output_lines = []
    in_define = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#define"):
            in_define = stripped.endswith('\\')
        elif in_define:
            in_define = stripped.endswith('\\')
        else:
            output_lines.append(line)
    return "\n".join(output_lines)

def parse_flags_txt(filepath):
    """
    Parses flags.txt to extract flag information.
    Expected format:
      --flag-name (Description)
            type: type_name  default: default_value
    """
    flags = []
    
    # Map from flags.txt types to DB types
    type_map_to_db = {
        'bool': 'boolean',
        'maybe_bool': 'boolean',
        'int': 'integer',
        'uint': 'integer',
        'uint64': 'integer',
        'float': 'float',
        'size_t': 'integer',
        'string': 'string'
    }

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: File not found at '{filepath}'", file=sys.stderr)
        return []

    current_flag = None
    
    # Regex for the flag name line: "  --name (Description)"
    # Note: Description might contain parentheses, so we grab everything inside the outer ones?
    # Or just greedy match.
    flag_pattern = re.compile(r'^\s*--(?P<name>[\w-]+)\s*\((?P<description>.*)\)\s*$')
    
    # Regex for the type/default line: "        type: bool  default: --no-name"
    type_pattern = re.compile(r'^\s*type:\s*(?P<type>\w+)\s+default:\s*(?P<default>.*)$')

    for i, line in enumerate(lines):
        # Check for flag name line
        flag_match = flag_pattern.match(line)
        if flag_match:
            current_flag = {
                'name': flag_match.group('name'),
                'description': flag_match.group('description'),
                'location': f"{filepath}:{i+1}"
            }
            continue

        # Check for type/default line (should follow flag name)
        if current_flag:
            type_match = type_pattern.match(line)
            if type_match:
                raw_type = type_match.group('type')
                default_val = type_match.group('default').strip()
                
                current_flag['type'] = type_map_to_db.get(raw_type, 'string')
                if raw_type in ('bool', 'maybe_bool'):
                    if default_val.startswith('--no-'):
                        current_flag['default'] = 'false'
                    elif default_val.startswith('--'):
                        current_flag['default'] = 'true'
                    else:
                        current_flag['default'] = 'false' if raw_type == 'maybe_bool' else default_val
                elif '=' in default_val:
                    current_flag['default'] = default_val.split('=', 1)[1]
                else:
                    current_flag['default'] = default_val
                
                flags.append(current_flag)
                current_flag = None

    return flags

def parse_explicit_dependencies(content):
    """Parses DEFINE_..._IMPLICATION macros to extract dependencies."""
    dependencies = []
    
    patterns = {
        "implication": (r"DEFINE_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,)]+?)\)", 'true'),
        "neg_implication": (r"DEFINE_NEG_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,)]+?)\)", 'false'),
        "value_implication": (r"DEFINE_VALUE_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,]+?),\s*(?P<value>[^,)]+?)\)", None),
        "neg_value_implication": (r"DEFINE_NEG_VALUE_IMPLICATION\((?P<when>[^,]+?),\s*(?P<then>[^,]+?),\s*(?P<value>[^,)]+?)\)", None),
        "neg_neg_implication": (r"DEFINE_NEG_NEG_IMPLICATION\((?P<when>[^,]+?),\s*(?P<then>[^,)]+?)\)", 'false'),
        "weak_implication": (r"DEFINE_WEAK_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,)]+?)\)", 'true'),
        "weak_value_implication": (r"DEFINE_WEAK_VALUE_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,]+?),\s*(?P<value>[^,)]+?)\)", None),
        "disable_flag_implication": (r"DEFINE_DISABLE_FLAG_IMPLICATION\((?P<whenflag>[^,]+?),\s*(?P<thenflag>[^,)]+?)\)", 'false'),
    }
    
    for dep_type, (pattern_str, implicit_value) in patterns.items():
        pattern = re.compile(pattern_str, re.DOTALL)
        for match in pattern.finditer(content):
            dep = match.groupdict()
            dep['type'] = dep_type
            if 'value' not in dep and implicit_value:
                dep['value'] = implicit_value
            
            # Clean up and convert underscores to hyphens for flag names
            for key, value in dep.items():
                if key in ['cond', 'then', 'when', 'whenflag', 'thenflag']:
                    # Strip whitespace, remove '!', and convert _ to -
                    clean_val = value.strip().replace('!', '').replace('_', '-')
                    dep[key] = clean_val
                else:
                    dep[key] = value.strip()
                    
            dependencies.append(dep)
            
    return dependencies

def parse_readonly_flags(content):
    """
    Parses flag-definitions.h to identify read-only flags.
    Looks for DEFINE_BOOL_READONLY, DEFINE_INT_READONLY, DEFINE_UINT_READONLY, etc.
    Returns a set of flag names (with hyphens).
    """
    readonly_flags = set()
    
    # Pattern to match DEFINE_TYPE_READONLY(name, ...)
    # We match the macro name ending in _READONLY and capture the first argument (name)
    pattern = re.compile(r'^\s*DEFINE_\w+_READONLY\s*\(\s*(?P<name>\w+)\s*,', re.MULTILINE)
    
    for match in pattern.finditer(content):
        name = match.group('name')
        # Convert underscores to hyphens to match flags.txt format
        clean_name = name.replace('_', '-')
        readonly_flags.add(clean_name)
        
    return readonly_flags

def write_to_db(flags, dependencies):
    """Connects to the PostgreSQL database and writes the parsed data."""
    conn = None
    try:
        print('Connecting to the PostgreSQL database...')
        conn = db_manager.get_connection()
        if conn is None:
            print("Failed to connect to database.")
            return

        cur = conn.cursor()

        print('Clearing old data...')
        cur.execute("TRUNCATE TABLE parameter, parameter_relationships RESTART IDENTITY;")

        print('Inserting parameters...')
        # Explicitly name the columns to ensure data goes into the right place.
        flag_insert_query = """
            INSERT INTO parameter (parameter_name, data_type, default_value, description, location, readonly)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING parameter_id, parameter_name;
        """
        flag_data = [(f['name'], f['type'], f['default'], f['description'], f['location'], f.get('readonly', False)) for f in flags]
        
        flag_name_to_id = {}
        for record in flag_data:
            cur.execute(flag_insert_query, record)
            result = cur.fetchone()
            if result:
                id, name = result
                flag_name_to_id[name] = id
        
        print(f'Inserted {len(flag_name_to_id)} parameters.')

        print('Inserting relationships...')
        rel_insert_query = """
            INSERT INTO parameter_relationships (source_parameter_id, target_parameter_id, relationship_type, value)
            VALUES (%s, %s, %s, %s);
        """
        rel_data = []
        for dep in dependencies:
            source_name = dep.get('cond') or dep.get('when') or dep.get('whenflag')
            target_name = dep.get('then') or dep.get('thenflag')
            
            source_id = flag_name_to_id.get(source_name)
            target_id = flag_name_to_id.get(target_name)
            
            if source_id and target_id:
                rel_data.append((
                    source_id,
                    target_id,
                    dep['type'],
                    dep.get('value')
                ))
            else:
                # Optional: Log missing flags if needed
                # print(f"Warning: Could not find IDs for dependency: {source_name} -> {target_name}")
                pass

        cur.executemany(rel_insert_query, rel_data)
        print(f'Inserted {len(rel_data)} relationships.')

        conn.commit()
        cur.close()
        print('Data successfully written to the database.')

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error: {error}", file=sys.stderr)
    finally:
        if conn is not None:
            conn.close()
            print('Database connection closed.')

def main():
    """Main function to read file, parse, and print results."""
    # Default paths
    flags_txt_path = 'scripts/parameter-extractor/flags.txt'
    definitions_h_path = 'src/flags/flag-definitions.h'
    
    # Allow overriding via arguments or config if needed, but for now hardcoding as per request context
    # or trying to find them relative to project root
    
    if not os.path.exists(flags_txt_path):
        # Try finding it relative to this script
        flags_txt_path = os.path.join(os.path.dirname(__file__), 'flags.txt')

    # For flag-definitions.h, we might need to look in the v8 workspace
    # The user mentioned "v8/src/flags/flag-definitions.h"
    # We can try to find it or expect it to be passed/configured.
    # Let's try a few common locations or use the one from the user's open file if possible.
    # Since I can't access user's open file path programmatically easily here, I'll check a likely path
    # or assume the user runs this from a place where it can find it.
    # However, the previous script had a fallback 'src/flags/flag-definitions.h'.
    # I will try to use the absolute path from the user's workspace if I can guess it, 
    # but better to rely on the user running it with the right CWD or providing the path.
    # I'll stick to the previous default but also check the absolute path I saw earlier.
    
    v8_path = '/home/dby/chromium/v8/v8/src/flags/flag-definitions.h'
    if os.path.exists(v8_path):
        definitions_h_path = v8_path
    elif not os.path.exists(definitions_h_path):
        print(f"Warning: {definitions_h_path} not found. Dependency parsing might fail.", file=sys.stderr)

    # print(f"Parsing flags from: {flags_txt_path}")
    # flags = parse_flags_txt(flags_txt_path)
    
    # dependencies = []
    readonly_flags = set()
    
    if os.path.exists(definitions_h_path):
        print(f"Parsing dependencies and read-only flags from: {definitions_h_path}")
        try:
            with open(definitions_h_path, 'r', encoding='utf-8') as f:
                content = f.read()
            clean_content = remove_preprocessor_defs(content)
            # dependencies = parse_explicit_dependencies(clean_content)
            readonly_flags = parse_readonly_flags(clean_content)
            
        except Exception as e:
            print(f"Error reading {definitions_h_path}: {e}", file=sys.stderr)
    
    # Update flags with readonly status
    # readonly_count = 0
    # for flag in flags:
    #     if flag['name'] in readonly_flags:
    #         flag['readonly'] = True
    #         readonly_count += 1
    #     else:
    #         flag['readonly'] = False
            
    # print(f"Successfully parsed {len(flags)} flags ({readonly_count} read-only) and {len(dependencies)} dependencies.")
    
    try:
        conn = db_manager.get_connection()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error: {error}", file=sys.stderr)
        exit()

    for flag in readonly_flags:
        flag_update_query = """
            UPDATE parameter SET readonly = True WHERE parameter_name = %s;
        """
        cur = conn.cursor()
        cur.execute(flag_update_query, (flag,))
        conn.commit()
    
    cur.close()
        
    # write_to_db(flags, dependencies)

if __name__ == "__main__":
    main()