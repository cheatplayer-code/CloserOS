"use client";

import { useCallback, useRef, useState } from "react";

import type { ApiFailure } from "./types";

interface FormActionState {
  isSubmitting: boolean;
  error: ApiFailure | null;
  fieldError: string | null;
  successMessage: string | null;
}

const INITIAL_STATE: FormActionState = {
  isSubmitting: false,
  error: null,
  fieldError: null,
  successMessage: null,
};

export function useFormAction() {
  const [state, setState] = useState<FormActionState>(INITIAL_STATE);
  const requestIdRef = useRef(0);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  const run = useCallback(
    async <T>(
      action: () => Promise<
        | { ok: true; data?: T }
        | { ok: false; failure: ApiFailure }
        | { ok: true; message: string }
      >,
    ) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;

      setState({
        isSubmitting: true,
        error: null,
        fieldError: null,
        successMessage: null,
      });

      const result = await action();
      if (requestIdRef.current !== requestId) {
        return { ok: false as const, stale: true as const };
      }

      if (!result.ok) {
        setState({
          isSubmitting: false,
          error: result.failure,
          fieldError: null,
          successMessage: null,
        });
        return {
          ok: false as const,
          stale: false as const,
          failure: result.failure,
        };
      }

      if ("message" in result) {
        setState({
          isSubmitting: false,
          error: null,
          fieldError: null,
          successMessage: result.message,
        });
        return {
          ok: true as const,
          stale: false as const,
          message: result.message,
        };
      }

      setState({
        isSubmitting: false,
        error: null,
        fieldError: null,
        successMessage: null,
      });
      return { ok: true as const, stale: false as const, data: result.data };
    },
    [],
  );

  const setFieldError = useCallback((message: string | null) => {
    setState((current) => ({
      ...current,
      fieldError: message,
      error: null,
      successMessage: null,
    }));
  }, []);

  return {
    ...state,
    reset,
    run,
    setFieldError,
  };
}

export type FormActionController = ReturnType<typeof useFormAction>;
