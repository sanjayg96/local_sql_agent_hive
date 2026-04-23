import sqlite3

def execute_sql(db_path: str, sql_query: str):
    """Executes SQL against a local SQLite database and returns results or errors."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        conn.close()
        return {"success": True, "data": rows, "columns": columns, "error": None}
    except Exception as e:
        return {"success": False, "data": None, "columns": None, "error": str(e)}