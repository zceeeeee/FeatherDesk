import type { ChatMessage } from "../types";

export interface TaobaoProduct {
  title: string;
  shop: string;
  manufacturer?: string;
  model?: string;
  specifications?: string;
  price: number | null;
  price_text?: string;
  image_url?: string;
  product_url?: string;
}

export interface TaobaoTableRow {
  key: string;
  title: string;
  model: string;
  price: string;
  vendor: string;
  specifications: string;
  product_url?: string;
}

export interface TaobaoSearchArtifact {
  type: "taobao_product_search";
  keyword: string;
  products: TaobaoProduct[];
  statistics: {
    count: number;
    min: number;
    max: number;
    average: number;
    median: number;
  } | null;
  histogram: {
    mime_type: string;
    data_url: string;
    bins: Array<{ start: number; end: number; count: number }>;
  } | null;
}

export function getTaobaoArtifact(message: ChatMessage): TaobaoSearchArtifact | null {
  const value = message.metadata?.taobao_product_search;
  if (!value || typeof value !== "object") return null;
  const artifact = value as Partial<TaobaoSearchArtifact>;
  if (artifact.type !== "taobao_product_search" || !Array.isArray(artifact.products)) return null;
  return artifact as TaobaoSearchArtifact;
}

function valueOrFallback(value: string | undefined): string {
  const normalized = value?.trim();
  return normalized || "暂无";
}

function productPrice(product: TaobaoProduct): string {
  if (product.price != null && Number.isFinite(product.price)) {
    return `¥${product.price.toFixed(2)}`;
  }
  return valueOrFallback(product.price_text);
}

export function getTaobaoTableRows(artifact: TaobaoSearchArtifact): TaobaoTableRow[] {
  return artifact.products.slice(0, 5).map((product, index) => ({
    key: `${product.product_url || product.title}-${index}`,
    title: valueOrFallback(product.title),
    model: valueOrFallback(product.model),
    price: productPrice(product),
    vendor: valueOrFallback(product.manufacturer || product.shop),
    specifications: valueOrFallback(product.specifications),
    product_url: product.product_url
  }));
}
