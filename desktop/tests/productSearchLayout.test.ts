import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MessageItem } from "../src/components/MessageItem";
import type { ChatMessage } from "../src/types";

const message: ChatMessage = {
  id: "taobao-result",
  conversation_id: "conversation-1",
  role: "assistant",
  type: "result",
  content: "淘宝搜索完成",
  metadata: {
    taobao_product_search: {
      type: "taobao_product_search",
      keyword: "显示器",
      products: Array.from({ length: 5 }, (_, index) => ({
        title: `显示器 ${index + 1}`,
        shop: `店铺 ${index + 1}`,
        model: `M${index + 1}`,
        specifications: "27 英寸；4K",
        price: 1000 + index * 100,
        image_url: `https://img.example/${index + 1}.jpg`,
        product_url: `https://item.taobao.com/item.htm?id=${index + 1}`
      })),
      statistics: null,
      histogram: null
    }
  },
  created_at: "2026-07-22T00:00:00Z"
};

test("Taobao result occupies a wide vertical message and labels responsive cells", () => {
  const html = renderToStaticMarkup(createElement(MessageItem, { message }));

  assert.match(html, /message-has-taobao-result/);
  assert.equal((html.match(/<article class="taobao-product"/g) || []).length, 3);
  assert.match(html, /data-label="商品\/型号"/);
  assert.match(html, /data-label="规格参数"/);
});

test("Taobao result CSS stacks the table inside the default 400px chat window", () => {
  const css = readFileSync("src/styles.css", "utf8");

  assert.match(css, /\.message-has-taobao-result\s*\{[^}]*width:\s*100%/s);
  assert.match(css, /\.message-has-taobao-result \.message-content\s*\{[^}]*display:\s*grid/s);
  assert.match(css, /@media \(max-width:\s*620px\)/);
  assert.match(css, /\.taobao-product-table td::before\s*\{[^}]*content:\s*attr\(data-label\)/s);
});
