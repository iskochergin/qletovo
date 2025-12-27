"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function Page() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/");
  }, [router]);

  return (
    <div className="flex h-dvh w-screen items-center justify-center bg-background">
      <div className="rounded-2xl border p-8 text-center">
        <h3 className="font-semibold text-xl">Доступен только гостевой режим</h3>
        <p className="text-muted-foreground mt-2 text-sm">
          Вход по аккаунту отключён. Продолжайте как гость.
        </p>
      </div>
    </div>
  );
}
