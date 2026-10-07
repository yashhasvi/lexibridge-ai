// src/components/Avatar.tsx
import { motion } from "framer-motion";

interface AvatarProps {
  mode: "idle" | "speaking" | "typing" | "responding";
}

export const Avatar: React.FC<AvatarProps> = ({ mode }) => {
  const getAnimation = () => {
    switch (mode) {
      case "speaking":
        return { rotate: [0, -5, 5, -5, 0], transition: { repeat: Infinity, duration: 0.8 } };
      case "typing":
        return { y: [0, -2, 0], transition: { repeat: Infinity, duration: 0.4 } };
      case "responding":
        return { scale: [1, 1.05, 1], transition: { repeat: Infinity, duration: 0.5 } };
      default:
        return {};
    }
  };

  return (
    <motion.div
      className="w-40 h-40 mx-auto bg-green-400 rounded-full flex items-center justify-center text-white text-3xl"
      animate={getAnimation()}
    >
      🦖
    </motion.div>
  );
};
