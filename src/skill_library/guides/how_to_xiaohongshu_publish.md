# 如何实现小红书图文发布

1. 打开 `https://www.xiaohongshu.com/login`。
2. 如果页面出现“手机号登录”，说明当前未登录；填入手机号、勾选协议并点击“获取验证码”。
3. 等待用户手动完成验证码输入，直到页面左下角出现“关于我们”。
4. 登录成功后进入 `https://creator.xiaohongshu.com/publish/publish?source=official&from=tab_switch&target=image`。
5. 先点击“文字配图”。
6. 填入用户给定的图文内容，点击下方“生成图片”。
7. 识别左上方是否出现“预览图片”，出现后点击左下方红色“下一步”。
8. 识别上方是否出现“图片编辑”，出现后点击下方红色“发布”。

示例：

```python
from skill_library.send.xiaohongshu_publish import run

run("今天的图文内容", phone_number="13574133406")
```

用户指令示例：

```text
小红书发布图文，电话号码是13574133406，内容是“今天的穿搭灵感”
```
