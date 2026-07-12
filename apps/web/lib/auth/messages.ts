export const GENERIC_REQUEST_ACCEPTED =
  "If the request can be processed, you will receive further instructions shortly.";

export const GENERIC_LOGIN_FAILED =
  "Sign-in failed. Check your email and password, then try again.";

export const GENERIC_AUTH_UNAVAILABLE =
  "Your session is unavailable. Sign in again to continue.";

export const GENERIC_SECURITY_FAILED =
  "This action could not be completed. Refresh the page and try again.";

export const GENERIC_REQUEST_UNAVAILABLE =
  "This request could not be completed. Check your details and try again.";

export const GENERIC_SERVICE_UNAVAILABLE =
  "The service is temporarily unavailable. Try again in a moment.";

export const GENERIC_VALIDATION_FAILED =
  "Some fields need attention before you can continue.";

export const GENERIC_RATE_LIMITED = (seconds: number): string =>
  `Too many attempts. Wait ${seconds} second${seconds === 1 ? "" : "s"} before trying again.`;

export const GENERIC_PASSWORD_CHANGED =
  "Your password was updated successfully.";

export const GENERIC_EMAIL_VERIFIED =
  "Email verification completed. You can now sign in.";

export const GENERIC_PASSWORD_RESET =
  "If the request can be processed, reset instructions will follow.";

export const GENERIC_PASSWORD_RESET_COMPLETE =
  "Your password was reset. Sign in with your new password.";

export const GENERIC_REGISTRATION =
  "Registration request received. If eligible, check your email for verification steps.";

export const GENERIC_MFA_UNAVAILABLE =
  "Security keys are not available yet. Use an authenticator code instead.";
