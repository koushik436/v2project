import { motion } from 'framer-motion';

export default function Card({ className = '', children, hover = true }) {
  return (
    <motion.div
      whileHover={hover ? { y: -3, scale: 1.01 } : undefined}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className={`glass-panel rounded-3xl p-5 md:p-6 ${className}`}
    >
      {children}
    </motion.div>
  );
}
