"""Fetch GitHub profile stats via the GraphQL API (stdlib only)."""
import json, urllib.request
from datetime import date, datetime, timedelta, timezone

API = "https://api.github.com/graphql"
CAL = "contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }"

def gql(query: str, token: str, **variables) -> dict:
    req = urllib.request.Request(
        API, data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {body['errors']}")
    return body["data"]

def days_of(cal: dict) -> dict[str, int]:
    return {d["date"]: d["contributionCount"] for w in cal["weeks"] for d in w["contributionDays"]}

def fetch_stats(user: str, token: str) -> dict:
    q = f"""query($login: String!) {{ user(login: $login) {{ createdAt
      followers {{ totalCount }} following {{ totalCount }}
      contributionsCollection {{ {CAL} }} }} }}"""
    u = gql(q, token, login=user)["user"]
    if u is None:
        raise RuntimeError(f"GitHub user not found: {user}")
    repos, stars, langs, cursor = 0, 0, {}, None
    rq = """query($login: String!, $after: String) { user(login: $login) {
      repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
        totalCount pageInfo { hasNextPage endCursor }
        nodes { stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } } } } } } }"""
    while True:
        r = gql(rq, token, login=user, after=cursor)["user"]["repositories"]
        repos = r["totalCount"]
        for n in r["nodes"]:
            stars += n["stargazerCount"]
            for e in n["languages"]["edges"]:
                langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
        if not r["pageInfo"]["hasNextPage"]:
            break
        cursor = r["pageInfo"]["endCursor"]
    # All-time contributions: one aliased contributionsCollection per calendar year.
    now = datetime.now(timezone.utc)
    years = range(int(u["createdAt"][:4]), now.year + 1)
    parts = " ".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", '
        f'to: "{now.isoformat() if y == now.year else f"{y}-12-31T23:59:59Z"}") {{ {CAL} }}'
        for y in years)
    yd = gql(f"query($login: String!) {{ user(login: $login) {{ {parts} }} }}", token, login=user)["user"]
    contributions, all_days = 0, {}
    for y in years:
        contributions += yd[f"y{y}"]["contributionCalendar"]["totalContributions"]
        all_days.update(days_of(yd[f"y{y}"]["contributionCalendar"]))

    recent = days_of(u["contributionsCollection"]["contributionCalendar"])
    all_days.update(recent)  # most up-to-date view of the last year
    best = run = 0
    for d in sorted(all_days):
        run = run + 1 if all_days[d] > 0 else 0; best = max(best, run)
    day = date.fromisoformat(max(all_days))
    if all_days.get(day.isoformat(), 0) == 0:
        day -= timedelta(days=1)
    streak = 0
    while all_days.get(day.isoformat(), 0) > 0:
        streak, day = streak + 1, day - timedelta(days=1)

    return {
        "repos": repos, "stars": stars,
        "followers": u["followers"]["totalCount"], "following": u["following"]["totalCount"],
        "contributions": contributions,
        "active_days": sum(1 for c in recent.values() if c > 0),
        "streak": streak, "best_streak": best, "created_at": u["createdAt"],
        "top_languages": [k for k, _ in sorted(langs.items(), key=lambda kv: -kv[1])[:4]],
    }

if __name__ == "__main__":
    import os, subprocess
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    s = fetch_stats("ayushmk7", tok)
    print(s)
    assert all(isinstance(s[k], int) for k in ("repos", "stars", "followers", "following",
               "contributions", "active_days", "streak", "best_streak"))
    assert isinstance(s["created_at"], str)
    assert isinstance(s["top_languages"], list) and all(isinstance(x, str) for x in s["top_languages"])
