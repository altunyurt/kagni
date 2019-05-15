import apsw
import pickle


class DB:
    def __init__(self, path):
        self.con = apsw.Connection(path)
        cur = self.con.cursor()

        cur.execute("""create table if not exists data (key text not null, value blob not null);""")

        cur.close()

    def dump(self, data):
        ''' needs to be run as a task '''
        cur = self.con.cursor()
        for key, val in data.items():
            cur.execute("""insert into data values(?,?)""", [key, pickle.dumps(val)])

        cur.close()

    def load(self):
        cur = self.con.cursor()
        cur.execute("""select key, value from data""")
        for (key, val) in cur.fetchall():
            print(key, pickle.loads(val))

        cur.close()



