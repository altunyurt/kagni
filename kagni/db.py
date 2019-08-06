import pickle
import pathlib
from functools import wraps

try:
    import apsw as sqlite
except ImportError:
    import sqlite3 as sqlite


class DB:
    def __init__(self, file_name, backup_path=None):
        self.file_name = file_name
        # a directory path . backups will have the same name + date
        self.backup_path = backup_path
        self.table_name = "data"

    def connector(f):
        @wraps(f)
        def wrapper(inst, *args, **kwargs):
            with sqlite.connect(inst.file_name) as conn:
                conn.row_factory = sqlite.Row
                kwargs.update({"conn": conn})
                with conn:
                    return f(inst, *args, **kwargs)

        return wrapper

    @connector
    def create_table(self, conn=None):
        return conn.execute(
            f"create table if not exists {self.table_name} (key text not null, value blob not null);"
        )

    @connector
    def backup_table(self, conn=None):

        try:
            return conn.execute(
                f"alter table {self.table_name} rename to {self.table_name}_bak"
            )
        except sqlite.OperationalError:
            pass

    @connector
    def insert_rows(self, data, conn=None):
        for key, val in data.items():
            conn.execute(
                f"insert into {self.table_name} values(?, ?)", [key, pickle.dumps(val)]
            )

        return

    def dump(self, data):
        """ needs to be run as a task """

        self.backup_table()
        self.create_table()
        self.insert_rows(data)
        return

    @connector
    def load(self, conn=None):

        with conn.execute("select key, value from data") as cursor:
            for (key, val) in cur.fetchall():
                print(key, pickle.loads(val))
