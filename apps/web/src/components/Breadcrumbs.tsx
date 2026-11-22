import type { BreadcrumbItem } from "../lib/breadcrumbs";

export interface BreadcrumbsProps {
  /** Ordered list of breadcrumb items. The last item is the current page. */
  items: BreadcrumbItem[];
}

/**
 * Accessible breadcrumb navigation.
 *
 * - `aria-label="Kolace"` provides a screen-reader-accessible landmark.
 * - Uses semantic `<nav>` + `<ol>` + `<li>` structure.
 * - The last item uses `aria-current="page"` (no link).
 * - The separator (›) is rendered via CSS `::after` on list items, not as
 *   text content, so screen readers don't announce "chevron".
 * - Icons/spinners are `aria-hidden`; meaning is conveyed by visible text.
 */
export function Breadcrumbs({ items }: BreadcrumbsProps) {
  if (!items.length) return null;

  return (
    <nav aria-label="Kolace" className="breadcrumbs">
      <ol className="breadcrumbs__list">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <li key={index} className="breadcrumbs__item">
              {isLast ? (
                <span
                  aria-current="page"
                  className="breadcrumbs__current"
                >
                  {item.label}
                </span>
              ) : (
                <a
                  href={item.href ?? "#"}
                  className="breadcrumbs__link"
                >
                  {item.label}
                </a>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
