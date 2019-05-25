import aiosqlite
import pickle
import pathlib
from functools import wraps


class DB:
    def __init__(self, file_name, backup_path=None):
        self.file_name = file_name
        # a directory path . backups will have the same name + date
        self.backup_path = backup_path
        self.table_name = "data"

    def connector(f):
        @wraps(f)
        async def wrapper(inst, *args, **kwargs):
            async with aiosqlite.connect(inst.file_name) as _db:
                _db.row_factory = aiosqlite.Row
                kwargs.update({"_db": _db})
                print("kwa", kwargs, *args)
                return await f(inst, *args, **kwargs)

        return wrapper

    @connector
    async def create_table(self, _db=None):
        await _db.execute(
            f"create table if not exists {self.table_name} (key text not null, value blob not null);"
        )
        return await _db.commit()

    # async def backup(self):
    #     if self.backup_path:
    #         path = pathlib.Path(self.backup_path)
    #         if not path.exists():
    #             path.mkdir()

    #         path.joinpath('')

    @connector
    async def backup_table(self, _db=None):

        try:
            await _db.execute(
                f"alter table {self.table_name} rename to {self.table_name}_bak"
            )
        except aiosqlite.OperationalError:
            pass

    @connector
    async def insert_rows(self, data, _db=None):
        for key, val in data.items():
            await _db.execute(
                f"insert into {self.table_name} values(?, ?)", [key, pickle.dumps(val)]
            )

        return await _db.commit()

    async def dump(self, data):
        """ needs to be run as a task """

        await self.backup_table()
        await self.create_table()
        await self.insert_rows(data)

    async def load(self):
        async with aiosqlite.connect(self.file_name) as _db:
            _db.row_factory = aiosqlite.Row

            async with db.execute("key, value from data") as cursor:
                print(row)
                # for (key, val) in cur.fetchall():
                #     print(key, pickle.loads(val))
        return
