import aiosqlite
import pickle


class DB:
    def __init__(self, path):
        self.path = path

    async def create_table(self):
        async with aiosqlite.connect(self.path) as _db:
            await _db.execute(
                """create table if not exists data 
                              (key text not null, value blob not null);"""
            )
            await _db.commit()
        return

    async def dump(self, data):
        """ needs to be run as a task """
        async with aiosqlite.connect(self.path) as _db:
            for key, val in data.items():
                await _db.execute("""insert into data values(?,?)""", 
                            [key, pickle.dumps(val)])

            await _db.commit()

    async def load(self):
        async with aiosqlite.connect(self.path) as _db:
            _db.row_factory = aiosqlite.Row

            async with db.execute('key, value from data') as cursor:
                print(row)
                # for (key, val) in cur.fetchall():
                #     print(key, pickle.loads(val))
        return 
