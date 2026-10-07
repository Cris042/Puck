import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("http://localhost:8080/")
    page.get_by_label("E-mail").click()
    page.get_by_label("E-mail").fill("bruna@escola.test")
    page.get_by_label("Matrícula").click()
    page.get_by_label("Matrícula").fill("A0031")
    page.get_by_label("Senha").click()
    page.get_by_label("Senha").fill("Usabilidade#2026")
    page.get_by_role("button", name="Entrar").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
