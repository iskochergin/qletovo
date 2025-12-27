"use client";

import { useRouter } from "next/navigation";
import { memo } from "react";
import { Button } from "@/components/ui/button";
import { PlusIcon } from "./icons";
function PureChatHeader({
  chatId,
  isReadonly,
}: {
  chatId: string;
  isReadonly: boolean;
}) {
  const router = useRouter();

  return (
    <header className="sticky top-0 flex items-center gap-2 bg-background px-3 py-3">
      <Button
        className="h-10 px-3"
        onClick={() => {
          router.push("/");
          router.refresh();
        }}
        variant="outline"
      >
        <PlusIcon className="mr-2" />
        <span>Новый Чат</span>
      </Button>
    </header>
  );
}

export const ChatHeader = memo(PureChatHeader, (prevProps, nextProps) => {
  return (
    prevProps.chatId === nextProps.chatId &&
    prevProps.isReadonly === nextProps.isReadonly
  );
});
