import type { ReactNode } from "react";

import { safeOfficialUrl } from "../lib/safeOfficialUrl";

type OfficialSourceLinkProps = {
  url: string | null;
  children: ReactNode;
};

export function OfficialSourceLink({ url, children }: OfficialSourceLinkProps) {
  const href = safeOfficialUrl(url);
  if (!href) return <span className="fine-print">{children} — odkaz není bezpečně dostupný; ověřte u poskytovatele.</span>;
  return <a href={href} rel="noreferrer" target="_blank">{children}</a>;
}
