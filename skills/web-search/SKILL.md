---
name: web-search
description: >-
  Use when the user needs information from public websites rather than only the local workspace:
  searching the web, checking official docs, release notes, project homepages, public API docs,
  or recent public pages. Prefer web_search for discovery and http_fetch for direct known URLs.
version: "1.0.0"
triggers:
  - web search
  - search web
  - 搜网页
  - 网页搜索
  - 联网搜索
  - 上网查
  - 官网
  - release notes
  - public docs
priority: 4
allowed_tools:
  - http_fetch
  - file_read
  - command_lookup
required_tools:
  - http_fetch
---

# Web search

## When to use

- The user asks for information that is likely on a **public website** rather than in the workspace.
- The task needs **official documentation**, **homepage content**, **release notes**, or another public page.
- The user explicitly asks to **search the web**, **look up** a website, or **check online docs**.

## Prefer `http_fetch`

- Use `web_search` when the user wants discovery: search results, official docs, homepages, recent public pages.
- Use `http_fetch` for direct HTTP reads instead of `shell_exec` with `curl` or `wget` when the target URL is already known.
- If the exact page is unknown, start with `web_search`, then follow with one or more direct `http_fetch` calls of the best candidate pages.

## Recommended workflow

1. Identify the likely target:
   official site, official docs, release page, GitHub repo, package page, or a public search result page.
2. Run `web_search` to get candidate result URLs.
3. Fetch the top result pages directly with `http_fetch`.
4. Summarize only after reading those pages.
5. Prefer **official** or primary sources over mirrors, summaries, or random blogs.

## URL strategy

- If the user already gave a domain or URL, start there.
- If the task mentions a product or library but not the exact page, prefer:
  official docs, official homepage, GitHub releases/changelog, package registry page.
- Search-result pages are only a waypoint; the final answer should be based on the target pages you fetched.

## Environment constraints

- `http_fetch` only supports `http://` and `https://`.
- Hosts may be restricted by `UNI_AGENT_HTTP_FETCH_ALLOWED_HOSTS`.
- Private-network and loopback targets are blocked unless the runtime explicitly allows them.
- If a host is blocked, say that the runtime policy needs to be widened instead of pretending the page does not exist.

## Do not use

- Do not use this skill for purely local codebase search; use workspace tools instead.
- Do not rely on a single search-result snippet when you can fetch the destination page itself.
- Do not use `shell_exec` only to perform simple HTTP GETs that `http_fetch` can already handle.

## Output expectations

- Cite the fetched page URLs in the answer when relevant.
- Distinguish clearly between:
  fetched facts,
  inferred conclusions,
  and cases where network policy blocked access.
