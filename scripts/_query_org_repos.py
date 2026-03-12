#!/usr/bin/env python3
"""查询各组织下最活跃的 repos，从 ClickHouse 获取协作事件统计"""
import requests, json

orgs = ['01-ai', 'baichuan-inc', 'deepseek-ai', 'mistralai', 'QwenLM', 'THUDM', 'meta-llama']

for org in orgs:
    sql = f"""
    SELECT 
        repo_name,
        count() as total_events,
        countIf(event_type IN ('IssueCommentEvent','PullRequestEvent','PullRequestReviewEvent',
            'PullRequestReviewCommentEvent','IssuesEvent','PushEvent')) as collab_events,
        countIf(event_type = 'IssueCommentEvent') as issue_comments,
        countIf(event_type IN ('PullRequestEvent','PullRequestReviewEvent',
            'PullRequestReviewCommentEvent')) as pr_events,
        uniqExact(actor_login) as unique_actors,
        min(toStartOfMonth(created_at)) as first_month,
        max(toStartOfMonth(created_at)) as last_month,
        uniqExact(toStartOfMonth(created_at)) as active_months
    FROM github_events
    WHERE lower(repo_name) LIKE lower('{org}/%')
      AND created_at >= '2021-01-01'
    GROUP BY repo_name
    HAVING collab_events > 50
    ORDER BY collab_events DESC
    LIMIT 10
    FORMAT JSONEachRow
    """
    
    try:
        resp = requests.get(
            "https://play.clickhouse.com/",
            params={"user": "play", "query": sql},
            timeout=60
        )
        print(f"\n{'='*70}")
        print(f"  {org}/ 组织下活跃 repos:")
        print(f"{'='*70}")
        if resp.status_code == 200 and resp.text.strip():
            for line in resp.text.strip().split('\n'):
                r = json.loads(line)
                print(f"  {r['repo_name']:50s} 协作:{r['collab_events']:>7,}  PR:{r['pr_events']:>6,}  评论:{r['issue_comments']:>6,}  人:{r['unique_actors']:>5,}  月:{r['active_months']}  ({r['first_month'][:7]}~{r['last_month'][:7]})")
        else:
            print(f"  (无结果: {resp.text[:300]})")
    except Exception as e:
        print(f"  查询失败: {e}")

print("\n✅ 完成")
