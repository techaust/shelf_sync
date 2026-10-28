import { TriangleAlert } from "lucide-react";

/** A field's error line: an icon and the words, so it never relies on its colour (05 section 7). The field names it
 *  in aria-describedby and is aria-invalid. */
export function FieldError({ id, text, wide = false }: { id?: string; text: string; wide?: boolean }) {
  return (
    <p className={`field__error${wide ? " is-wide" : ""}`} id={id}>
      <TriangleAlert className="icon" aria-hidden="true" />
      <span>{text}</span>
    </p>
  );
}
