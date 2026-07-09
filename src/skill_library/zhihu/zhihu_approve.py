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

    log(f"finish approve")
