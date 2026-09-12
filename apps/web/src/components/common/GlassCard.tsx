/**
 * @file GlassCard
 * @description Glassmorphism card container; optionally acts as a clickable button with keyboard support (Enter/Space).
 *
 * Responsibilities:
 * - Render the glass surface with optional padding
 * - Act as an accessible button (role, tab index, Enter/Space) when onClick is set
 */

import { cn } from '@/utils/cn';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  padding?: boolean;
  onClick?: () => void;
}

export function GlassCard({ children, className, padding = true, onClick }: GlassCardProps) {
  return (
    <div
      className={cn('glass-card', padding && 'liquid-glass-padded', className)}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') onClick();
            }
          : undefined
      }
    >
      {children}
    </div>
  );
}
