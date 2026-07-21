import type { TaobaoSearchArtifact } from "./productSearchViewModel";

function price(value: number): string {
  return `¥${value.toFixed(2)}`;
}

export function ProductSearchResult({ artifact }: { artifact: TaobaoSearchArtifact }) {
  const statistics = artifact.statistics;
  return (
    <section className="taobao-result" aria-label="淘宝商品搜索结果">
      <div className="taobao-result-heading">
        <strong>淘宝商品 · {artifact.keyword}</strong>
        <span>{artifact.products.length} 个结果</span>
      </div>
      <div className="taobao-products">
        {artifact.products.map((product, index) => (
          <article className="taobao-product" key={`${product.product_url || product.title}-${index}`}>
            {product.image_url ? (
              <img
                src={product.image_url}
                alt={product.title}
                loading="lazy"
                referrerPolicy="no-referrer"
              />
            ) : <div className="taobao-product-placeholder">无图</div>}
            <div className="taobao-product-info">
              {product.product_url ? (
                <a href={product.product_url} target="_blank" rel="noreferrer">{product.title}</a>
              ) : <strong>{product.title}</strong>}
              <span>{product.shop || "店铺信息未提供"}</span>
              <b>{product.price == null ? (product.price_text || "价格未提供") : price(product.price)}</b>
            </div>
          </article>
        ))}
      </div>
      {statistics ? (
        <div className="taobao-statistics">
          <strong>价格统计</strong>
          <span>最低 {price(statistics.min)}</span>
          <span>最高 {price(statistics.max)}</span>
          <span>平均 {price(statistics.average)}</span>
          <span>中位数 {price(statistics.median)}</span>
        </div>
      ) : <div className="taobao-no-price">未识别到可统计的价格</div>}
      {artifact.histogram?.data_url ? (
        <div className="taobao-histogram">
          <strong>价格频数直方图</strong>
          <img src={artifact.histogram.data_url} alt="淘宝商品价格频数直方图" />
        </div>
      ) : null}
    </section>
  );
}
