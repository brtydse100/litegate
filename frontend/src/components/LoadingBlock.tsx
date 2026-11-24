/** A pulsing placeholder with the shape of the content that is loading. */
export function LoadingBlock({
  label,
  className = "h-32",
}: {
  label: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={`animate-pulse rounded-2xl border border-line-soft bg-card ${className}`}
    >
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Placeholder rows for a list or table that is loading. */
export function LoadingRows({
  label,
  rows = 4,
}: {
  label: string;
  rows?: number;
}) {
  return (
    <div role="status" className="flex flex-col gap-2 px-5 py-4">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          aria-hidden="true"
          className="h-5 animate-pulse rounded bg-well"
          style={{ width: `${90 - index * 12}%` }}
        />
      ))}
    </div>
  );
}

/** A page-shaped placeholder: sidebar and content, before access is known. */
export function LoadingPage({ label }: { label: string }) {
  return (
    <div
      role="status"
      className="min-h-screen bg-canvas md:flex md:h-screen md:overflow-hidden"
    >
      <span className="sr-only">{label}</span>
      <div
        aria-hidden="true"
        className="hidden w-60 shrink-0 border-r border-line-soft bg-card md:block"
      />
      <div
        aria-hidden="true"
        className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-5 px-4 py-9 sm:px-8"
      >
        <div className="h-8 w-56 animate-pulse rounded-lg bg-well" />
        <div className="h-40 animate-pulse rounded-2xl border border-line-soft bg-card" />
        <div className="h-64 animate-pulse rounded-2xl border border-line-soft bg-card" />
      </div>
    </div>
  );
}
