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
                    /已赞同|取消赞同/.test(name) ||
                    /is-active|active|selected/.test(String(classes));
            };
            const buttons = Array.from(document.querySelectorAll("button.VoteButton"));
            const target = buttons.find((button) => {
                const name = [
                    button.getAttribute("aria-label") || "",
                    button.textContent || "",
                    button.innerText || "",
                ].join(" ").replace(/\\s+/g, " ").trim();
                return visible(button) &&
                    /^赞同(?:\\s+\\d+)?(?:\\s|$)/.test(name) &&
                    !isPressed(button, name);
            });
            if (!target) return "Zhihu unpressed approve button not found";
            target.scrollIntoView({ block: "center", inline: "center" });
            target.click();
            return "Zhihu approve button clicked";
        })()"""
    )
    log(str(result))
    wait(2)

    log(f"finish approve")
