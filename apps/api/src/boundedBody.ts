// Never materialize an untrusted request body before checking the actual byte count.
// The caller owns its endpoint-specific limit and public error contract.
export async function readBoundedBody(
  request: Request,
  maxBytes: number,
  tooLarge: () => Error,
): Promise<string> {
  const declared = request.headers.get("content-length");
  if (declared !== null && /^\d+$/.test(declared) && Number(declared) > maxBytes) {
    throw tooLarge();
  }
  if (!request.body) return "";

  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let bytes = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return text + decoder.decode();
    bytes += value.byteLength;
    if (bytes > maxBytes) {
      // Do not await a potentially uncooperative producer's cancellation.
      void reader.cancel().catch(() => undefined);
      throw tooLarge();
    }
    text += decoder.decode(value, { stream: true });
  }
}
