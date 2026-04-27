from uni_agent.agent.intent_router import IntentRouter


def test_intent_router_routes_memory_before_other_shortcuts() -> None:
    router = IntentRouter(memory_query=lambda _: "who am i", web_query=lambda _: "who am i")

    plan = router.route(
        "who am i",
        allowed_tools={"memory_search", "web_search"},
        selected_skill="general",
    )

    assert plan is not None
    assert plan[0].tool == "memory_search"
    assert plan[0].skill == "general"


def test_intent_router_routes_delegate() -> None:
    router = IntentRouter(memory_query=lambda _: None, web_query=lambda _: None)

    plan = router.route(
        "delegate_task: inspect docs",
        allowed_tools={"delegate_task"},
        selected_skill=None,
    )

    assert plan is not None
    assert plan[0].tool == "delegate_task"


def test_intent_router_routes_web_search() -> None:
    router = IntentRouter(memory_query=lambda _: None, web_query=lambda _: "latest docs")

    plan = router.route(
        "look up latest docs",
        allowed_tools={"web_search"},
        selected_skill=None,
    )

    assert plan is not None
    assert plan[0].tool == "web_search"
