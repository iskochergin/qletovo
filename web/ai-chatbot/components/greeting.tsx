import { motion } from "framer-motion";

export const Greeting = () => {
  return (
    <div
      className="mx-auto mt-4 flex size-full max-w-4xl flex-col items-center justify-center px-4 text-center md:mt-16 md:px-8"
      key="overview"
    >
      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-center gap-3 font-semibold text-2xl md:text-4xl"
        exit={{ opacity: 0, y: 10 }}
        initial={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.5 }}
      >
        <span>Хочешь в Летово?</span>
        <span className="text-3xl md:text-4xl">😊</span>
      </motion.div>
      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="mt-2 text-lg text-zinc-500 md:text-xl"
        exit={{ opacity: 0, y: 10 }}
        initial={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.6 }}
      >
        Я помогу быстро найти ответы по документам «Летово».
        <br />
        Спроси меня что угодно про приём, учёбу или регламенты.
      </motion.div>
    </div>
  );
};
