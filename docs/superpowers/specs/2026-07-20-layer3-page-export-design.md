# Layer 3 Page Export Design

## Goal

Add a reusable Layer 3 export atomic operation that extracts visible page text, table data, and links for consumption by later operations in the same task. It must ignore images and must work with both Chromium and CloakBrowser through the existing Playwright `Page` interface.

## Scope

In scope:

- Visible text extraction from the current page.
- Visible table extraction with headers and rows.
- Visible link extraction with link text and absolute address.
- Filtering scripts, styles, hidden nodes, image nodes, and image URLs.
- In-memory `export_result` task context.
- Script entry point `export_page()`.
- Explore atomic action `export`.
- Passing an export summary to the next Explore planning cycle.

Out of scope:

- Downloading or embedding images.
- OCR of Canvas, WebGL, screenshots, or image-only text.
- A user-facing export message or file download.
- The future Taobao search skill, product thumbnails, price histogram, median, average, maximum, or minimum calculations.

## Architecture

`src/layer_3/exporter.py` owns DOM extraction and returns an `ExportResult`. It accepts the existing Playwright `Page` object and has no browser-engine-specific dependency. A task context owned by the agent loop stores the latest result under `export_result` for the lifetime of one task.

Two callers share this exporter:

1. The script engine injects `export_page()`, returning a serializable dictionary to the current script. Generated or registered scripts can use that value in a later operation.
2. Explore adds an `export` action type. The Explore executor calls the exporter, returns a serialized result in `ActionResult.value`, and the Explore agent stores the result in the current task context. The next planning prompt receives a bounded summary, while later code can access the full structured result.

No skill registry entry is added. Export is an atomic operation available to the execution layers.

## Data Contract

The serializable result has this shape:

```json
{
  "url": "https://example.test/page",
  "title": "Example",
  "text": "Visible page text...",
  "tables": [
    {
      "headers": ["Product", "Price"],
      "rows": [["Item A", "19.90"]]
    }
  ],
  "links": [
    {"text": "Open item", "href": "https://example.test/item"}
  ]
}
```

Rules:

- Whitespace is normalized in text, table cells, link text, and addresses.
- Hidden nodes, `script`, `style`, `noscript`, `template`, `svg`, `canvas`, `video`, and `img` nodes are excluded from text extraction.
- Image addresses are never collected as links or separate fields.
- Tables with a `thead` use its visible cells as headers; otherwise the first visible row is treated as headers only when the DOM marks it as a header row. Remaining visible rows are returned as data.
- Missing tables or links produce empty arrays.
- Bounds limit text characters and table/link counts to keep the result suitable for task context and LLM prompts. Truncation is deterministic and does not change the result shape.

## Task Context

The agent creates a fresh context at the beginning of each top-level task and discards it after completion. `export_result` is replaced by the latest successful export. Failed exports do not overwrite a previous successful result.

The script engine exposes the current context through the existing restricted namespace without exposing browser internals. Explore injects only a bounded textual summary into its next planning prompt to avoid excessive context; the full result remains available to the next operation through the task context interface.

## Error Handling

- A missing or closed page returns a failed atomic result with a clear error.
- DOM evaluation errors return a failed result and do not create an empty success result.
- Pages with no exportable text, tables, or links return success with empty fields.
- Malformed table rows are skipped individually; one malformed row does not discard valid tables.
- Export never downloads resources and never fails because an image is present.

## Testing

- Unit-test visible text extraction and whitespace normalization.
- Verify scripts, styles, hidden nodes, and image nodes are excluded.
- Verify table headers, rows, empty tables, and malformed rows.
- Verify link text/address extraction and image URL exclusion.
- Verify limits and deterministic truncation.
- Verify the script `export_page()` entry point.
- Verify the Explore `export` action and `ActionResult` serialization.
- Verify the latest successful result is available to the next operation and failed exports do not overwrite it.
- Run the relevant Python tests and the existing desktop/TypeScript checks if shared task or UI code is touched.

## Compatibility

The exporter uses standard synchronous Playwright page methods already used by the project. Chromium and CloakBrowser both satisfy this interface. Canvas/WebGL-only content and image-only text are intentionally unsupported because this operation is text/data-only.
