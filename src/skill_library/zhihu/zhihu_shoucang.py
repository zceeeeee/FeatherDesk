SIGN_URL = "https://www.zhihu.com/signin"


def _js_string(value: str) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "\\r")
    return f'"{text}"'


def _complete_collection_dialog():
    marker = "data-agentic-zhihu-collection-confirm"
    result = "NO_DIALOG"
    for _ in range(8):
        result = run_js(
            f"""(() => {{
                const MARKER = {_js_string(marker)};
                const visible = (el) => {{
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        style.pointerEvents !== "none" &&
                        rect.width > 0 &&
                        rect.height > 0;
                }};
                const textOf = (el) =>
                    (el.getAttribute("aria-label") || el.innerText || el.textContent || "")
                        .replace(/\\s+/g, " ")
                        .trim();

                document.querySelectorAll(`[${{MARKER}}='1']`)
                    .forEach((el) => el.removeAttribute(MARKER));
                const dialogs = Array.from(document.querySelectorAll(
                    "[role='dialog'], .Modal-wrapper, .Modal"
                )).filter(visible);
                if (!dialogs.length) return "NO_DIALOG";

                const buttons = dialogs.flatMap((dialog) =>
                    Array.from(dialog.querySelectorAll("button")).filter(visible)
                );
                const candidates = buttons
                    .map((button) => ({{
                        button,
                        text: textOf(button),
                        primary: /Button--primary|Button--blue/.test(
                            String(button.className || "")
                        ),
                    }}))
                    .filter((item) =>
                        item.text === "\u6536\u85cf" ||
                        item.text === "\u786e\u5b9a" ||
                        item.text === "\u5b8c\u6210"
                    )
                    .sort((a, b) => Number(b.primary) - Number(a.primary));
                if (!candidates.length) {{
                    const seen = buttons.map(textOf).filter(Boolean).slice(0, 12).join(" | ");
                    return `FAILED: collection dialog action not found. Buttons: ${{seen}}`;
                }}
                const target = candidates[0].button;
                target.scrollIntoView({{ block: "center", inline: "center" }});
                target.setAttribute(MARKER, "1");
                return {{ status: "READY", text: candidates[0].text }};
            }})()"""
        )
        if result != "NO_DIALOG":
            break
        wait(0.25)
    log(f"Zhihu collection dialog: {result}")
    if result == "NO_DIALOG":
        return False
    if isinstance(result, str):
        raise RuntimeError(result)

    selector = f'[{marker}="1"]'
    wait(0.5)
    click_result = click(selector)
    log(f"Zhihu collection dialog click result: {click_result}")
    if not click_result or not click_result.get("success"):
        raise RuntimeError(f"Zhihu collection dialog click failed: {click_result}")

    for _ in range(12):
        wait(0.5)
        completed = run_js(
            f"""(() => {{
                const target = document.querySelector({_js_string(selector)});
                if (!target) return true;
                const name = (
                    target.getAttribute("aria-label") ||
                    target.innerText ||
                    target.textContent || ""
                ).replace(/\\s+/g, " ").trim();
                return name === "\u53d6\u6d88\u6536\u85cf" ||
                    name === "\u5df2\u6536\u85cf";
            }})()"""
        )
        if completed:
            log("Zhihu collection completed")
            return True
    raise RuntimeError("Zhihu collection dialog did not confirm the collection")


def _collect_article():
    action_name = "\u6536\u85cf"
    selected_name = "\u53d6\u6d88\u6536\u85cf"
    marker = "data-agentic-zhihu-collect-target"
    result = run_js(
        f"""(() => {{
            const ACTION_NAME = "{action_name}";
            const SELECTED_NAME = "{selected_name}";
            const MARKER = "{marker}";
            const rendered = (el) => {{
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    style.pointerEvents !== "none" &&
                    rect.width > 0 &&
                    rect.height > 0;
            }};
            const getName = (button) =>
                (button.getAttribute("aria-label") ||
                    button.innerText || button.textContent || "")
                    .replace(/\\s+/g, " ")
                    .trim();

            document.querySelectorAll(`[${{MARKER}}='1']`)
                .forEach((el) => el.removeAttribute(MARKER));
            const candidates = Array.from(document.querySelectorAll(
                "button.ContentItem-action"
            ))
                .filter((button) => rendered(button) && !button.disabled)
                .map((button) => ({{
                    button,
                    ariaLabel: (button.getAttribute("aria-label") || "").trim(),
                    name: getName(button),
                    rect: button.getBoundingClientRect(),
                    inArticle: Boolean(button.closest("article")),
                }}))
                .filter((item) =>
                    item.ariaLabel === ACTION_NAME ||
                    item.ariaLabel === SELECTED_NAME
                )
                .sort((a, b) =>
                    Number(b.inArticle) - Number(a.inArticle) ||
                    Math.abs((a.rect.top + a.rect.bottom) / 2 - window.innerHeight / 2) -
                        Math.abs((b.rect.top + b.rect.bottom) / 2 - window.innerHeight / 2) ||
                    a.rect.left - b.rect.left
                );
            const target = candidates[0];
            if (!target) return "FAILED: visible Zhihu collection button not found";
            if (target.ariaLabel === SELECTED_NAME) {{
                return `ALREADY_SELECTED: ${{target.name}}`;
            }}
            target.button.scrollIntoView({{ block: "center", inline: "center" }});
            target.button.setAttribute(MARKER, "1");
            return {{ status: "READY", name: target.name }};
        }})()"""
    )
    log(f"Zhihu collection target: {result}")
    if isinstance(result, str):
        if result.startswith("ALREADY_SELECTED:"):
            return
        raise RuntimeError(result)
    if not result or result.get("status") != "READY":
        raise RuntimeError(f"Zhihu collection target is invalid: {result}")

    selector = f'[{marker}="1"]'
    wait(1)
    center = run_js(
        f"""(() => {{
            const target = document.querySelector({_js_string(selector)});
            if (!target) return null;
            target.scrollIntoView({{ block: "center", inline: "center" }});
            const rect = target.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return null;
            return {{
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
            }};
        }})()"""
    )
    log(f"Trying real mouse click on Zhihu collection button: {center}")
    if not center:
        raise RuntimeError("Zhihu collection target disappeared before mouse click")
    click_result = mouse_click(center["x"], center["y"])
    log(f"Zhihu collection real mouse click result: {click_result}")
    if not click_result or not click_result.get("success"):
        raise RuntimeError(f"Zhihu collection real mouse click failed: {click_result}")

    if _complete_collection_dialog():
        return

    for _ in range(12):
        wait(0.5)
        completed = run_js(
            f"""(() => {{
                const target = document.querySelector({_js_string(selector)});
                if (!target) return false;
                return (target.getAttribute("aria-label") || "").trim() ===
                    "{selected_name}";
            }})()"""
        )
        if completed:
            log("Zhihu collection completed")
            return
    raise RuntimeError("Zhihu collection click produced no selected state")


def run(article_url: str, keyword: str = "-1"):
    article_url = str(article_url or "").strip()
    if not article_url:
        raise RuntimeError("Missing Zhihu article URL for collection")

    if not ensure_auth("zhihu", SIGN_URL):
        log("Zhihu login state not confirmed; skip collection")
        return

    goto(article_url)
    wait_for_element("button.ContentItem-action", timeout=15)
    _collect_article()
    log("finish collection")
