# 测试 Cypher 查询
import kuzu

# db = kuzu.Database(r"output\\kuzu_db")
db = kuzu.Database(r"output/kuzu_db")
conn = kuzu.Connection(db)

# 多条查询
queries = [
    """
    MATCH (a:Actor)-[e:ActorToDiscussion]->(d:Discussion)
    RETURN a.id, e.edge_type,e.repo_name,e.created_at, d.title
    LIMIT 5;
    """
]

for query in queries:
    print(f"\n执行: {query[:50]}...")
    result = conn.execute(query)
    while result.has_next():
        print(result.get_next())

res = conn.execute("CALL show_tables() RETURN *;")
while res.has_next():
    print(res.get_next())