"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme, systemTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const currentTheme = mounted ? resolvedTheme : systemTheme ?? "light";
  const nextTheme = currentTheme === "dark" ? "light" : "dark";

  if (!mounted) {
    return null;
  }

  return (
    <div className="fixed right-3 top-3 z-30">
      <Button
        aria-label={`Переключить на ${nextTheme === "dark" ? "тёмный" : "светлый"} режим`}
        className="h-10 w-10 p-0"
        onClick={() => setTheme(nextTheme)}
        type="button"
        variant="outline"
      >
        {currentTheme === "dark" ? (
          <Sun className="size-5" />
        ) : (
          <Moon className="size-5" />
        )}
      </Button>
    </div>
  );
}
