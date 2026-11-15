"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, type Me } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/labels";

type SessionValue = { me: Me | null; loading: boolean; refresh: () => Promise<void> };

const SessionContext = createContext<SessionValue>({ me: null, loading: true, refresh: async () => {} });

export function useSession() {
  return useContext(SessionContext);
}

// Asks the workflow service who is signed in, and sends anyone who isn't to /login.
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>("/api/auth/me"));
    } catch (error) {
      setMe(null);
      if (error instanceof ApiError && error.status === 401 && pathname !== "/login") router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [pathname, router]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return <SessionContext.Provider value={{ me, loading, refresh }}>{children}</SessionContext.Provider>;
}

export function SessionBar() {
  const { me, refresh } = useSession();
  const router = useRouter();
  if (!me) return null;

  async function signOut() {
    await api("/api/auth/logout", { method: "POST" });
    await refresh();
    router.replace("/login");
  }

  return (
    <>
      <nav>
        {me.role === "admin" ? <Link href="/admin/users">Users</Link> : <Link href="/">My queue</Link>}
      </nav>
      <div className="who">
        <span data-testid="signed-in-as">
          {me.display_name} · {ROLE_LABEL[me.role]}
        </span>
        <button type="button" className="link" onClick={signOut}>
          Sign out
        </button>
      </div>
    </>
  );
}
