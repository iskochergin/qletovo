"use client";

import { Moon, Sun, Link as LinkIcon, X as CloseIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useTheme } from "next-themes";
import { PlusIcon } from "@/components/icons";
import { useActiveChat } from "@/components/active-chat-context";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  useSidebar,
} from "@/components/ui/sidebar";
import { VisibilitySelector } from "./visibility-selector";

export function AppSidebar() {
  const router = useRouter();
  const { setOpenMobile, setOpen } = useSidebar();
  const { chatId, visibilityType, setVisibilityType } = useActiveChat();
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const themeLabel = mounted
    ? `Toggle ${resolvedTheme === "dark" ? "light" : "dark"} mode`
    : "Toggle theme";

  useEffect(() => {
    setMounted(true);
  }, []);

  const shareLink = useMemo(() => {
    if (!chatId) {
      return "";
    }
    if (typeof window === "undefined") {
      return `/chat/${chatId}`;
    }
    return `${window.location.origin}/chat/${chatId}`;
  }, [chatId]);

  const handleCopyShareLink = async () => {
    if (!shareLink || visibilityType !== "public") {
      return;
    }

    try {
      await navigator.clipboard.writeText(shareLink);
      toast.success("Ссылка для доступа скопирована");
    } catch (_error) {
      toast.error("Не удалось скопировать ссылку");
    }
  };

  return (
    <Sidebar className="group-data-[side=left]:border-r-0">
      <SidebarHeader>
        <SidebarMenu>
          <div className="flex flex-row items-center justify-between">
            <button
              className="flex flex-row items-center gap-3"
              onClick={() => {
                setOpenMobile(false);
                router.push("/");
                router.refresh();
              }}
              type="button"
            >
              <span className="cursor-pointer rounded-md px-2 font-semibold text-lg hover:bg-muted">
                Chatbot
              </span>
            </button>
            <Button
              className="h-8 w-8 p-1 md:h-fit md:w-fit md:p-2"
              onClick={() => {
                setOpen(false);
              }}
              type="button"
              variant="ghost"
            >
              <span className="sr-only">Close sidebar</span>
              <CloseIcon className="size-4" />
            </Button>
          </div>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <div className="flex flex-col gap-4 p-3">
          <div className="flex flex-col gap-2 rounded-lg border p-3">
            <div className="text-sm font-semibold">Access</div>
            {chatId ? (
              <VisibilitySelector
                chatId={chatId}
                className="w-full justify-between"
                disabled={!setVisibilityType}
                selectedVisibilityType={visibilityType}
                style={{ height: "44px" }}
              />
            ) : (
              <p className="text-muted-foreground text-xs">
                Start a chat to adjust visibility.
              </p>
            )}

            <Button
              className="flex h-11 items-center gap-2"
              disabled={!chatId || visibilityType !== "public"}
              onClick={handleCopyShareLink}
              type="button"
              variant="outline"
            >
              <LinkIcon className="size-4" />
              {visibilityType === "public"
                ? "Copy share link"
                : "Make chat public to share"}
            </Button>
          </div>

          <Button
            className="h-11 justify-center"
            onClick={() =>
              setTheme(resolvedTheme === "dark" ? "light" : "dark")
            }
            type="button"
            variant="outline"
          >
            {mounted ? (
              resolvedTheme === "dark" ? (
                <Sun className="size-4" />
              ) : (
                <Moon className="size-4" />
              )
            ) : null}
            <span className="ml-2">{themeLabel}</span>
          </Button>
        </div>
      </SidebarContent>
    </Sidebar>
  );
}
