const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function isValidEmail(value: string): boolean {
  const normalized = normalizeEmail(value);
  return (
    normalized.length > 0 &&
    normalized.length <= 320 &&
    EMAIL_PATTERN.test(normalized)
  );
}

export function isValidPassword(value: string): boolean {
  return value.length >= 8 && value.length <= 128;
}

export function passwordsMatch(
  password: string,
  confirmPassword: string,
): boolean {
  return password === confirmPassword;
}

export function isValidTokenLength(value: string): boolean {
  return value.length === 43;
}

export function validateRegistrationInput(input: {
  email: string;
  password: string;
  confirmPassword: string;
}): string | null {
  if (!isValidEmail(input.email)) {
    return "Enter a valid email address.";
  }

  if (!isValidPassword(input.password)) {
    return "Password must be 8 to 128 characters.";
  }

  if (!passwordsMatch(input.password, input.confirmPassword)) {
    return "Passwords do not match.";
  }

  return null;
}

export function validatePasswordChangeInput(input: {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}): string | null {
  if (!input.currentPassword) {
    return "Enter your current password.";
  }

  if (!isValidPassword(input.newPassword)) {
    return "New password must be 8 to 128 characters.";
  }

  if (!passwordsMatch(input.newPassword, input.confirmPassword)) {
    return "New passwords do not match.";
  }

  return null;
}

export function validatePasswordResetInput(input: {
  resetToken: string;
  newPassword: string;
  confirmPassword: string;
}): string | null {
  if (!isValidTokenLength(input.resetToken.trim())) {
    return "Enter the full 43-character reset token.";
  }

  if (!isValidPassword(input.newPassword)) {
    return "New password must be 8 to 128 characters.";
  }

  if (!passwordsMatch(input.newPassword, input.confirmPassword)) {
    return "New passwords do not match.";
  }

  return null;
}

export function validateVerificationToken(value: string): string | null {
  if (!isValidTokenLength(value.trim())) {
    return "Enter the full 43-character verification token.";
  }

  return null;
}

export function validateTotpCode(value: string): string | null {
  const trimmed = value.trim();
  if (!/^\d{6}$/.test(trimmed)) {
    return "Enter a 6-digit authenticator code.";
  }

  return null;
}
