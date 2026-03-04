"""将 CSV 数据导入 Kuzu，包含建表与 COPY。

用法（在仓库根目录运行）：
    python scripts/kuzu_import_from_csv.py \
        --csv-dir output/kuzu_csv \
        --db-path output/kuzu_db \
        --overwrite

说明：
- 仅依赖 csv 导出结果，不修改数据；缺失值保持为空。
- 采用“单关系表 + edge_type”设计。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import kuzu


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 CSV 导入 Kuzu 数据库")
    parser.add_argument("--csv-dir", type=Path, default=Path("output/kuzu_csv"), help="CSV 所在目录")
    parser.add_argument("--db-path", type=Path, default=Path("output/kuzu_db.kuzu"), help="Kuzu 数据库文件路径（不要指向目录）")
    parser.add_argument("--overwrite", action="store_true", help="如已存在则删除后重建")
    return parser.parse_args()


def recreate_db_if_needed(db_path: Path, overwrite: bool) -> None:
    if db_path.exists():
        if not overwrite:
            raise FileExistsError(f"数据库文件已存在，请使用 --overwrite 或先删除: {db_path}")
        if db_path.is_dir():
            shutil.rmtree(db_path)
        else:
            db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)


def create_schema(conn: kuzu.Connection) -> None:
    # 节点表
    conn.execute(
        """
        CREATE NODE TABLE IF NOT EXISTS Actor(
            id STRING,
            actor_id STRING,
            login STRING,
            event_count STRING,
            event_types STRING,
            PRIMARY KEY (id)
        );
        """
    )
    conn.execute(
        """
        CREATE NODE TABLE IF NOT EXISTS Repo(
            id STRING,
            repo_id STRING,
            name STRING,
            event_count STRING,
            event_types STRING,
            PRIMARY KEY (id)
        );
        """
    )
    conn.execute(
        """
        CREATE NODE TABLE IF NOT EXISTS Discussion(
            id STRING,
            node_type STRING,
            repo_id STRING,
            number STRING,
            title STRING,
            state STRING,
            creator_id STRING,
            creator_login STRING,
            comment_count STRING,
            participants_count STRING,
            created_at STRING,
            PRIMARY KEY (id)
        );
        """
    )

    # 关系表（单表 + edge_type + id）
    conn.execute(
        """
        CREATE REL TABLE IF NOT EXISTS ActorToActor(
            FROM Actor TO Actor,
            id STRING,
            edge_type STRING,
            created_at STRING,
            comment_body STRING,
            total_events STRING,
            repo_name STRING,
            month STRING
        );
        """
    )
    conn.execute(
        """
        CREATE REL TABLE IF NOT EXISTS ActorToDiscussion(
            FROM Actor TO Discussion,
            id STRING,
            edge_type STRING,
            created_at STRING,
            comment_body STRING,
            total_events STRING,
            repo_name STRING,
            month STRING
        );
        """
    )
    conn.execute(
        """
        CREATE REL TABLE IF NOT EXISTS ActorToRepo(
            FROM Actor TO Repo,
            id STRING,
            edge_type STRING,
            created_at STRING,
            comment_body STRING,
            total_events STRING,
            repo_name STRING,
            month STRING
        );
        """
    )


def copy_all(conn: kuzu.Connection, csv_dir: Path) -> None:
    # 针对不同表设置 COPY 选项：Actor/Repo 无多行文本，可并行；其他含多行时关闭并行
    copy_options = {
        "Actor": "(HEADER=TRUE, PARALLEL=TRUE)",
        "Repo": "(HEADER=TRUE, PARALLEL=TRUE)",
        "Discussion": "(HEADER=TRUE, PARALLEL=FALSE)",
        "ActorToActor": "(HEADER=TRUE, PARALLEL=FALSE)",
        "ActorToDiscussion": "(HEADER=TRUE, PARALLEL=FALSE)",
        "ActorToRepo": "(HEADER=TRUE, PARALLEL=FALSE)",
    }

    def copy(table: str, filename: str) -> None:
        csv_path = csv_dir / filename
        if not csv_path.exists():
            raise FileNotFoundError(f"缺少 CSV 文件: {csv_path}")
        opts = copy_options.get(table, "(HEADER=TRUE, PARALLEL=FALSE)")
        print(f"[COPY] {table} <- {csv_path} {opts}", flush=True)
        conn.execute(f'COPY {table} FROM "{csv_path.as_posix()}" {opts};')
        print(f"[DONE] {table}", flush=True)

    copy("Actor", "actors.csv")
    copy("Repo", "repos.csv")
    copy("Discussion", "discussions.csv")
    copy("ActorToActor", "actor_actor_edges.csv")
    copy("ActorToDiscussion", "actor_discussion_edges.csv")
    copy("ActorToRepo", "actor_repo_edges.csv")


def main() -> None:
    args = parse_args()

    # 如目标路径已存在且是目录，但未指定 --overwrite，则直接报错提示清理
    if args.db_path.exists() and args.db_path.is_dir() and not args.overwrite:
        print(
            f"目标路径已是目录，请先删除或使用 --overwrite: {args.db_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    recreate_db_if_needed(args.db_path, args.overwrite)

    db = kuzu.Database(str(args.db_path))
    conn = kuzu.Connection(db)

    create_schema(conn)
    copy_all(conn, args.csv_dir)

    print("导入完成：")

    # 节点表计数
    for table in ["Actor", "Repo", "Discussion"]:
        res = conn.execute(f"MATCH (n:{table}) RETURN count(n);")
        print(f"  {table}: {res.get_next()}")

    # 关系表计数
    rel_counts = {
        "ActorToActor": "MATCH ()-[r:ActorToActor]->() RETURN count(r);",
        "ActorToDiscussion": "MATCH ()-[r:ActorToDiscussion]->() RETURN count(r);",
        "ActorToRepo": "MATCH ()-[r:ActorToRepo]->() RETURN count(r);",
    }
    for rel, query in rel_counts.items():
        res = conn.execute(query)
        print(f"  {rel}: {res.get_next()}")


if __name__ == "__main__":
    main()
