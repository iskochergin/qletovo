import { motion } from "framer-motion";

export const Greeting = () => {
  return (
    <div
      className="mx-auto mt-6 flex size-full max-w-4xl flex-col items-center justify-center px-4 text-center md:mt-16 md:px-8"
      key="overview"
    >
      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-center gap-3 font-semibold text-3xl md:text-5xl"
        exit={{ opacity: 0, y: 10 }}
        initial={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.5 }}
      >
        <span className="bg-gradient-to-r from-amber-500 via-orange-500 to-pink-500 bg-clip-text text-balance text-transparent dark:from-amber-300 dark:via-orange-300 dark:to-pink-300 dark:drop-shadow-[0_0_12px_rgba(255,183,94,0.35)]">
          Хочешь в Летово?
        </span>
      </motion.div>
      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="mt-3 max-w-3xl text-xl text-foreground md:text-xl dark:text-white"
        exit={{ opacity: 0, y: 10 }}
        initial={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.6 }}
      >
        Помогу быстро найти ответы на вопросы о поступлении, учёбе и правилах лучшей школы мира!
      </motion.div>
    </div>
  );
};
