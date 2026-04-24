from uni_agent.agent.planner import HeuristicPlanner
from uni_agent.tools.registry import ToolRegistry


def test_heuristic_plan_includes_file_write() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan('write the file notes.txt with content "hello"', [], registry.list_tools())

    write_steps = [step for step in plan if step.tool == "file_write"]
    assert write_steps
    assert write_steps[0].arguments["path"] == "notes.txt"
    assert write_steps[0].arguments["content"] == "hello"


def test_heuristic_skips_read_when_write_targets_same_path() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan('write the file README.md with content "x"', [], registry.list_tools())

    assert any(step.tool == "file_write" for step in plan)
    assert all(step.tool != "file_read" for step in plan)


def test_heuristic_adds_http_fetch_for_urls() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("download https://example.com/path", [], registry.list_tools())

    fetch_steps = [step for step in plan if step.tool == "http_fetch"]
    assert fetch_steps
    assert fetch_steps[0].arguments["url"].startswith("https://example.com/path")


def test_heuristic_shortcuts_to_web_search_for_explicit_web_queries() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("请联网搜索 Python 官方文档首页", [], registry.list_tools())

    assert len(plan) == 1
    assert plan[0].tool == "web_search"
    assert "Python" in plan[0].arguments["query"]


def test_heuristic_shortcuts_hot_news_queries_to_web_search() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("查看今天的热点新闻", [], registry.list_tools())

    assert len(plan) == 1
    assert plan[0].tool == "web_search"
    assert "热点新闻" in plan[0].arguments["query"]


def test_heuristic_shortcuts_cn_ai_hot_news_queries_to_curated_sources() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    prior_context = """
    [r1-step-1] web_search failed: Search the public web for: '查看今天的 AI 热点新闻'.
      output:
      web_search failed: DuckDuckGo returned a bot-detection challenge.
      error: invalid_arguments: web_search failed: DuckDuckGo returned a bot-detection challenge.
    """

    plan = planner.create_plan("查看今天的 AI 热点新闻", [], registry.list_tools(), prior_context=prior_context)

    assert [step.tool for step in plan] == ["http_fetch", "http_fetch"]
    assert plan[0].arguments["url"] == "https://www.aibase.com/zh/daily"
    assert plan[1].arguments["url"] == "https://news.softunis.com/ai"


def test_heuristic_follows_up_web_search_with_ranked_news_sources() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()
    prior_context = """
    [r1-step-1] web_search completed: Search the public web for: '今天的新闻热点'.
      output:
      {
        "query": "今天的新闻热点",
        "results": [
          {"title": "Example generic home", "url": "https://example.com/", "snippet": "Official homepage"},
          {"title": "国内新闻滚动新闻-中国新闻网", "url": "https://www.chinanews.com.cn/china.shtml", "snippet": "4-24 18:06 多条国内新闻头条"},
          {"title": "中国新闻_央视网", "url": "https://news.cctv.com/china/", "snippet": "最新 国内 新闻 快讯"}
        ]
      }
    """

    plan = planner.create_plan("今天的新闻热点", [], registry.list_tools(), prior_context=prior_context)

    assert [step.tool for step in plan] == ["http_fetch", "http_fetch", "http_fetch"]
    assert plan[0].arguments["url"] == "https://www.chinanews.com.cn/china.shtml"
    assert plan[1].arguments["url"] == "https://news.cctv.com/china/"
    assert plan[2].arguments["url"] == "https://example.com/"


def test_heuristic_follows_up_web_search_with_http_fetch_for_content_tasks() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()
    prior_context = """
    [r1-step-1] web_search completed: Search the public web for: 'today news 2026'.
      output:
      {
        "query": "today news 2026",
        "results": [
          {"title": "AP News", "url": "https://apnews.com/", "snippet": "Latest news"},
          {"title": "Reuters", "url": "https://www.reuters.com/world/", "snippet": "World news"}
        ]
      }
    """

    plan = planner.create_plan("今天的新闻", [], registry.list_tools(), prior_context=prior_context)

    assert [step.tool for step in plan] == ["http_fetch", "http_fetch"]
    assert plan[0].arguments["url"] == "https://apnews.com/"
    assert plan[1].arguments["url"] == "https://www.reuters.com/world/"


def test_heuristic_follows_up_web_search_for_docs_queries() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()
    prior_context = """
    [r1-step-1] web_search completed: Search the public web for: 'Python official documentation'.
      output:
      {
        "query": "Python official documentation",
        "results": [
          {"title": "Python docs", "url": "https://docs.python.org/", "snippet": "Official docs"},
          {"title": "Python.org docs", "url": "https://www.python.org/doc/", "snippet": "Documentation portal"},
          {"title": "Tutorial", "url": "https://docs.python.org/3/tutorial/index.html", "snippet": "Tutorial"}
        ]
      }
    """

    plan = planner.create_plan("搜一下 Python 官方文档", [], registry.list_tools(), prior_context=prior_context)

    assert [step.tool for step in plan] == ["http_fetch", "http_fetch"]
    assert plan[0].arguments["url"] in {"https://docs.python.org/", "https://www.python.org/doc/"}
    assert plan[1].arguments["url"] in {"https://docs.python.org/", "https://www.python.org/doc/"}
    assert plan[0].arguments["url"] != plan[1].arguments["url"]


def test_heuristic_skips_memory_shortcut_when_outcome_feedback() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()
    with_memory = planner.create_plan("我是谁", [], registry.list_tools())
    assert with_memory[0].tool == "memory_search"
    with_feedback = planner.create_plan(
        "我是谁", [], registry.list_tools(), outcome_feedback="Previous batch did not satisfy the task."
    )
    assert with_feedback[0].tool != "memory_search"


def test_heuristic_delegate_task_when_user_explicit() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("请用 delegate_task 只读 README.md 前几行", [], registry.list_tools())

    assert len(plan) == 1
    assert plan[0].tool == "delegate_task"
    assert "README" in plan[0].arguments["task"]


def test_heuristic_prefers_du_for_largest_folder_question() -> None:
    registry = ToolRegistry()
    registry.register_builtin_tools()
    planner = HeuristicPlanner()

    plan = planner.create_plan("找到当前最大文件夹", [], registry.list_tools())

    shell = [step for step in plan if step.tool == "shell_exec"]
    assert shell
    assert shell[0].arguments["command"] == ["du", "-h", "-d", "1", "."]
    assert all(step.tool != "search_workspace" for step in plan)
