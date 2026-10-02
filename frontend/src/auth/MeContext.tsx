import { createContext, useContext } from "react";

export interface MeResponse {
  email: string;
  display_name: string;
  role: string;
  organization_id: string;
  business_units: { id: string; code: string; name: string }[];
}

export const MeContext = createContext<MeResponse | null>(null);

/** Current user's role/org/business-units, loaded once by AppLayout. */
export function useMe(): MeResponse {
  const me = useContext(MeContext);
  if (me === null) {
    throw new Error("useMe() called outside a signed-in MeContext.Provider");
  }
  return me;
}
