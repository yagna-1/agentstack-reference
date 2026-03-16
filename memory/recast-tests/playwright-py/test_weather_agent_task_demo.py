import os
from playwright.sync_api import sync_playwright, expect


def test_weather_agent_task_demo(page):
    # BLOCKED by AstraGraph: rule_id=unknown, score=1.00
    page.keyboard.press("blocked")

