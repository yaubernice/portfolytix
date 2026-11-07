export default function LogoMark({ size = 36 }) {
  return (
    <svg
      className="logo-mark"
      width={size}
      height={size}
      viewBox="0 0 36 36"
      aria-hidden="true"
    >
      <rect
        x="1"
        y="1"
        width="34"
        height="34"
        rx="3"
        fill="var(--logo-plate, #0f1c2e)"
        stroke="var(--logo-edge, #7a9bb8)"
        strokeWidth="1"
      />
      {/* Ascending chart bars that form the stem of the P */}
      <path
        fill="var(--logo-accent, #e86f4c)"
        d="M7.4 28.2V21.4l4.1-2.5v9.3z"
      />
      <path
        fill="var(--logo-accent, #e86f4c)"
        d="M13.1 28.2V15.4h4.1v12.8z"
      />
      <path
        fill="var(--logo-accent, #e86f4c)"
        d="M18.8 28.2V12l4-2.2v18.4z"
      />
      {/* Open P bowl sitting on the tallest bar */}
      <path
        d="M7.4 8.7H24.2a5.45 5.45 0 0 1 0 10.9"
        fill="none"
        stroke="var(--logo-accent, #e86f4c)"
        strokeWidth="3.1"
        strokeLinecap="butt"
        strokeLinejoin="round"
      />
    </svg>
  );
}
