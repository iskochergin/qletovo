"use client";

import { type ReactNode, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useChatVisibility } from "@/hooks/use-chat-visibility";
import { cn } from "@/lib/utils";
import {
  CheckCircleFillIcon,
  ChevronDownIcon,
  GlobeIcon,
  LockIcon,
} from "./icons";

export type VisibilityType = "private" | "public";

const visibilities: Array<{
  id: VisibilityType;
  label: string;
  description: string;
  icon: ReactNode;
}> = [
  {
    id: "private",
    label: "Приватный",
    description: "Видно только вам",
    icon: <LockIcon />,
  },
  {
    id: "public",
    label: "Публичный",
    description: "Любой по ссылке",
    icon: <GlobeIcon />,
  },
];

export function VisibilitySelector({
  chatId,
  className,
  selectedVisibilityType,
  disabled,
  ...buttonProps
}: {
  chatId: string;
  selectedVisibilityType: VisibilityType;
} & React.ComponentProps<typeof Button>) {
  const [open, setOpen] = useState(false);

  const { visibilityType, setVisibilityType } = useChatVisibility({
    chatId,
    initialVisibilityType: selectedVisibilityType,
  });

  const selectedVisibility = useMemo(
    () => visibilities.find((visibility) => visibility.id === visibilityType),
    [visibilityType]
  );

  return (
    <DropdownMenu onOpenChange={setOpen} open={open}>
      <DropdownMenuTrigger
        asChild
        className={cn(
          "w-fit data-[state=open]:bg-accent data-[state=open]:text-accent-foreground",
          className
        )}
      >
        <Button
          className="h-11 w-full justify-between px-2"
          data-testid="visibility-selector"
          disabled={disabled}
          variant="outline"
          {...buttonProps}
        >
          {selectedVisibility?.icon}
          <span>{selectedVisibility?.label}</span>
          <ChevronDownIcon className="ml-auto" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="min-w-[300px]">
        {visibilities.map((visibility) => (
          <DropdownMenuItem
            className="group/item flex flex-row items-center justify-between gap-4"
            data-active={visibility.id === visibilityType}
            data-testid={`visibility-selector-item-${visibility.id}`}
            key={visibility.id}
            onSelect={() => {
              setVisibilityType(visibility.id);
              setOpen(false);
            }}
          >
            <div className="flex flex-col items-start gap-1">
              {visibility.label}
              {visibility.description && (
                <div className="text-muted-foreground text-xs">
                  {visibility.description}
                </div>
              )}
            </div>
            <div className="text-foreground opacity-0 group-data-[active=true]/item:opacity-100 dark:text-foreground">
              <CheckCircleFillIcon />
            </div>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
