// Never materialize an untrusted request body before checking the actual byte count.
// The caller owns its endpoint-specific limit and public error contract.
export async function readBoundedBody(
  request: Request,
  maxBytes: number,
  tooLarge: () => Error,
  timedOut?: () => Error,
): Promise<string> {
  const declared = request.headers.get("content-length");
  if (declared !== null && /^\d+$/.test(declared) && Number(declared) > maxBytes) {
    throw tooLarge();
  }
  if (!request.body) return "";

  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  const deadline = Date.now() + 10_000;
  let text = "";
  let bytes = 0;
  for (;;) {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const { done, value } = timedOut
        ? await Promise.race([
          reader.read(),
          new Promise<never>((_, reject) => {
            timer = setTimeout(() => {
              // Reject first: cancellation may complete the pending read immediately.
              reject(timedOut());
              // Do not await cancellation of an uncooperative request producer.
              void reader.cancel().catch(() => undefined);
            }, Math.max(0, deadline - Date.now()));
          }),
        ])
        : await reader.read();
      if (done) return text + decoder.decode();
      bytes += value.byteLength;
      if (bytes > maxBytes) {
        // Do not await a potentially uncooperative producer's cancellation.
        void reader.cancel().catch(() => undefined);
        throw tooLarge();
      }
      text += decoder.decode(value, { stream: true });
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }
}
