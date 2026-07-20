# API Connectivity Test Design

## Goal

Add a connectivity test beside the API settings save action. The test verifies that the provider, API key, base URL, and model currently entered in the form can complete a minimal model request without saving those values or restarting the Agent backend.

## User Experience

- Add a secondary `Test connection` button beside `Save settings` on the API and model settings page.
- Disable the test button and show `Testing...` while a request is running.
- Validate that API Key, Base URL, and Model are present before sending a request.
- On success, show `Connection successful. Model is available.` with elapsed time.
- On failure, show a concise actionable message for authentication failure, unavailable model, unreachable endpoint, timeout, or an unexpected response.
- Starting a new test clears the previous result.
- Editing a tested setting clears the previous result so stale success is not shown for new values.
- Do not expose the API key in messages, logs, or returned errors.

## Architecture

The renderer sends the current form values through a new Electron IPC method. The Electron main process performs the network request and returns a normalized result. The test does not use the Python backend because the backend only receives saved configuration when it starts; routing unsaved credentials through it would blur the distinction between the current form and active runtime settings.

The new bridge operation accepts:

- `provider`
- `apiKey`
- `baseUrl`
- `model`
- `requestTimeout`

It returns a discriminated result containing success status, elapsed milliseconds, and a user-facing message. Raw response bodies are not returned to the renderer.

## Provider Requests

### OpenAI-compatible

Send `POST {baseUrl}/chat/completions` with bearer authentication, the selected model, one minimal user message, temperature `0`, and a small output-token limit. A valid successful completion proves both API reachability and model availability.

### Anthropic

Send `POST {baseUrl}/v1/messages` with `x-api-key`, the required Anthropic version header, the selected model, one minimal user message, temperature `0`, and a small output-token limit.

Base URL joining must avoid duplicate slashes. The configured request timeout is capped to the same practical range used by the settings form.

## Error Handling

The main process maps failures into stable messages without including the API key:

- `401` or `403`: API key authentication failed.
- `404`: endpoint or model was not found.
- `408`, abort, or timeout: request timed out.
- Other non-success status: include the status code and a short sanitized provider message when available.
- Network failure: API address could not be reached.
- Successful HTTP response with an invalid provider payload: model response was invalid.

Only one connectivity test is active per settings view. Repeated clicks while testing are ignored by the disabled button.

## Security

- The unsaved API key stays within the renderer-to-main IPC boundary and request headers.
- The key is never persisted by the connectivity test.
- The key is never interpolated into errors or logs.
- The existing encrypted save path remains unchanged.

## Testing

- Unit-test request construction for OpenAI-compatible and Anthropic providers.
- Unit-test URL normalization and timeout behavior.
- Unit-test authentication, model-not-found, timeout, network, and malformed-response error mapping.
- Component-test validation and the testing, success, and failure UI states.
- Run the desktop test suite, TypeScript type checking, and production build.

## Out of Scope

- Listing models from the provider.
- Saving settings automatically after a successful test.
- Testing vision-specific endpoints or multimodal input.
- Changing the active Agent backend configuration.
