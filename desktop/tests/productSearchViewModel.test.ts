import assert from "node:assert/strict";
import test from "node:test";
import {
  getTaobaoArtifact,
  getTaobaoTableRows,
  type TaobaoSearchArtifact
} from "../src/components/productSearchViewModel";

test("reads Taobao product artifact from assistant metadata", () => {
  const artifact = getTaobaoArtifact({
    id: "message-1",
    conversation_id: "conversation-1",
    role: "assistant",
    type: "result",
    content: "淘宝搜索完成",
    metadata: {
      taobao_product_search: {
        type: "taobao_product_search",
        keyword: "耳机",
        products: [],
        statistics: null,
        histogram: null
      }
    },
    created_at: "2026-07-20T00:00:00Z"
  });

  assert.equal(artifact?.keyword, "耳机");
});

test("ignores metadata that is not a Taobao artifact", () => {
  const artifact = getTaobaoArtifact({
    id: "message-2",
    conversation_id: "conversation-1",
    role: "assistant",
    type: "result",
    content: "完成",
    metadata: { final_url: "https://example.test" },
    created_at: "2026-07-20T00:00:00Z"
  });

  assert.equal(artifact, null);
});

test("builds at most five Taobao table rows with display fallbacks", () => {
  const artifact: TaobaoSearchArtifact = {
    type: "taobao_product_search",
    keyword: "耳机",
    products: Array.from({ length: 6 }, (_, index) => ({
      title: `商品${index + 1}`,
      shop: `店铺${index + 1}`,
      manufacturer: index === 0 ? "Sony" : "",
      model: index === 0 ? "WH-1000XM6" : "",
      specifications: index === 0 ? "蓝牙 5.3" : "",
      price: index === 0 ? 1999 : null,
      price_text: index === 0 ? "¥1999" : "",
      product_url: `https://item.taobao.com/item.htm?id=${index + 1}`
    })),
    statistics: null,
    histogram: null
  };

  const rows = getTaobaoTableRows(artifact);

  assert.equal(rows.length, 5);
  assert.equal(rows[0].vendor, "Sony");
  assert.equal(rows[0].model, "WH-1000XM6");
  assert.equal(rows[0].specifications, "蓝牙 5.3");
  assert.equal(rows[0].price, "¥1999.00");
  assert.equal(rows[1].vendor, "店铺2");
  assert.equal(rows[1].model, "暂无");
  assert.equal(rows[1].specifications, "暂无");
  assert.equal(rows[4].title, "商品5");
});
