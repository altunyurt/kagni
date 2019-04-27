# kagni
Kagni is a Redis-like data store. 

Kagni - Kağnı in Turkish is a form of tumbrel, pulled by bullocks used for carrying stuff in rural areas. It is slow as hell, but gets things done. Naming is due to its ability to store and load on / off stuff and also its sturdiness. 

Performance will get better hopefully :) 

### Details

#### Asyncio / Trio

Kagni has two async implementations for now, based on Asyncio + Uvloop and Trio. For now Asyncio + Uvloop implementation gives the best performance, but personally I like the Trio implementation better, for not getting in the way much.

#### Sqlite db backend 

All data lives in memory and an internal async job will be periodically dumping the memory into SQLite database.
Already a battle tested and proven data storage technology, SQLite will be more than enough to handle the storage 
easing the backup process as well. 


#### Roaring bitmaps

Bitmaps in Redis start to hog memory in time as the data grows. Roaring Bitmaps is a better solution for the same requirements.
The implementation is compatible with utilities / libraries such as [Bitmapist](https://github.com/Doist/bitmapist) 

### Redis Compatibility

Kagni speaks [RESP(REdis Serialization Protocol)](https://redis.io/topics/protocol) fluently. 
I've implemented the following commands up to now: 

- Ping
- Command
- Get
- Set
- Getset
- Mget
- Mset
- Del
- Expire
- Ttl
- Keys
- Incr
- Incrby
- Getrange
- Setbit
- Getbit 
- Bitop
- Bitcount
- Bitpos
- Flushdb
- Flushall
