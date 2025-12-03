#!/usr/bin/env python3
import re
import json
import sys
import configparser
import psycopg2

def clean_comment(comment_str):
    """
    Extracts and cleans the content of C-style concatenated string literals.
    e.g., '"hello " "world"' -> 'hello world'
    """
    literals = re.findall(r'"((?:\\"|[^"])*)"', comment_str)
    return ' '.join(l.replace('\\n', '\n').replace('\\t', '\t').strip() for l in literals)

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

def parse_flags_and_implicit_deps(content, filepath):
    """
    Parses FLAG_... and DEFINE_... macros to extract flag information,
    including their location, and implicit dependencies.
    """
    flags = []
    implicit_dependencies = []

    # A map from V8 macro types to the database ENUM types
    type_map_to_db = {
        'BOOL': 'boolean', 'DEBUG_BOOL': 'boolean', 'MAYBE_BOOL': 'boolean',
        'BOOL_READONLY': 'boolean',
        'INT': 'integer', 'UINT': 'integer', 'UINT64': 'integer',
        'SIZE_T': 'integer', 'FLOAT': 'integer', 'UINT_READONLY': 'integer',
        'STRING': 'string'
    }

    # --- Handler for 3-argument macros ---
    pattern_3_args = re.compile(
        r'^\s*DEFINE_(?P<type>BOOL|INT|UINT|UINT64|FLOAT|SIZE_T|STRING|DEBUG_BOOL|BOOL_READONLY|UINT_READONLY)\s*\('
        r'\s*(?P<name>\w+)\s*,'
        r'\s*(?P<default>.*?)\s*,'
        r'\s*(?P<comment>(?:"(?:\\"|[^"])*"\s*)+)'
        r'\s*\)', re.DOTALL | re.MULTILINE
    )
    for match in pattern_3_args.finditer(content):
        d = match.groupdict()
        line_num = content.count('\n', 0, match.start()) + 1
        flags.append({
            'name': d['name'],
            'type': type_map_to_db.get(d['type'], 'string'),
            'default': d['default'].strip(),
            'description': clean_comment(d['comment']),
            'location': f"{filepath}:{line_num}"
        })

    # --- Handler for 2-argument macros ---
    pattern_2_args = re.compile(
        r'^\s*DEFINE_(?P<type>MAYBE_BOOL)\s*\('
        r'\s*(?P<name>\w+)\s*,'
        r'\s*(?P<comment>(?:"(?:\\"|[^"])*"\s*)+)'
        r'\s*\)', re.DOTALL | re.MULTILINE
    )
    for match in pattern_2_args.finditer(content):
        d = match.groupdict()
        line_num = content.count('\n', 0, match.start()) + 1
        flags.append({
            'name': d['name'],
            'type': type_map_to_db.get(d['type'], 'boolean'),
            'default': 'std::nullopt',
            'description': clean_comment(d['comment']),
            'location': f"{filepath}:{line_num}"
        })

    # --- Handler for experimental features ---
    pattern_experimental = re.compile(
        r'^\s*DEFINE_EXPERIMENTAL_FEATURE\s*\('
        r'\s*(?P<name>\w+)\s*,'
        r'\s*(?P<comment>(?:"(?:\\"|[^"])*"\s*)+)'
        r'\s*\)', re.DOTALL | re.MULTILINE
    )
    for match in pattern_experimental.finditer(content):
        d = match.groupdict()
        line_num = content.count('\n', 0, match.start()) + 1
        flags.append({
            'name': d['name'], 'type': 'boolean', 'default': 'false',
            'description': clean_comment(d['comment']) + ' (experimental)',
            'location': f"{filepath}:{line_num}"
        })
        implicit_dependencies.append({
            'type': 'implication', 'cond': d['name'], 'then': 'experimental', 'value': 'true'
        })

    # --- Handler for test-only flags ---
    pattern_test_only = re.compile(
        r'^\s*DEFINE_TEST_ONLY_FLAG\s*\('
        r'\s*(?P<name>\w+)\s*,'
        r'\s*(?P<comment>(?:"(?:\\"|[^"])*"\s*)+)'
        r'\s*\)', re.DOTALL | re.MULTILINE
    )
    for match in pattern_test_only.finditer(content):
        d = match.groupdict()
        line_num = content.count('\n', 0, match.start()) + 1
        flags.append({
            'name': d['name'], 'type': 'boolean', 'default': 'false',
            'description': clean_comment(d['comment']) + ' (test-only / unsafe)',
            'location': f"{filepath}:{line_num}"
        })
        implicit_dependencies.append({
            'type': 'implication', 'cond': d['name'], 'then': 'test_only_unsafe', 'value': 'true'
        })

    return flags, implicit_dependencies

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
            for key, value in dep.items():
                dep[key] = value.strip().replace('!', '')
            dependencies.append(dep)
            
    return dependencies

def get_config(filename='config.ini'):
    """Read configuration from a file."""
    parser = configparser.ConfigParser()
    parser.read(filename)
    return parser

def write_to_db(flags, dependencies):
    """Connects to the PostgreSQL database and writes the parsed data."""
    conn = None
    try:
        config = get_config()
        db_params = dict(config.items('postgresql'))
        if 'database' in db_params:
            db_params['dbname'] = db_params.pop('database')
        dsn = " ".join([f"{key}='{value}'" for key, value in db_params.items()])
        print('Connecting to the PostgreSQL database...')
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        print('Clearing old data...')
        cur.execute("TRUNCATE TABLE parameter, parameter_relationships RESTART IDENTITY;")

        print('Inserting parameters...')
        # Explicitly name the columns to ensure data goes into the right place.
        flag_insert_query = """
            INSERT INTO parameter (parameter_name, data_type, default_value, description, location)
            VALUES (%s, %s, %s, %s, %s) RETURNING parameter_id, parameter_name;
        """
        flag_data = [(f['name'], f['type'], f['default'], f['description'], f['location']) for f in flags]
        
        flag_name_to_id = {}
        for record in flag_data:
            cur.execute(flag_insert_query, record)
            result = cur.fetchone()
            if result:
                id, name = result
                flag_name_to_id[name] = id
        
        print(f'Inserted {len(flag_name_to_id)} parameters.')

        print('Inserting relationships...')
        # Explicitly name the columns here as well.
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
    config = get_config()
    filepath = config.get('files', 'source_file', fallback='src/flags/flag-definitions.h')
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File not found at '{filepath}'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    clean_content = remove_preprocessor_defs(content)
    flags, implicit_deps = parse_flags_and_implicit_deps(clean_content, filepath)
    explicit_deps = parse_explicit_dependencies(clean_content)
    dependencies = implicit_deps + explicit_deps

    print(f"Successfully parsed {len(flags)} flags and {len(dependencies)} dependencies.")
    
    write_to_db(flags, dependencies)

if __name__ == "__main__":
    main()