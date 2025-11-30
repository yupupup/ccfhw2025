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

def parse_flags(content):
    """Parses FLAG_... and DEFINE_... macros to extract flag information."""
    flags = []
    
    pattern_3_args = re.compile(
        r'DEFINE_(?P<type>BOOL|INT|UINT|UINT64|FLOAT|SIZE_T|STRING|DEBUG_BOOL)\s*\('
        r'\s*(?P<name>\w+)\s*,'
        r'\s*(?P<default>.*?)\s*,'
        r'\s*(?P<comment>(?:"(?:\\"|[^"])*"\s*)+)'
        r'\s*\)', re.DOTALL
    )
    
    pattern_2_args = re.compile(
        r'DEFINE_(?P<type>MAYBE_BOOL)\s*\('
        r'\s*(?P<name>\w+)\s*,'
        r'\s*(?P<comment>(?:"(?:\\"|[^"])*"\s*)+)'
        r'\s*\)', re.DOTALL
    )

    pattern_experimental = re.compile(
        r'DEFINE_EXPERIMENTAL_FEATURE\s*\('
        r'\s*(?P<name>\w+)\s*,'
        r'\s*(?P<comment>(?:"(?:\\"|[^"])*"\s*)+)'
        r'\s*\)', re.DOTALL
    )

    type_map = {
        'BOOL': 'bool', 'DEBUG_BOOL': 'bool',
        'INT': 'int', 'UINT': 'unsigned int', 'UINT64': 'uint64_t',
        'FLOAT': 'double', 'SIZE_T': 'size_t',
        'STRING': 'const char*', 'MAYBE_BOOL': 'std::optional<bool>'
    }

    for match in pattern_3_args.finditer(content):
        d = match.groupdict()
        flags.append({
            'name': d['name'],
            'type': type_map.get(d['type'], d['type']),
            'default': d['default'].strip(),
            'description': clean_comment(d['comment'])
        })
        
    for match in pattern_2_args.finditer(content):
        d = match.groupdict()
        flags.append({
            'name': d['name'],
            'type': type_map.get(d['type'], d['type']),
            'default': 'std::nullopt',
            'description': clean_comment(d['comment'])
        })

    for match in pattern_experimental.finditer(content):
        d = match.groupdict()
        flags.append({
            'name': d['name'],
            'type': 'bool',
            'default': 'false',
            'description': clean_comment(d['comment']) + ' (experimental)'
        })

    return flags

def parse_dependencies(content):
    """Parses DEFINE_..._IMPLICATION macros to extract dependencies."""
    dependencies = []
    
    patterns = {
        "implication": r"DEFINE_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,)]+?)\)",
        "neg_implication": r"DEFINE_NEG_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,)]+?)\)",
        "value_implication": r"DEFINE_VALUE_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,]+?),\s*(?P<value>[^,)]+?)\)",
        "neg_value_implication": r"DEFINE_NEG_VALUE_IMPLICATION\((?P<when>[^,]+?),\s*(?P<then>[^,]+?),\s*(?P<value>[^,)]+?)\)",
        "neg_neg_implication": r"DEFINE_NEG_NEG_IMPLICATION\((?P<when>[^,]+?),\s*(?P<then>[^,)]+?)\)",
        "weak_implication": r"DEFINE_WEAK_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,)]+?)\)",
        "weak_value_implication": r"DEFINE_WEAK_VALUE_IMPLICATION\((?P<cond>[^,]+?),\s*(?P<then>[^,]+?),\s*(?P<value>[^,)]+?)\)",
        "disable_flag_implication": r"DEFINE_DISABLE_FLAG_IMPLICATION\((?P<whenflag>[^,]+?),\s*(?P<thenflag>[^,)]+?)\)",
    }
    
    for dep_type, pattern_str in patterns.items():
        pattern = re.compile(pattern_str, re.DOTALL)
        for match in pattern.finditer(content):
            dep = match.groupdict()
            dep['type'] = dep_type
            for key, value in dep.items():
                dep[key] = value.strip().replace('!', '')
            dependencies.append(dep)
            
    return dependencies

def get_db_config(filename='config.ini', section='postgresql'):
    """Read database configuration from a file."""
    parser = configparser.ConfigParser()
    parser.read(filename)
    db = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            db[param[0]] = param[1]
    else:
        raise Exception(f'Section {section} not found in the {filename} file.')
    return db

def write_to_db(flags, dependencies):
    """Connects to the PostgreSQL database and writes the parsed data."""
    conn = None
    try:
        params = get_db_config()
        print('Connecting to the PostgreSQL database...')
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        print('Clearing old data...')
        cur.execute("TRUNCATE TABLE parameter, parameter_relationships RESTART IDENTITY;")

        print('Inserting parameters...')
        flag_insert_query = """
            INSERT INTO parameter (parameter_name, data_type, default_value, description)
            VALUES (%s, %s, %s, %s) RETURNING parameter_id, parameter_name;
        """
        flag_data = [(f['name'], f['type'], f['default'], f['description']) for f in flags]
        
        # Use a dictionary to map flag names to their new IDs
        cur.executemany(flag_insert_query, flag_data)
        inserted_flags = cur.fetchall()
        flag_name_to_id = {name: id for id, name in inserted_flags}
        
        print(f'Inserted {len(inserted_flags)} parameters.')

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
    filepath = 'src/flags/flag-definitions.h'
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
    flags = parse_flags(clean_content)
    dependencies = parse_dependencies(clean_content)

    print(f"Successfully parsed {len(flags)} flags and {len(dependencies)} dependencies.")
    
    write_to_db(flags, dependencies)

if __name__ == "__main__":
    main()