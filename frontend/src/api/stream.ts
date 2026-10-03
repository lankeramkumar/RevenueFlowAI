import { ApiError } from "./client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type StreamEvent =
  | { event: "plan"; dispatches: string[] }
  | { event: "specialist"; domain: string; status: string }
  | { event: "result"; data: unknown }
  | { event: "error"; status: number; detail: unknown };

/**
 * Reads a server-sent-events investigation. Aborting `signal` closes the
 * connection, which the server treats as a cancellation.
 */
export async function streamPost(
  path: string,
  body: unknown,
  accessToken: string | undefined,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, "stream_failed", response.statusText);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseBlock(block);
      if (parsed) onEvent(parsed);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function parseBlock(block: string): StreamEvent | null {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    else if (line.startsWith("data: ")) data = line.slice(6);
  }
  if (!event || !data) return null;
  const payload = JSON.parse(data);
  if (event === "plan") return { event, dispatches: payload.dispatches };
  if (event === "specialist") return { event, domain: payload.domain, status: payload.status };
  if (event === "result") return { event, data: payload };
  if (event === "error") return { event, status: payload.status, detail: payload.detail };
  return null;
}
