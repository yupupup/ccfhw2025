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
