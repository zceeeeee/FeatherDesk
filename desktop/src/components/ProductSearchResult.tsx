import {
  getTaobaoTableRows,
  type TaobaoSearchArtifact
} from "./productSearchViewModel";

function price(value: number): string {
  return `¥${value.toFixed(2)}`;
}

export function ProductSearchResult({ artifact }: { artifact: TaobaoSearchArtifact }) {
  const statistics = artifact.statistics;
  const tableRows = getTaobaoTableRows(artifact);
  return (
    <section className="taobao-result" aria-label="淘宝商品搜索结果">
      <div className="taobao-result-heading">
        <strong>淘宝商品 · {artifact.keyword}</strong>
        <span>{artifact.products.length} 个结果</span>
      </div>
      <div className="taobao-products">
        {artifact.products.slice(0, 3).map((product, index) => (
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
      <div className="taobao-table-scroll">
        <table className="taobao-product-table">
          <thead>
            <tr>
              <th>商品/型号</th>
              <th>价格</th>
              <th>厂商/店铺</th>
              <th>规格参数</th>
              <th>链接</th>
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => (
              <tr key={row.key}>
                <td data-label="商品/型号">
                  <div className="taobao-cell-content">
                    <strong>{row.title}</strong>
                    <span>{row.model}</span>
                  </div>
                </td>
                <td data-label="价格"><span className="taobao-table-price">{row.price}</span></td>
                <td data-label="厂商/店铺"><span>{row.vendor}</span></td>
                <td data-label="规格参数"><span>{row.specifications}</span></td>
                <td data-label="链接">
                  <span>{row.product_url ? (
                    <a href={row.product_url} target="_blank" rel="noreferrer">打开商品</a>
                  ) : "暂无"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
