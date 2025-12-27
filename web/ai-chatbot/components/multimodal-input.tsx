"use client";

import type { UseChatHelpers } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import equal from "fast-deep-equal";
import {
  type Dispatch,
  memo,
  type SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";
import { useLocalStorage, useWindowSize } from "usehooks-ts";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  PromptInput,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputToolbar,
} from "./elements/prompt-input";
import { ArrowUpIcon, StopIcon } from "./icons";
import { SuggestedActions } from "./suggested-actions";
import { Button } from "./ui/button";
import type { VisibilityType } from "./visibility-selector";

function PureMultimodalInput({
  chatId,
  input,
  setInput,
  status,
  stop,
  messages,
  setMessages,
  sendMessage,
  className,
  selectedVisibilityType,
  selectedModelId: _selectedModelId,
}: {
  chatId: string;
  input: string;
  setInput: Dispatch<SetStateAction<string>>;
  status: UseChatHelpers<ChatMessage>["status"];
  stop: () => void;
  messages: UIMessage[];
  setMessages: UseChatHelpers<ChatMessage>["setMessages"];
  sendMessage: UseChatHelpers<ChatMessage>["sendMessage"];
  className?: string;
  selectedVisibilityType: VisibilityType;
  selectedModelId: string;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { width } = useWindowSize();
  const MIN_TEXTAREA_HEIGHT = 30; // compact single-line start height in px
  const MAX_TEXTAREA_HEIGHT = 4 * 30; // cap height to ~4 lines

  const adjustHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      const nextHeight = Math.min(
        Math.max(textareaRef.current.scrollHeight, MIN_TEXTAREA_HEIGHT),
        MAX_TEXTAREA_HEIGHT
      );
      textareaRef.current.style.height = `${nextHeight}px`;
      textareaRef.current.style.overflowY =
        textareaRef.current.scrollHeight > MAX_TEXTAREA_HEIGHT
          ? "auto"
          : "hidden";
    }
  }, [MAX_TEXTAREA_HEIGHT, MIN_TEXTAREA_HEIGHT]);

  useEffect(() => {
    if (textareaRef.current) {
      adjustHeight();
    }
  }, [adjustHeight]);

  const hasAutoFocused = useRef(false);
  useEffect(() => {
    if (!hasAutoFocused.current && width) {
      const timer = setTimeout(() => {
        textareaRef.current?.focus();
        hasAutoFocused.current = true;
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [width]);

  const resetHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = `${MIN_TEXTAREA_HEIGHT}px`;
      textareaRef.current.style.overflowY = "hidden";
    }
  }, [MIN_TEXTAREA_HEIGHT]);

  const [localStorageInput, setLocalStorageInput] = useLocalStorage(
    "input",
    ""
  );

  useEffect(() => {
    if (textareaRef.current) {
      const domValue = textareaRef.current.value;
      // Prefer DOM value over localStorage to handle hydration
      const finalValue = domValue || localStorageInput || "";
      setInput(finalValue);
      adjustHeight();
    }
    // Only run once after hydration
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adjustHeight, localStorageInput, setInput]);

  useEffect(() => {
    setLocalStorageInput(input);
  }, [input, setLocalStorageInput]);

  const handleInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    adjustHeight();
  };

  const submitForm = useCallback(() => {
    window.history.pushState({}, "", `/chat/${chatId}`);

    sendMessage({
      role: "user",
      parts: [
        {
          type: "text",
          text: input,
        },
      ],
    });

    setLocalStorageInput("");
    resetHeight();
    setInput("");

    if (width && width > 768) {
      textareaRef.current?.focus();
    }
  }, [
    input,
    setInput,
    setLocalStorageInput,
    width,
    chatId,
    resetHeight,
  ]);

  return (
    <div className={cn("relative flex w-full flex-col gap-4", className)}>
      {messages.length === 0 && (
        <SuggestedActions
          chatId={chatId}
          selectedVisibilityType={selectedVisibilityType}
          sendMessage={sendMessage}
        />
      )}

      <PromptInput
        className="border border-border bg-background p-3 shadow-xs transition-all duration-200 focus-within:border-border hover:border-muted-foreground/50 text-[16px]"
        onSubmit={(event) => {
          event.preventDefault();
          if (status !== "ready") {
            toast.error("Подождите, идёт ответ...");
          } else {
            submitForm();
          }
        }}
      >
        <div className="flex flex-row items-start gap-1 sm:gap-2 text-[16px]">
        <PromptInputTextarea
          className="grow resize-none border-0! border-none! bg-transparent px-2 py-1.5 lg:text-[16px] md:text-[16px] text-[16px] leading-8 outline-none ring-0 [-ms-overflow-style:none] [scrollbar-width:none] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 [&::-webkit-scrollbar]:hidden"
          data-testid="multimodal-input"
          disableAutoResize={true}
          maxHeight={200}
          minHeight={MIN_TEXTAREA_HEIGHT}
          onChange={handleInput}
          placeholder="Напишите вопрос..."
          ref={textareaRef}
          style={{
            minHeight: MIN_TEXTAREA_HEIGHT,
            maxHeight: MAX_TEXTAREA_HEIGHT,
          }}
          rows={1}
          value={input}
        />
        </div>
        <PromptInputToolbar className="border-top-0! border-t-0! p-0 shadow-none dark:border-0 dark:border-transparent! justify-end">
          {status === "submitted" ? (
            <StopButton setMessages={setMessages} stop={stop} />
          ) : (
            <PromptInputSubmit
              className="size-8 rounded-full bg-black text-white transition-colors duration-200 hover:bg-black/90 disabled:bg-muted disabled:text-muted-foreground dark:bg-primary dark:text-primary-foreground dark:hover:bg-primary/90"
              data-testid="send-button"
              disabled={!input.trim()}
              status={status}
            >
              <ArrowUpIcon size={14} />
            </PromptInputSubmit>
          )}
        </PromptInputToolbar>
      </PromptInput>
    </div>
  );
}

export const MultimodalInput = memo(
  PureMultimodalInput,
  (prevProps, nextProps) => {
    if (prevProps.input !== nextProps.input) {
      return false;
    }
    if (prevProps.status !== nextProps.status) {
      return false;
    }
    if (prevProps.selectedVisibilityType !== nextProps.selectedVisibilityType) {
      return false;
    }

    return true;
  }
);

function PureStopButton({
  stop,
  setMessages,
}: {
  stop: () => void;
  setMessages: UseChatHelpers<ChatMessage>["setMessages"];
}) {
  return (
    <Button
      className="size-7 rounded-full bg-foreground p-1 text-background transition-colors duration-200 hover:bg-foreground/90 disabled:bg-muted disabled:text-muted-foreground"
      data-testid="stop-button"
      onClick={(event) => {
        event.preventDefault();
        stop();
        setMessages((messages) => messages);
      }}
    >
      <StopIcon size={14} />
    </Button>
  );
}

const StopButton = memo(PureStopButton);
