# 我需要文章的网址信息
# 类似https://zhuanlan.zhihu.com/p/2049017245020558481

SIGN_URL="https://www.zhihu.com/signin"

def _js_string(value: str) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "\\r")
    return f'"{text}"'


def _click_content_action(
    action_name: str,
    selected_name: str,
    marker: str,
):
    action_json = _js_string(action_name)
    selected_json = _js_string(selected_name)
    marker_json = _js_string(marker)
    result = run_js(
        f"""(() => {{
            const ACTION_NAME = {action_json};
            const SELECTED_NAME = {selected_json};
            const MARKER = {marker_json};
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
                    button.innerText ||
                    button.textContent || "")
                    .replace(/\\s+/g, " ")
                    .trim();
            const isSelected = (button, name) => {{
                const pressed = (button.getAttribute("aria-pressed") || "").toLowerCase();
                const checked = (button.getAttribute("aria-checked") || "").toLowerCase();
                const ariaLabel = (button.getAttribute("aria-label") || "").trim();
                const classes = String(button.className || "");
                return pressed === "true" ||
                    checked === "true" ||
                    ariaLabel === SELECTED_NAME ||
                    name.includes(SELECTED_NAME) ||
                    /is-active|active|selected/.test(classes);
            }};

            document.querySelectorAll(`[${{MARKER}}='1']`)
                .forEach((el) => el.removeAttribute(MARKER));
            const buttons = Array.from(document.querySelectorAll("button.ContentItem-action"))
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
                    Math.abs(
                        (a.rect.top + a.rect.bottom) / 2 - window.innerHeight / 2
                    ) - Math.abs(
                        (b.rect.top + b.rect.bottom) / 2 - window.innerHeight / 2
                    ) ||
                    a.rect.left - b.rect.left
                );
            const targetInfo = buttons[0];
            if (!targetInfo) {{
                return `FAILED: visible Zhihu action button "${{ACTION_NAME}}" not found`;
            }}
            if (isSelected(targetInfo.button, targetInfo.name)) {{
                return `ALREADY_SELECTED: ${{targetInfo.name}}`;
            }}
            targetInfo.button.scrollIntoView({{ block: "center", inline: "center" }});
            targetInfo.button.setAttribute(MARKER, "1");
            return {{
                status: "READY",
                name: targetInfo.name,
                text: (targetInfo.button.innerText || targetInfo.button.textContent || "")
                    .replace(/\\s+/g, " ")
                    .trim(),
            }};
        }})()"""
    )
    log(f"Zhihu {action_name} target: {result}")
    if isinstance(result, str):
        if result.startswith("ALREADY_SELECTED:"):
            return
        raise RuntimeError(result)
    if not result or result.get("status") != "READY":
        raise RuntimeError(f"Zhihu {action_name} target is invalid: {result}")

    def _verify_clicked():
        return run_js(
            f"""(() => {{
                const ACTION_NAME = {action_json};
                const SELECTED_NAME = {selected_json};
                const MARKER = {marker_json};
                const candidates = Array.from(document.querySelectorAll(
                    "button.ContentItem-action"
                )).filter((button) => {{
                    const ariaLabel = (button.getAttribute("aria-label") || "").trim();
                    return ariaLabel === ACTION_NAME || ariaLabel === SELECTED_NAME;
                }});
                const selected = candidates.find((button) => {{
                    const ariaLabel = (button.getAttribute("aria-label") || "").trim();
                    return ariaLabel === SELECTED_NAME;
                }});
                if (selected) return true;

                const current = candidates[0] ||
                    document.querySelector(`[${{MARKER}}='1']`);
                if (!current) return false;
                const currentLabel = (current.getAttribute("aria-label") || "").trim();
                return currentLabel === SELECTED_NAME;
            }})()"""
        )

    def _wait_for_clicked():
        for _ in range(12):
            wait(0.5)
            if _verify_clicked():
                log(f"Zhihu {action_name} completed")
                return True
        return False

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
                width: rect.width,
                height: rect.height,
                label: (target.getAttribute("aria-label") || "").trim(),
            }};
        }})()"""
    )
    log(f"Trying real mouse click on Zhihu {action_name} button: {center}")
    if not center:
        raise RuntimeError(f"Zhihu {action_name} target disappeared before mouse click")
    click_result = mouse_click(center["x"], center["y"])
    log(f"Zhihu {action_name} real mouse click result: {click_result}")
    if not click_result or not click_result.get("success"):
        raise RuntimeError(f"Zhihu {action_name} real mouse click failed: {click_result}")
    if _wait_for_clicked():
        return

    raise RuntimeError(
        f"Zhihu {action_name} click produced no selected state ({selected_name})"
    )

def run(article_url: str, keyword: str = "-1"):
    """Open Zhihu writer, fill title/body with keyword, and click publish."""
    article_url = str(article_url or "").strip()
    if not article_url:
        raise RuntimeError("Missing Zhihu article URL for approve")

    if not ensure_auth("zhihu", SIGN_URL):
        log("Zhihu login state not confirmed; skip approve")
        return

    goto(article_url)
 

    wait_for_element("button.VoteButton", timeout=15)
    result = run_js(
        """(() => {
            const APPROVE_TEXT = "\\u8d5e\\u540c";
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const isPressed = (button, name) => {
                const pressed = (button.getAttribute("aria-pressed") || "").toLowerCase();
                const checked = (button.getAttribute("aria-checked") || "").toLowerCase();
                const classes = button.className || "";
                return pressed === "true" ||
                    checked === "true" ||
                    name.includes("\\u5df2\\u8d5e\\u540c") ||
                    name.includes("\\u53d6\\u6d88\\u8d5e\\u540c") ||
                    /is-active|active|selected/.test(String(classes));
            };
            document.querySelectorAll("[data-agentic-zhihu-approve-target='1']")
                .forEach((el) => el.removeAttribute("data-agentic-zhihu-approve-target"));
            const buttons = Array.from(document.querySelectorAll("button.VoteButton"));
            const candidates = buttons
                .filter((button) => {
                    const name = [
                        button.getAttribute("aria-label") || "",
                        button.textContent || "",
                        button.innerText || "",
                    ].join(" ").replace(/\\s+/g, " ").trim();
                    return visible(button) &&
                        name.startsWith(APPROVE_TEXT) &&
                        !isPressed(button, name) &&
                        !button.disabled;
                })
                .map((button) => {
                    const rect = button.getBoundingClientRect();
                    const name = [
                        button.getAttribute("aria-label") || "",
                        button.textContent || "",
                        button.innerText || "",
                    ].join(" ").replace(/\\s+/g, " ").trim();
                    return { button, name, top: rect.top, left: rect.left };
                })
                .sort((a, b) => Math.abs(a.top) - Math.abs(b.top) || a.left - b.left);
            const targetInfo = candidates[0];
            if (!targetInfo) {
                const selected = buttons.find((button) => {
                    if (!visible(button) || button.disabled) return false;
                    const name = [
                        button.getAttribute("aria-label") || "",
                        button.textContent || "",
                        button.innerText || "",
                    ].join(" ").replace(/\\s+/g, " ").trim();
                    return isPressed(button, name);
                });
                if (selected) {
                    const selectedName = [
                        selected.getAttribute("aria-label") || "",
                        selected.textContent || "",
                        selected.innerText || "",
                    ].join(" ").replace(/\\s+/g, " ").trim();
                    return `ALREADY_SELECTED: ${selectedName}`;
                }
                const seen = buttons
                    .filter(visible)
                    .map((button) => [
                        button.getAttribute("aria-label") || "",
                        button.textContent || "",
                        button.innerText || "",
                    ].join(" ").replace(/\\s+/g, " ").trim())
                    .filter(Boolean)
                    .slice(0, 8)
                    .join(" | ");
                return `FAILED: Zhihu unpressed approve button not found. Visible buttons: ${seen}`;
            }
            targetInfo.button.scrollIntoView({ block: "center", inline: "center" });
            targetInfo.button.setAttribute("data-agentic-zhihu-approve-target", "1");
            return `OK: marked Zhihu approve button "${targetInfo.name}"`;
        })()"""
    )
    log(str(result))
    approve_already_selected = str(result).startswith("ALREADY_SELECTED:")
    if str(result).startswith("FAILED:"):
        raise RuntimeError(str(result))

    def _verify_approve_clicked():
        return run_js(
            """(() => {
                const target = document.querySelector("[data-agentic-zhihu-approve-target='1']");
                if (!target) return "FAILED: marked Zhihu approve button disappeared after click";
                const name = [
                    target.getAttribute("aria-label") || "",
                    target.textContent || "",
                    target.innerText || "",
                ].join(" ").replace(/\\s+/g, " ").trim();
                const pressed = (target.getAttribute("aria-pressed") || "").toLowerCase() === "true";
                const checked = (target.getAttribute("aria-checked") || "").toLowerCase() === "true";
                const className = String(target.className || "");
                const active = /is-active|active|selected/.test(className);
                const namePressed =
                    name.includes("\\u5df2\\u8d5e\\u540c") ||
                    name.includes("\\u53d6\\u6d88\\u8d5e\\u540c");
                return `VERIFY: after="${name}", pressed=${pressed || checked || active || namePressed}`;
            })()"""
        )

    def _target_center():
        return run_js(
            """(() => {
                const target = document.querySelector("[data-agentic-zhihu-approve-target='1']");
                if (!target) return null;
                target.scrollIntoView({ block: "center", inline: "center" });
                const rect = target.getBoundingClientRect();
                return {
                    x: rect.left + rect.width / 2,
                    y: rect.top + rect.height / 2,
                    width: rect.width,
                    height: rect.height,
                };
            })()"""
        )

    if approve_already_selected:
        log(f"Zhihu approve already completed: {result}")
    else:
        center = _target_center()
        log(f"Trying real mouse click on Zhihu approve button: {center}")
        if not center:
            raise RuntimeError("Zhihu approve target disappeared before mouse click")
        mouse_click(center["x"], center["y"])
        wait(1)
        verify_result = str(_verify_approve_clicked())
        log(verify_result)

        if "pressed=True" not in verify_result and "pressed=true" not in verify_result:
            raise RuntimeError(f"Zhihu approve click did not change button state after real mouse click: {verify_result}")
    wait(2)

    _click_content_action(
        "\u559c\u6b22",
        "\u53d6\u6d88\u559c\u6b22",
        "data-agentic-zhihu-like-target",
    )

    log(f"finish approve")
