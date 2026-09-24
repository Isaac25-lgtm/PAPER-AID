import { useState, type FormEvent, type ReactNode } from "react";
import {
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router";
import { Logo } from "../../components/layout/logo";
import { Button } from "../../components/ui/button";
import { Checkbox, Input } from "../../components/ui/field";
import { Alert } from "../../components/ui/primitives";
import { useTitle } from "../../lib/use-title";
import { useAuth } from "./auth-context";

// Only same-site paths are allowed as a post-login destination (no open redirects).
function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//")
    ? value
    : "/app";
}

export function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user)
    return (
      <Navigate
        to={`/sign-in?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );
  return <Outlet />;
}

export function RequireAdmin() {
  const { user } = useAuth();
  if (!user?.isAdmin) return <Navigate to="/app" replace />;
  return <Outlet />;
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M22.5 12.3c0-.8-.1-1.5-.2-2.3H12v4.3h5.9a5 5 0 0 1-2.2 3.3v2.8h3.6c2-1.9 3.2-4.7 3.2-8.1Z"
      />
      <path
        fill="#34A853"
        d="M12 23c3 0 5.5-1 7.3-2.7l-3.6-2.8c-1 .7-2.2 1.1-3.7 1.1-2.9 0-5.3-1.9-6.2-4.6H2.1v2.9A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.8 14c-.2-.7-.4-1.3-.4-2s.1-1.4.4-2V7.1H2.1a11 11 0 0 0 0 9.8L5.8 14Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.2-3.2A11 11 0 0 0 2.1 7.1L5.8 10C6.7 7.3 9.1 5.4 12 5.4Z"
      />
    </svg>
  );
}

function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  const { signInWithGoogle, mode } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [googleError, setGoogleError] = useState<string | null>(null);
  return (
    <div className="flex min-h-dvh flex-col bg-gradient-to-b from-brand-50 to-surface-subtle">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-4 sm:px-6">
        <Logo />
      </header>
      <main
        id="main"
        className="flex flex-1 items-start justify-center px-4 pt-6 pb-16 sm:pt-12"
      >
        <div className="w-full max-w-md">
          <div className="rounded-2xl border border-line bg-white p-6 shadow-raised sm:p-8">
            <h1 className="text-2xl font-bold">{title}</h1>
            <p className="mt-1.5 text-sm text-fg-muted">{subtitle}</p>
            {mode === "firebase" && (
              <>
                <Button
                  variant="secondary"
                  className="mt-6 w-full"
                  onClick={async () => {
                    setGoogleError(null);
                    try {
                      await signInWithGoogle();
                      navigate(safeNext(params.get("next")), { replace: true });
                    } catch (err) {
                      setGoogleError(
                        err instanceof Error
                          ? err.message
                          : "Google sign-in failed.",
                      );
                    }
                  }}
                >
                  <GoogleIcon /> Continue with Google
                </Button>
                {googleError && (
                  <Alert tone="danger" className="mt-3">
                    {googleError}
                  </Alert>
                )}
                <div className="my-6 flex items-center gap-3 text-xs text-fg-subtle">
                  <span className="h-px flex-1 bg-line" /> or with email{" "}
                  <span className="h-px flex-1 bg-line" />
                </div>
              </>
            )}
            {mode === "local" && <div className="mt-6" />}
            {children}
          </div>
          <p className="mt-6 text-center text-sm text-fg-muted">{footer}</p>
          {mode === "local" && (
            <p className="mt-4 rounded-lg bg-white/70 p-3 text-center text-xs text-fg-subtle ring-1 ring-line">
              Local test sign-in, on this computer only: any email with an
              8-character password works. Admin pages open for the emails in
              ADMIN_EMAILS in backend/.env. Google sign-in appears once the
              Firebase project is connected.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

function useAuthSubmit(
  action: (email: string, password: string) => Promise<void>,
) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (
    e: FormEvent<HTMLFormElement>,
    precheck?: () => string | null,
  ) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const problem = precheck?.();
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      await action(
        String(form.get("email") ?? ""),
        String(form.get("password") ?? ""),
      );
      navigate(safeNext(params.get("next")), { replace: true });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Something went wrong. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, submit, next: params.get("next") };
}

export function SignInPage() {
  useTitle("Sign in");
  const { signIn } = useAuth();
  const { error, busy, submit, next } = useAuthSubmit(signIn);
  const query = next ? `?next=${encodeURIComponent(next)}` : "";
  return (
    <AuthShell
      title="Welcome back"
      subtitle={
        next === "/app/new"
          ? "Sign in to upload your paper."
          : "Sign in to see your papers and results."
      }
      footer={
        <>
          New to PaperAid?{" "}
          <Link
            to={`/sign-up${query}`}
            className="font-semibold text-brand-700 hover:underline"
          >
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={(e) => submit(e)} className="space-y-4" noValidate>
        {error && <Alert tone="danger">{error}</Alert>}
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          required
        />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
        <Button type="submit" className="w-full" size="lg" loading={busy}>
          Sign in
        </Button>
      </form>
    </AuthShell>
  );
}

export function SignUpPage() {
  useTitle("Create account");
  const { signUp } = useAuth();
  const { error, busy, submit, next } = useAuthSubmit(signUp);
  const [consent, setConsent] = useState(false);
  const query = next ? `?next=${encodeURIComponent(next)}` : "";
  return (
    <AuthShell
      title="Create your account"
      subtitle="We only ask for what we need to run your jobs."
      footer={
        <>
          Already have an account?{" "}
          <Link
            to={`/sign-in${query}`}
            className="font-semibold text-brand-700 hover:underline"
          >
            Sign in
          </Link>
        </>
      }
    >
      <form
        onSubmit={(e) =>
          submit(e, () =>
            consent ? null : "Please agree to the terms to continue.",
          )
        }
        className="space-y-4"
        noValidate
      >
        {error && <Alert tone="danger">{error}</Alert>}
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          required
        />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          hint="At least 8 characters."
          required
        />
        <Checkbox
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          label={
            <>
              I agree to the Terms and{" "}
              <Link
                to="/privacy"
                className="font-medium text-brand-700 underline"
              >
                Privacy summary
              </Link>
              , including processing of my files by PaperAid&rsquo;s AI
              providers outside Uganda.
            </>
          }
        />
        <Button type="submit" className="w-full" size="lg" loading={busy}>
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}
