import { jsx } from "react/jsx-runtime";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";
import { api, userFacingErrorMessage } from "../lib/api";
import { useAuth } from "../auth/AuthContext";
const BusinessContext = createContext(null);
const SELECTED_BUSINESS_KEY = "receptionist.selected-business";
function BusinessProvider({ children }) {
  const { user } = useAuth();
  const [businesses, setBusinesses] = useState([]);
  const [activeBusinessId, setActiveBusinessId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const refreshBusinesses = useCallback(async (preferredId = null) => {
    if (!user) {
      setBusinesses([]);
      setActiveBusinessId(null);
      setLoading(false);
      return [];
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.businesses();
      setBusinesses(result);
      setActiveBusinessId((current) => {
        const preferred = preferredId || current || localStorage.getItem(SELECTED_BUSINESS_KEY);
        const selected = result.find((business) => business.id === preferred);
        const nextId = selected?.id ?? result[0]?.id ?? null;
        if (nextId) localStorage.setItem(SELECTED_BUSINESS_KEY, nextId);
        else localStorage.removeItem(SELECTED_BUSINESS_KEY);
        return nextId;
      });
      return result;
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not load businesses."));
      setBusinesses([]);
      return null;
    } finally {
      setLoading(false);
    }
  }, [user]);
  useEffect(() => {
    void refreshBusinesses();
  }, [refreshBusinesses]);
  const selectBusiness = useCallback((id) => {
    if (!businesses.some((business) => business.id === id)) return false;
    localStorage.setItem(SELECTED_BUSINESS_KEY, id);
    setActiveBusinessId(id);
    return true;
  }, [businesses]);
  const activeBusiness = businesses.find((business) => business.id === activeBusinessId) ?? null;
  const value = useMemo(
    () => ({
      businesses,
      activeBusiness,
      activeBusinessId,
      loading,
      error,
      selectBusiness,
      refreshBusinesses
    }),
    [
      businesses,
      activeBusiness,
      activeBusinessId,
      loading,
      error,
      selectBusiness,
      refreshBusinesses
    ]
  );
  return /* @__PURE__ */ jsx(BusinessContext.Provider, { value, children });
}
function useBusiness() {
  const context = useContext(BusinessContext);
  if (!context) throw new Error("useBusiness must be used within BusinessProvider");
  return context;
}
export {
  BusinessProvider,
  useBusiness
};
