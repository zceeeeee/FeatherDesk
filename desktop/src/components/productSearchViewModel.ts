import type { ChatMessage } from "../types";

export interface TaobaoProduct {
  title: string;
  shop: string;
  price: number | null;
  price_text?: string;
  image_url?: string;
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
