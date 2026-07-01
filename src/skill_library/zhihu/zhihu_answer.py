ANSWER_URL = "https://www.zhihu.com/question/2054905087156342820"


def _js_string(value: str) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "\\r")
    return f'"{text}"'


def run(keyword: str):
    """Open Zhihu question page, write an answer, and publish it."""
    goto(ANSWER_URL)

    answer_button = "button.Button.FEfUrdfMIKpQDJDqkjte.Button--blue.JmYzaky7MEPMFcJDLNMG"
    wait_for_element(answer_button, timeout=20)
    run_js(
        f"""async () => {{
            const button = document.querySelector("{answer_button}");
            if (!button) return "answer button not found";

            button.scrollIntoView({{ block: "center", inline: "center" }});
            for (let i = 0; i < 20; i += 1) {{
                const disabled =
                    button.getAttribute("data-disabled") === "true" ||
                    button.getAttribute("aria-disabled") === "true" ||
                    button.disabled === true;
                const loading = button.getAttribute("data-loading") === "true";
                if (!disabled && !loading) break;
                await new Promise((resolve) => setTimeout(resolve, 200));
            }}

            const rect = button.getBoundingClientRect();
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;
            const eventOptions = {{
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: x,
                clientY: y,
            }};

            button.dispatchEvent(new PointerEvent("pointerdown", eventOptions));
            button.dispatchEvent(new MouseEvent("mousedown", eventOptions));
            button.dispatchEvent(new PointerEvent("pointerup", eventOptions));
            button.dispatchEvent(new MouseEvent("mouseup", eventOptions));
            button.dispatchEvent(new MouseEvent("click", eventOptions));
            return "answer button dispatched";
        }}"""
    )

    editor_selector = ".AnswerForm .public-DraftEditor-content[contenteditable='true']"
    wait_for_element(editor_selector, timeout=20)

    answer_text = _js_string(keyword)
    run_js(
        f"""(() => {{
            const text = {answer_text};
            const editor =
                document.querySelector("{editor_selector}") ||
                document.querySelector(".AnswerForm [role='textbox'][contenteditable='true']");
            if (!editor) return "Zhihu answer editor not found";

            editor.focus();

            const offsetSpan = editor.querySelector(
                "div[data-contents='true'] .Editable-unstyled " +
                "div[data-offset-key] > span[data-offset-key]"
            );
            if (!offsetSpan) return "Zhihu answer offset span not found";

            const offsetKey = offsetSpan.getAttribute("data-offset-key") || "";
            offsetSpan.innerHTML = "";

            const textSpan = document.createElement("span");
            textSpan.setAttribute("data-text", "true");
            if (offsetKey) {{
                textSpan.setAttribute("data-offset-key", offsetKey);
            }}
            textSpan.textContent = text;
            offsetSpan.appendChild(textSpan);

            editor.dispatchEvent(new InputEvent("input", {{
                bubbles: true,
                cancelable: true,
                inputType: "insertText",
                data: text,
            }}));
            editor.dispatchEvent(new Event("change", {{ bubbles: true }}));
            return textSpan.outerHTML;
        }})()"""
    )
    wait_for_element(editor_selector, timeout=20)
    click(editor_selector)
    wait(2)

    publish_selector = "button.Button.Button--primary.Button--blue.css-78nr5c"
    wait_for_element(publish_selector, timeout=20)
    click(publish_selector)
    wait(2)

    log(f"Zhihu answer published: {keyword}")
    close_browser()
