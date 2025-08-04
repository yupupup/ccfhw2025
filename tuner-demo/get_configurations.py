import sqlite3
import zlib
import pickle
import json

def parse_opentuner_blob(blob_data):
    try:
        # 尝试zlib解压
        decompressed = zlib.decompress(blob_data)
        
        # 尝试pickle解析
        try:
            return pickle.loads(decompressed)
        except:
            # 尝试JSON解析
            try:
                return json.loads(decompressed.decode('utf-8'))
            except:
                return f"Unknown format (hex): {decompressed.hex()}"
    except zlib.error:
        return "Failed to decompress (raw hex): " + blob_data.hex()

# 连接数据库
conn = sqlite3.connect('./opentuner.db/DESKTOP-TBLVIRD.db')
cursor = conn.cursor()

# 查询数据
cursor.execute("""
    SELECT r.id, r.time, c.data 
    FROM result r 
    JOIN configuration c ON r.configuration_id = c.id
    ORDER BY r.time ASC
    LIMIT 10
""")

# 解析并打印
for row in cursor.fetchall():
    run_id, time, blob_data = row
    params = parse_opentuner_blob(blob_data)
    print(f"Run {run_id} | Time: {time:.1f} | Params: {params}")

conn.close()