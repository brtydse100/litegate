/**
 * LiteGate mark: an arched gateway with a key slot, on a blue tile.
 * A configured logo `src` replaces the mark in the same rounded square tile.
 */
export default function LogoMark({
  size,
  className = "",
  src,
  alt = "",
}: {
  size: number;
  className?: string;
  src?: string;
  alt?: string;
}) {
  if (src) {
    return (
      <img
        src={src}
        alt={alt}
        width={size}
        height={size}
        style={{ width: size, height: size, borderRadius: (size * 15) / 64 }}
        className={`shrink-0 object-cover ${className}`}
      />
    );
  }
  // Small sizes get a slightly larger slot so it stays readable.
  const small = size < 40;
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={`shrink-0 ${className}`}
    >
      <rect width="64" height="64" rx="15" fill="rgb(var(--blue-solid))" />
      <path d="M17 49V31a15 15 0 0 1 30 0v18z" fill="#fff" />
      <circle
        cx="32"
        cy="32"
        r={small ? 5 : 4.5}
        fill="rgb(var(--blue-solid))"
      />
      <rect
        x={small ? 29.5 : 30}
        y="34"
        width={small ? 5 : 4}
        height="9"
        rx={small ? 2.5 : 2}
        fill="rgb(var(--blue-solid))"
      />
    </svg>
  );
}
