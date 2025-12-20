#!/usr/bin/env python3
import configparser
import psycopg2
import sys
import os
from psycopg2 import sql

def get_config(filename='scripts/db_config.ini'):
    """从配置文件读取数据库连接信息。"""
    parser = configparser.ConfigParser()
    # 确保我们能找到配置文件，无论从哪里运行脚本
    if not os.path.exists(filename):
        # 如果在测试或从子目录运行时找不到，尝试从工作区根目录构建路径
        # 这是为了增加脚本的健壮性
        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        alt_path = os.path.join(workspace_root, filename)
        if os.path.exists(alt_path):
            filename = alt_path
        else:
            print(f"Error: Config file not found at {filename} or {alt_path}", file=sys.stderr)
            return None
            
    parser.read(filename)
    return parser

def get_connection():
    """建立并返回一个数据库连接。"""
    conn = None
    try:
        config = get_config()
        if config is None or not config.has_section('postgresql'):
             print(f"Error: 'postgresql' section not found in config.", file=sys.stderr)
             return None
        
        db_params = dict(config.items('postgresql'))
        if 'database' in db_params:
            db_params['dbname'] = db_params.pop('database')
        
        dsn = " ".join([f"{key}='{value}'" for key, value in db_params.items()])
        conn = psycopg2.connect(dsn)
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error connecting to database: {error}", file=sys.stderr)
        return None
    return conn

def setup_database(conn):
    """在数据库中创建用于存储分析结果的表（如果不存在）。"""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS parameter_analysis (
        analysis_id SERIAL PRIMARY KEY,
        parameter_id INTEGER NOT NULL REFERENCES parameter(parameter_id),
        impact_value FLOAT NOT NULL,
        stability_value FLOAT NOT NULL,
        category VARCHAR(50) NOT NULL,
        dominant_value VARCHAR(255),
        analysis_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        with conn.cursor() as cur:
            cur.execute(create_table_query)
            conn.commit()
            print("Table 'parameter_analysis' is ready.")
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error setting up database: {error}", file=sys.stderr)
        conn.rollback()

def get_parameters_to_analyze(conn, param_types=['boolean', 'integer']):
    """
    从数据库获取待分析的参数列表。
    返回一个包含参数信息的字典列表。
    """
    query = sql.SQL("""
        SELECT parameter_id, parameter_name, data_type, default_value 
        FROM parameter 
        WHERE data_type IN %s;
    """)
    
    params = []
    try:
        with conn.cursor() as cur:
            cur.execute(query, (tuple(param_types),))
            rows = cur.fetchall()
            for row in rows:
                params.append({
                    'id': row[0],
                    'name': row[1],
                    'type': row[2],
                    'default': row[3]
                })
            print(f"Fetched {len(params)} parameters to analyze.")
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error fetching parameters: {error}", file=sys.stderr)
    
    return params

def save_analysis_results(conn, results):
    """
    将分析结果批量写入数据库。
    'results' 是一个字典列表，每个字典包含一个参数的分析结果。
    """
    insert_query = """
        INSERT INTO parameter_analysis 
            (parameter_id, impact_value, stability_value, category, dominant_value)
        VALUES 
            (%s, %s, %s, %s, %s);
    """
    
    data_to_insert = [
        (
            r['parameter_id'], 
            r['impact_value'], 
            r['stability_value'], 
            r['category'], 
            r['dominant_value']
        ) for r in results
    ]
    
    if not data_to_insert:
        print("No results to save.")
        return

    try:
        with conn.cursor() as cur:
            cur.executemany(insert_query, data_to_insert)
            conn.commit()
            print(f"Successfully saved {len(data_to_insert)} analysis results to the database.")
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error saving analysis results: {error}", file=sys.stderr)
        conn.rollback()

if __name__ == '__main__':
    # 用于测试模块功能的代码
    print("Testing db_manager module...")
    connection = get_connection()
    if connection:
        setup_database(connection)
        
        # 测试获取参数
        test_params = get_parameters_to_analyze(connection)
        if test_params:
            print(f"\nSample of parameters fetched:")
            for p in test_params[:2]:
                print(p)
        
        # 测试保存结果
        if test_params:
            print("\nTesting result saving...")
            sample_results = [
                {
                    'parameter_id': test_params[0]['id'],
                    'impact_value': 0.15,
                    'stability_value': 0.9,
                    'category': 'stable',
                    'dominant_value': 'true'
                },
                {
                    'parameter_id': test_params[1]['id'],
                    'impact_value': 0.02,
                    'stability_value': 1.0,
                    'category': 'none',
                    'dominant_value': '1024'
                }
            ]
            # 清空旧数据以便测试
            with connection.cursor() as cur:
                cur.execute("TRUNCATE TABLE parameter_analysis RESTART IDENTITY;")
            save_analysis_results(connection, sample_results)

        connection.close()
        print("\nDatabase connection closed.")