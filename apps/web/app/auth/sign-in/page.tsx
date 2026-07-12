import { Suspense } from "react";

import { SignInPage } from "../../../components/auth/auth-pages";
import { Spinner } from "../../../components/auth/spinner";

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="center-state">
          <Spinner label="Loading sign in" />
        </div>
      }
    >
      <SignInPage />
    </Suspense>
  );
}
