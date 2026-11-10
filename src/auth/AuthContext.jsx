import { jsx } from "react/jsx-runtime";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";
import { ApiError, api, authToken } from "../lib/api";
const AuthContext = createContext(null);
function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const signOut = useCallback(() => {
    authToken.clear();
    setUser(null);
  }, []);
  const refreshUser = useCallback(async () => {
    if (!authToken.read()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.me());
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      authToken.clear();
      setUser(null);
    }
  }, []);
  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener("auth:expired", onExpired);
    void refreshUser().catch(() => {
      authToken.clear();
      setUser(null);
    }).finally(() => setLoading(false));
    return () => window.removeEventListener("auth:expired", onExpired);
  }, [refreshUser]);
  const signIn = useCallback(async (email, password) => {
    const result = await api.login(email, password);
    authToken.write(result.access_token);
    setUser(await api.me());
  }, []);
  const signUp = useCallback(
    async (name, email, password) => {
      await api.register(name, email, password);
      await signIn(email, password);
    },
    [signIn]
  );
  const value = useMemo(
    () => ({
      user,
      loading,
      signIn,
      signUp,
      signOut,
      refreshUser,
      updateUser: setUser
    }),
    [user, loading, signIn, signUp, signOut, refreshUser]
  );
  return /* @__PURE__ */ jsx(AuthContext.Provider, { value, children });
}
function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
export {
  AuthProvider,
  useAuth
};
