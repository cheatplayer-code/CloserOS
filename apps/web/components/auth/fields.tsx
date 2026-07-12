import type { InputHTMLAttributes } from "react";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string | null;
}

export function TextField({
  label,
  hint,
  error,
  id,
  ...props
}: TextFieldProps) {
  const fieldId = id ?? props.name;

  return (
    <div className="field">
      <label className="field__label" htmlFor={fieldId}>
        {label}
      </label>
      {hint ? <p className="field__hint">{hint}</p> : null}
      <input
        {...props}
        id={fieldId}
        className={`field__input${error ? " field__input--invalid" : ""}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={
          error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined
        }
      />
      {error ? (
        <p className="field__error" id={`${fieldId}-error`} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface PasswordFieldProps extends Omit<TextFieldProps, "type" | "label"> {
  label: string;
}

export function PasswordField(props: PasswordFieldProps) {
  return <TextField {...props} type="password" spellCheck={false} />;
}
