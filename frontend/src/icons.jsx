// Iconos SVG al estilo SF Symbols. La fuente SF Symbols tiene licencia y no se
// puede embeber: se recrean los glifos usados como SVG en currentColor para que
// hereden la etiqueta (label/accent) de cada control en claro y oscuro.
// Todos son decorativos: el nombre accesible vive en el botón contenedor.

function svgProps(className, extra) {
  return {
    className,
    viewBox: '0 0 24 24',
    'aria-hidden': 'true',
    focusable: 'false',
    ...extra,
  }
}

export function IconWave({ className }) {
  return (
    <svg
      {...svgProps(className)}
      fill="none"
      stroke="currentColor"
      strokeWidth="2.1"
      strokeLinecap="round"
    >
      <path d="M3 10.5v3M7.25 7.5v9M11.5 4v16M15.75 7.5v9M20 10.5v3" />
    </svg>
  )
}

export function IconSpark({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path d="M12 2.6l2.05 5.35 5.35 2.05-5.35 2.05L12 17.4l-2.05-5.35L4.6 10l5.35-2.05L12 2.6Z" />
      <path d="M18.8 15.1l.95 2.35 2.35.95-2.35.95-.95 2.35-.95-2.35-2.35-.95 2.35-.95.95-2.35Z" />
    </svg>
  )
}

export function IconMic({ className }) {
  return (
    <svg
      {...svgProps(className)}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3.25a3 3 0 0 1 3 3v5.5a3 3 0 1 1-6 0v-5.5a3 3 0 0 1 3-3Z" />
      <path d="M18.4 11.25a6.4 6.4 0 0 1-12.8 0" />
      <path d="M12 17.65V21" />
    </svg>
  )
}

export function IconArrowUp({ className }) {
  return (
    <svg
      {...svgProps(className)}
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 19.5V5.2" />
      <path d="m5.6 11.4 6.4-6.4 6.4 6.4" />
    </svg>
  )
}

export function IconArrowUpRight({ className }) {
  return (
    <svg
      {...svgProps(className)}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7.5 16.5 16.5 7.5" />
      <path d="M9.4 7.5h7.1v7.1" />
    </svg>
  )
}

export function IconSpeaker({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path d="M11.2 4.3a.9.9 0 0 1 1.5.68v14.04a.9.9 0 0 1-1.5.68l-4.7-4.14a1.6 1.6 0 0 0-1.02-.37H4.75A1.75 1.75 0 0 1 3 13.4v-2.8a1.75 1.75 0 0 1 1.75-1.75h.73c.38 0 .74-.14 1.02-.37l4.7-4.18Z" />
      <path
        d="M15.4 9.1a4.3 4.3 0 0 1 0 5.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        d="M17.8 6.6a7.6 7.6 0 0 1 0 10.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function IconSpeakerOff({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path d="M11.2 4.3a.9.9 0 0 1 1.5.68v14.04a.9.9 0 0 1-1.5.68l-4.7-4.14a1.6 1.6 0 0 0-1.02-.37H4.75A1.75 1.75 0 0 1 3 13.4v-2.8a1.75 1.75 0 0 1 1.75-1.75h.73c.38 0 .74-.14 1.02-.37l4.7-4.18Z" />
      <path
        d="M15.6 9.4 20.8 14.6M20.8 9.4l-5.2 5.2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function IconDoc({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M7.5 3.6A1.6 1.6 0 0 0 5.9 5.2v13.6a1.6 1.6 0 0 0 1.6 1.6h10.8a1.6 1.6 0 0 0 1.6-1.6V9.3a1.6 1.6 0 0 0-.47-1.13l-4.77-4.77A1.6 1.6 0 0 0 13.8 3.6H7.5Zm7.3-.75v4.3c0 .55.45 1 1 1h4.3l-5.3-5.3Z"
      />
    </svg>
  )
}

export function IconInfo({ className }) {
  return (
    <svg
      {...svgProps(className)}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
    >
      <circle cx="12" cy="12" r="8.6" />
      <path d="M12 11.2v5.2" />
      <path d="M12 7.9h.01" />
    </svg>
  )
}

export function IconCheckCircle({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2.9a9.1 9.1 0 1 0 0 18.2 9.1 9.1 0 0 0 0-18.2Zm4.25 6.06-5.15 5.96-3.35-3.03 1.26-1.4 1.93 1.75 3.94-4.57 1.37 1.29Z"
      />
    </svg>
  )
}

export function IconChatTab({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path d="M12 3.4c5.14 0 9.3 3.44 9.3 7.68 0 4.24-4.16 7.68-9.3 7.68-.82 0-1.62-.09-2.38-.25l-4.72 2.09a.62.62 0 0 1-.85-.71l.87-3.5C3.32 14.9 2.7 13.24 2.7 11.08 2.7 6.84 6.86 3.4 12 3.4Z" />
    </svg>
  )
}

export function IconSmileTab({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2.6a9.4 9.4 0 1 0 0 18.8 9.4 9.4 0 0 0 0-18.8ZM8.45 9.2a1.32 1.32 0 1 0 0 2.64 1.32 1.32 0 0 0 0-2.64Zm7.1 0a1.32 1.32 0 1 0 0 2.64 1.32 1.32 0 0 0 0-2.64ZM12 17.35a5.35 5.35 0 0 1-4.66-2.72l1.48-.82a3.86 3.86 0 0 0 6.36 0l1.48.82A5.35 5.35 0 0 1 12 17.35Z"
      />
    </svg>
  )
}

export function IconTextTab({ className }) {
  return (
    <svg {...svgProps(className)} fill="currentColor">
      <path d="M4 5.2h16a1 1 0 1 1 0 2H4a1 1 0 1 1 0-2Zm0 5.8h16a1 1 0 1 1 0 2H4a1 1 0 1 1 0-2Zm0 5.8h10a1 1 0 1 1 0 2H4a1 1 0 1 1 0-2Z" />
    </svg>
  )
}
