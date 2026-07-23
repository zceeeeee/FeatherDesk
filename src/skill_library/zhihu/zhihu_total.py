"""Publish a Zhihu article, comment on it, then collect it."""


def run(
    title: str,
    keyword: str,
    comment_keyword: str,
    add_picture=False,
    comment_use_ai=False,
    comment_requirement: str = "",
):
    article_url = __zhihu_send_run(
        title=title,
        keyword=keyword,
        add_picture=add_picture,
    )
    article_url = str(article_url or "").strip()
    if not article_url:
        raise RuntimeError("Zhihu total workflow did not receive the published article URL")

    log(f"Zhihu total workflow article URL: {article_url}")
    wait(3)
    log("Zhihu total workflow step: comment")
    __zhihu_comment_run(
        keyword=comment_keyword,
        article_url=article_url,
        use_ai=comment_use_ai,
        requirement_text=comment_requirement,
    )
    wait(2)
    log("Zhihu total workflow step: collect")
    __zhihu_shoucang_run(article_url=article_url)
    log(f"Zhihu total workflow completed: {article_url}")
    return article_url
