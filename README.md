# kagni
Kagni is a Redis-like data store

### Details

#### Asyncio / Trio

Kagni has two async implementations for now, based on asyncio+uvloop and trio. 

#### Sqlite db backend 

All data lives in memory and an internal async job will be periodically dumping the memory into SQLite database.
Already a battle tested and proven data storage technology, SQLite will be more than enough to handle the storage 
easing the backup process as well. 


