import assert from "node:assert/strict";
import test from "node:test";
import { getTaobaoArtifact } from "../src/components/productSearchViewModel";

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
