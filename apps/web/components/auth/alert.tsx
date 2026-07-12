type AlertTone = "info" | "success" | "error";

interface AlertProps {
  tone: AlertTone;
  title?: string;
  message: string;
}

export function Alert({ tone, title, message }: AlertProps) {
  return (
    <div
      className={`alert alert--${tone}`}
      role={tone === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      {title ? <p className="alert__title">{title}</p> : null}
      <p className="alert__message">{message}</p>
    </div>
  );
}
