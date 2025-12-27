"use client";

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { VisibilityType } from "@/components/visibility-selector";

type ActiveChatState = {
  chatId: string | null;
  visibilityType: VisibilityType;
  setVisibilityType?: (visibility: VisibilityType) => void;
};

type ActiveChatContextValue = ActiveChatState & {
  setActiveChat: (nextState: ActiveChatState) => void;
};

const ActiveChatContext = createContext<ActiveChatContextValue | null>(null);

export function ActiveChatProvider({ children }: { children: ReactNode }) {
  const [chatState, setChatState] = useState<ActiveChatState>({
    chatId: null,
    visibilityType: "private",
    setVisibilityType: undefined,
  });

  const value = useMemo<ActiveChatContextValue>(
    () => ({
      ...chatState,
      setActiveChat: setChatState,
    }),
    [chatState]
  );

  return (
    <ActiveChatContext.Provider value={value}>
      {children}
    </ActiveChatContext.Provider>
  );
}

export function useActiveChat() {
  const context = useContext(ActiveChatContext);

  if (!context) {
    throw new Error("useActiveChat must be used within an ActiveChatProvider");
  }

  return context;
}
