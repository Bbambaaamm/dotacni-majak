export function verificationLabel(status: string): string {
  switch (status) {
    case "VERIFIED": return "Ověřeno";
    case "PARTIALLY_VERIFIED": return "Částečně ověřeno";
    case "AUTO_EXTRACTED": return "Automaticky zpracováno";
    case "NEEDS_REVIEW": return "Vyžaduje ověření";
    default: return status;
  }
}
